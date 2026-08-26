#include <windows.h>
#include <tlhelp32.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <thread>
#include <vector>

namespace {

struct ThreadSamples {
    DWORD id = 0;
    std::map<std::uint64_t, std::uint64_t> rip_counts;
    std::uint64_t failed_samples = 0;
};

std::vector<DWORD> process_threads(DWORD process_id) {
    std::vector<DWORD> result;
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (snapshot == INVALID_HANDLE_VALUE) return result;

    THREADENTRY32 entry{};
    entry.dwSize = sizeof(entry);
    if (Thread32First(snapshot, &entry)) {
        do {
            if (entry.th32OwnerProcessID == process_id)
                result.push_back(entry.th32ThreadID);
        } while (Thread32Next(snapshot, &entry));
    }
    CloseHandle(snapshot);
    return result;
}

std::uint64_t image_base(DWORD process_id) {
    HANDLE snapshot = CreateToolhelp32Snapshot(
        TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, process_id);
    if (snapshot == INVALID_HANDLE_VALUE) return 0;

    MODULEENTRY32 entry{};
    entry.dwSize = sizeof(entry);
    const bool found = Module32First(snapshot, &entry) != FALSE;
    CloseHandle(snapshot);
    return found
        ? reinterpret_cast<std::uint64_t>(entry.modBaseAddr)
        : 0;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 4) {
        std::cerr << "usage: windows_rip_sampler PID OUTPUT.csv INTERVAL_US\n";
        return 2;
    }

    const DWORD process_id = static_cast<DWORD>(std::stoul(argv[1]));
    const std::string output_path = argv[2];
    const auto interval = std::chrono::microseconds(std::stoll(argv[3]));
    HANDLE process = OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, process_id);
    if (!process) {
        std::cerr << "OpenProcess failed: " << GetLastError() << "\n";
        return 1;
    }

    std::map<DWORD, ThreadSamples> samples;
    for (DWORD thread_id : process_threads(process_id))
        samples.emplace(thread_id, ThreadSamples{thread_id});

    std::atomic_bool stop = false;
    std::thread input_thread([&stop] {
        std::string line;
        std::getline(std::cin, line);
        stop.store(true, std::memory_order_release);
    });

    std::uint64_t iterations = 0;
    auto next_sample = std::chrono::steady_clock::now();
    while (!stop.load(std::memory_order_acquire) &&
           WaitForSingleObject(process, 0) == WAIT_TIMEOUT) {
        if ((iterations % 1000) == 0) {
            for (DWORD thread_id : process_threads(process_id))
                samples.try_emplace(thread_id, ThreadSamples{thread_id});
        }

        for (auto& [thread_id, thread_samples] : samples) {
            HANDLE thread = OpenThread(
                THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT |
                    THREAD_QUERY_INFORMATION,
                FALSE, thread_id);
            if (!thread) {
                ++thread_samples.failed_samples;
                continue;
            }
            if (SuspendThread(thread) == static_cast<DWORD>(-1)) {
                ++thread_samples.failed_samples;
                CloseHandle(thread);
                continue;
            }

            CONTEXT context{};
            context.ContextFlags = CONTEXT_CONTROL;
            if (GetThreadContext(thread, &context))
                ++thread_samples.rip_counts[context.Rip];
            else
                ++thread_samples.failed_samples;

            ResumeThread(thread);
            CloseHandle(thread);
        }

        ++iterations;
        next_sample += interval;
        std::this_thread::sleep_until(next_sample);
    }

    stop.store(true, std::memory_order_release);
    if (input_thread.joinable()) input_thread.join();

    std::ofstream output(output_path);
    if (!output) {
        std::cerr << "cannot create " << output_path << "\n";
        CloseHandle(process);
        return 1;
    }
    output << "# process_id," << process_id << "\n";
    output << "# runtime_image_base,0x" << std::hex
           << image_base(process_id) << std::dec << "\n";
    output << "# interval_us," << interval.count() << "\n";
    output << "# iterations," << iterations << "\n";
    output << "thread_id,rip,samples,failed_thread_samples\n";
    for (const auto& [thread_id, thread_samples] : samples) {
        std::vector<std::pair<std::uint64_t, std::uint64_t>> rows(
            thread_samples.rip_counts.begin(), thread_samples.rip_counts.end());
        std::sort(rows.begin(), rows.end(), [](const auto& left, const auto& right) {
            return left.second > right.second;
        });
        for (const auto& [rip, count] : rows) {
            output << thread_id << ",0x" << std::hex << rip << std::dec << ","
                   << count << "," << thread_samples.failed_samples << "\n";
        }
    }
    CloseHandle(process);
    return 0;
}
