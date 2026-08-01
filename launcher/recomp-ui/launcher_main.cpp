#include "recomp_launcher.h"
#include "launcher_profile.h"

#include <windows.h>

#include <array>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <string>

namespace {

constexpr wchar_t kRunner[] =
    L"F:\\Projects\\ndsrecomp\\ndsrecomp-mph\\runner\\build-mph-title-fixed\\nds_runner.exe";
constexpr wchar_t kBios[] =
    L"F:\\Projects\\ndsrecomp\\ndsrecomp\\bios";
constexpr wchar_t kGameDir[] =
    L"F:\\Projects\\ndsrecomp\\metroidprimehuntersrecomp";
constexpr wchar_t kConfig[] =
    L"F:\\Projects\\ndsrecomp\\metroidprimehuntersrecomp\\game.toml";
constexpr char kDefaultRom[] =
    "F:\\Projects\\ndsrecomp\\metroidprimehuntersrecomp\\Metroid Prime Hunters.nds";

struct ModState {
    bool adaptive_widescreen = true;
};

template <size_t N>
void copy_text(char (&target)[N], const char* source) {
    std::snprintf(target, N, "%s", source ? source : "");
}

int mod_feature_count(void*) {
    return 1;
}

int mod_feature_get(void* context, int index,
                    RecompLauncherCModFeature* output) {
    if (!context || !output || index != 0) return 0;
    const auto* state = static_cast<const ModState*>(context);
    std::memset(output, 0, sizeof(*output));
    copy_text(output->id, "adaptive-widescreen");
    copy_text(output->package_id, "mph-adaptive-widescreen");
    copy_text(output->package_version, "0.1.0");
    copy_text(output->package_name, "MPH Adaptive Widescreen");
    copy_text(output->name, "Adaptive Widescreen");
    copy_text(output->author, "ndsrecomp");
    copy_text(
        output->description,
        "Expands the upper gameplay screen to 21:9 and anchors its HUD while "
        "keeping the lower touchscreen native, separate, and clickable.");
    copy_text(output->group, "Display enhancements");
    copy_text(output->status,
              state->adaptive_widescreen ? "Enabled" : "Disabled");
    output->enabled = state->adaptive_widescreen ? 1 : 0;
    return 1;
}

int mod_feature_enable(void* context, const char* package_id,
                       const char* feature_id, int enabled) {
    if (!context || !package_id || !feature_id ||
        std::strcmp(package_id, "mph-adaptive-widescreen") != 0 ||
        std::strcmp(feature_id, "adaptive-widescreen") != 0) {
        return 0;
    }
    static_cast<ModState*>(context)->adaptive_widescreen = enabled != 0;
    return 1;
}

int mod_feature_option_get(void*, const char*, const char*, int,
                           RecompLauncherCModOption*) {
    return 0;
}

int mod_feature_set_option(void*, const char*, const char*, const char*,
                           const char*) {
    return 0;
}

int mod_commit(void*, const char*) {
    return 1;
}

const char* mod_last_error(void*) {
    return "";
}

RecompLauncherCModProvider make_mod_provider(ModState* state) {
    RecompLauncherCModProvider provider{};
    provider.ctx = state;
    provider.commit = mod_commit;
    provider.last_error = mod_last_error;
    provider.feature_count = mod_feature_count;
    provider.feature_get = mod_feature_get;
    provider.feature_option_get = mod_feature_option_get;
    provider.feature_enable = mod_feature_enable;
    provider.feature_set_option = mod_feature_set_option;
    provider.archive_extension = ".ndsmod";
    provider.archive_description = "Nintendo DS mod package";
    return provider;
}

std::wstring widen(const char* source) {
    if (!source || !source[0]) return {};
    const int count = MultiByteToWideChar(
        CP_UTF8, 0, source, -1, nullptr, 0);
    if (count <= 1) return {};
    std::wstring result(static_cast<size_t>(count), L'\0');
    MultiByteToWideChar(
        CP_UTF8, 0, source, -1, result.data(), count);
    result.resize(static_cast<size_t>(count - 1));
    return result;
}

std::wstring quote(const std::wstring& value) {
    return L"\"" + value + L"\"";
}

bool launch_runner(const char* rom, int display_layout, bool adaptive,
                   int supersampling, int antialiasing) {
    const std::wstring rom_wide = widen(rom);
    if (rom_wide.empty()) return false;

    std::wstring command =
        quote(kRunner) + L" " + quote(kBios) +
        L" --interactive --rom " + quote(rom_wide) +
        L" --config " + quote(kConfig) +
        L" --screen-layout " +
        (adaptive || display_layout == 1 ? L"separate" : L"stacked") +
        L" --adaptive-widescreen " +
        (adaptive ? L"top" : L"none") +
        L" --supersampling " + std::to_wstring(supersampling) +
        L" --antialiasing " + std::to_wstring(antialiasing) +
        L" --startup-mode automatic";

    wchar_t old_path[32768]{};
    GetEnvironmentVariableW(L"PATH", old_path,
                            static_cast<DWORD>(std::size(old_path)));
    std::wstring path =
        L"C:\\msys64\\mingw64\\bin;" + std::wstring(old_path);
    SetEnvironmentVariableW(L"PATH", path.c_str());

    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    const BOOL ok = CreateProcessW(
        kRunner, command.data(), nullptr, nullptr, FALSE,
        CREATE_NO_WINDOW, nullptr, kGameDir, &startup, &process);
    if (!ok) {
        std::fprintf(stderr, "CreateProcessW failed: %lu\n",
                     static_cast<unsigned long>(GetLastError()));
        return false;
    }
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return true;
}

}  // namespace

int main(int argc, char** argv) {
    (void)argc;

    RecompLauncherCSettings settings{};
    settings.output_method = 2;
    settings.window_scale = 3;
    settings.fullscreen = 0;
    settings.linear_filter = 0;
    settings.widescreen = 1;
    settings.widescreen_hud = 1;
    settings.enable_audio = 1;
    settings.audio_freq = 32768;
    settings.volume = 100;
    settings.player_src[0] = 2;
    settings.display_layout = 1;
    settings.supersampling = 1;
    settings.antialiasing = 0;

    static const char* const sha1[] = {
        "90164d1ac127ee5f9815ea4ae7de798c7b5fc629",
    };
    static const char* const display_layouts[] = {
        "Stacked window",
        "Separate windows",
    };
    ModState mod_state{};
    RecompLauncherCModProvider mod_provider = make_mod_provider(&mod_state);

    RecompLauncherCGameInfo game{};
    launcher_profile_apply("nds", &game);
    game.name = "Metroid Prime Hunters";
    game.region = "USA";
    game.known_sha1_hex = sha1;
    game.num_known_sha1 = std::size(sha1);
    game.widescreen_supported = 0;
    game.lock_device = 0;
    game.hide_rebind = 0;
    game.display_layout_labels = display_layouts;
    game.num_display_layouts = std::size(display_layouts);
    game.mods = &mod_provider;

    const std::filesystem::path exe =
        std::filesystem::absolute(argv[0]).parent_path();
    char selected_rom[1024]{};
    const int result = recomp_launcher_run_window(
        "Metroid Prime Hunters - Launcher", &settings, &game,
        exe.string().c_str(), kDefaultRom,
        selected_rom, sizeof(selected_rom));
    if (result == 1) return 0;
    if (result == 2) {
        std::fprintf(stderr, "recomp-ui unavailable\n");
        return 2;
    }
    return launch_runner(selected_rom, settings.display_layout,
                         mod_state.adaptive_widescreen,
                         settings.supersampling,
                         settings.antialiasing) ? 0 : 3;
}
