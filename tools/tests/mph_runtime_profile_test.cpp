#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

#include "state.h"
#include "title_patches.h"

namespace {

struct Write32 {
    uint32_t addr;
    uint32_t value;
};

std::vector<Write32> g_writes;
uint32_t g_morph_addr = 0;
uint8_t g_morph_value = 0;
int g_failures = 0;

void expect(bool condition, const char* message) {
    if (condition) return;
    std::fprintf(stderr, "FAIL: %s\n", message);
    ++g_failures;
}

void expect_write(std::size_t index, uint32_t addr, uint32_t value,
                  const char* message) {
    const bool ok = index < g_writes.size() &&
                    g_writes[index].addr == addr &&
                    g_writes[index].value == value;
    expect(ok, message);
}

}  // namespace

// title_patches.cpp only needs these bus surfaces. Keeping the test at the
// ABI boundary lets it link the real patched translation unit without a ROM,
// BIOS dump, or generated recomp bank.
bool bus_get_region(const char*, BusRegion*) {
    return false;
}

extern "C" uint8_t bus_read_u8_slow(uint32_t addr) {
    return addr == g_morph_addr ? g_morph_value : 0u;
}

extern "C" void bus_write_u32_slow(uint32_t addr, uint32_t value) {
    g_writes.push_back({addr, value});
}

int main() {
    constexpr const char* kUs10Sha1 =
        "90164d1ac127ee5f9815ea4ae7de798c7b5fc629";
    constexpr const char* kEu11Sha1 =
        "bdcd1dea293e24c98d4c481430e90d21198985a5";

    // Unknown or absent identities must fail closed. Enabling direct aim after
    // a failed selection must not create guest-memory writes.
    expect(!nds_title_patches_select_mph_runtime_profile(nullptr),
           "null ROM identity must not select a runtime profile");
    expect(!nds_title_patches_select_mph_runtime_profile(
               "0000000000000000000000000000000000000000"),
           "unknown ROM identity must not select a runtime profile");
    nds_title_patches_set_mph_mouse_aim(true);
    expect(!nds_title_patches_apply_mph_mouse_delta(1, 1),
           "unknown ROM must not accept direct mouse aim");
    expect(g_writes.empty(), "unknown ROM must not write guest aim fields");
    expect(!nds_title_patches_mph_in_ball(),
           "unknown ROM must not read a guessed morph address");

    // Baseline regression: US1.0 must keep the exact addresses that were
    // hard-coded before multi-ROM support.
    expect(nds_title_patches_select_mph_runtime_profile(kUs10Sha1),
           "US1.0 profile must be selectable");
    nds_title_patches_set_mph_mouse_aim(true);
    g_writes.clear();
    expect(nds_title_patches_apply_mph_mouse_delta(11, -7),
           "US1.0 direct mouse aim must accept a non-zero delta");
    expect(g_writes.size() == 2, "US1.0 aim must perform two writes");
    expect_write(0, 0x020DE526u, 11u,
                 "US1.0 X delta must target baseAimX");
    expect_write(1, 0x020DE52Eu, static_cast<uint32_t>(-7),
                 "US1.0 Y delta must target baseAimY");
    g_morph_addr = 0x020DA818u;
    g_morph_value = 0x02u;
    expect(nds_title_patches_mph_in_ball(),
           "US1.0 baseIsAltForm=2 must report Morph Ball");

    // EU1.1 addresses come from melonPrimeDS
    // MelonPrimeGameRomAddrTable.h, not from an inferred relocation delta.
    expect(nds_title_patches_select_mph_runtime_profile(kEu11Sha1),
           "EU1.1 profile must be selectable");

    // Selection deliberately clears the prior direct-aim enable. This prevents
    // state from one cartridge identity leaking into another profile.
    g_writes.clear();
    expect(!nds_title_patches_apply_mph_mouse_delta(3, 4),
           "profile switch must clear direct-aim enable state");
    expect(g_writes.empty(), "disabled aim after profile switch must not write");

    nds_title_patches_set_mph_mouse_aim(true);
    expect(nds_title_patches_apply_mph_mouse_delta(3, -4),
           "EU1.1 direct mouse aim must accept a non-zero delta");
    expect(g_writes.size() == 2, "EU1.1 aim must perform two writes");
    expect_write(0, 0x020DEE46u, 3u,
                 "EU1.1 X delta must target melonPrimeDS baseAimX");
    expect_write(1, 0x020DEE4Eu, static_cast<uint32_t>(-4),
                 "EU1.1 Y delta must target melonPrimeDS baseAimY");

    g_morph_addr = 0x020DB138u;
    g_morph_value = 0x02u;
    expect(nds_title_patches_mph_in_ball(),
           "EU1.1 baseIsAltForm=2 must report Morph Ball");
    g_morph_value = 0x00u;
    expect(!nds_title_patches_mph_in_ball(),
           "EU1.1 non-alt form must not report Morph Ball");

    // A final invalid identity clears the active profile and prevents stale
    // EU1.1 addresses from remaining live.
    expect(!nds_title_patches_select_mph_runtime_profile("bad"),
           "invalid final identity must clear the runtime profile");
    g_writes.clear();
    nds_title_patches_set_mph_mouse_aim(true);
    expect(!nds_title_patches_apply_mph_mouse_delta(9, 9),
           "cleared profile must reject mouse aim");
    expect(g_writes.empty(), "cleared profile must not retain EU1.1 writes");

    if (g_failures != 0) {
        std::fprintf(stderr, "%d runtime-profile assertion(s) failed\n",
                     g_failures);
        return 1;
    }
    std::puts("OK: exact-ROM MPH runtime profiles dispatch US1.0/EU1.1 safely");
    return 0;
}
