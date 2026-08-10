#include "recomp_launcher.h"
#include "launcher_profile.h"

#include <windows.h>

#include <array>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>

namespace {

constexpr wchar_t kRunner[] =
    L"F:\\Projects\\ndsrecomp\\ndsrecomp\\runner\\build-mph-title\\nds_runner.exe";
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
    bool mouse_aim = true;
    int mouse_sensitivity = 100;
    bool mouse_invert_y = false;
    std::filesystem::path settings_path;
    std::string last_error;
};

struct SensitivityChoice {
    int percent;
    const char* label;
};

constexpr std::array<SensitivityChoice, 10> kSensitivityChoices{{
    {25, "0.25x"},
    {30, "0.30x (legacy)"},
    {50, "0.50x"},
    {75, "0.75x"},
    {100, "1.00x"},
    {125, "1.25x"},
    {150, "1.50x"},
    {200, "2.00x"},
    {300, "3.00x"},
    {400, "4.00x"},
}};

template <size_t N>
void copy_text(char (&target)[N], const char* source) {
    std::snprintf(target, N, "%s", source ? source : "");
}

std::filesystem::path mod_settings_path() {
    if (const char* appdata = std::getenv("APPDATA")) {
        return std::filesystem::path(appdata) /
               "MetroidPrimeHuntersRecomp" / "mods.ini";
    }
    return std::filesystem::temp_directory_path() /
           "MetroidPrimeHuntersRecomp-mods.ini";
}

void load_mod_state(ModState& state) {
    std::ifstream file(state.settings_path);
    std::string line;
    while (std::getline(file, line)) {
        const size_t equals = line.find('=');
        if (equals == std::string::npos) continue;
        const std::string key = line.substr(0, equals);
        const std::string value = line.substr(equals + 1);
        if (key == "adaptive_widescreen")
            state.adaptive_widescreen = value != "false";
        else if (key == "mouse_aim")
            state.mouse_aim = value != "false";
        else if (key == "mouse_sensitivity") {
            char* end = nullptr;
            const long parsed = std::strtol(value.c_str(), &end, 10);
            if (end && *end == '\0' && parsed >= 10 && parsed <= 400)
                state.mouse_sensitivity = static_cast<int>(parsed);
        } else if (key == "mouse_invert_y") {
            state.mouse_invert_y = value == "true";
        }
    }
}

bool save_mod_state(ModState& state) {
    std::error_code error;
    std::filesystem::create_directories(
        state.settings_path.parent_path(), error);
    if (error) {
        state.last_error = "Could not create launcher settings directory: " +
                           error.message();
        return false;
    }
    const std::filesystem::path temporary =
        state.settings_path.string() + ".tmp";
    {
        std::ofstream file(temporary, std::ios::trunc);
        if (!file) {
            state.last_error = "Could not write launcher mod settings.";
            return false;
        }
        file << "adaptive_widescreen="
             << (state.adaptive_widescreen ? "true" : "false") << '\n'
             << "mouse_aim=" << (state.mouse_aim ? "true" : "false")
             << '\n'
             << "mouse_sensitivity=" << state.mouse_sensitivity << '\n'
             << "mouse_invert_y="
             << (state.mouse_invert_y ? "true" : "false") << '\n';
        if (!file) {
            state.last_error = "Could not finish launcher mod settings.";
            return false;
        }
    }
    if (!MoveFileExW(temporary.c_str(), state.settings_path.c_str(),
                     MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
        state.last_error = "Could not replace launcher mod settings.";
        std::filesystem::remove(temporary, error);
        return false;
    }
    state.last_error.clear();
    return true;
}

int mod_feature_count(void*) {
    return 2;
}

int mod_feature_get(void* context, int index,
                    RecompLauncherCModFeature* output) {
    if (!context || !output || index < 0 || index > 1) return 0;
    const auto* state = static_cast<const ModState*>(context);
    std::memset(output, 0, sizeof(*output));
    if (index == 0) {
        copy_text(output->id, "adaptive-widescreen");
        copy_text(output->package_id, "mph-adaptive-widescreen");
        copy_text(output->package_version, "0.1.0");
        copy_text(output->package_name, "MPH Adaptive Widescreen");
        copy_text(output->name, "Adaptive Widescreen");
        copy_text(output->author, "ndsrecomp");
        copy_text(
            output->description,
            "Expands the upper gameplay screen to 21:9 and anchors its HUD "
            "while keeping the lower touchscreen native and clickable.");
        copy_text(output->group, "Display enhancements");
        copy_text(output->status,
                  state->adaptive_widescreen ? "Enabled" : "Disabled");
        output->enabled = state->adaptive_widescreen ? 1 : 0;
    } else {
        copy_text(output->id, "mouse-aim");
        copy_text(output->package_id, "mph-mouse-aim");
        copy_text(output->package_version, "0.1.0");
        copy_text(output->package_name, "MPH Mouse Aim");
        copy_text(output->name, "Mouse Aim");
        copy_text(output->author, "ndsrecomp");
        copy_text(
            output->description,
            "Click the focused top screen to capture relative FPS mouse "
            "aim. Mouse 1 fires; Escape or focus loss releases the cursor. "
            "The bottom screen remains a normal touchscreen.");
        copy_text(output->group, "Controls");
        copy_text(output->status,
                  state->mouse_aim ? "Enabled - click top screen to capture"
                                   : "Disabled");
        output->enabled = state->mouse_aim ? 1 : 0;
        output->option_count = 2;
        output->camera_controls = 1;
    }
    return 1;
}

int mod_feature_enable(void* context, const char* package_id,
                       const char* feature_id, int enabled) {
    if (!context || !package_id || !feature_id) return 0;
    auto* state = static_cast<ModState*>(context);
    if (std::strcmp(package_id, "mph-adaptive-widescreen") == 0 &&
        std::strcmp(feature_id, "adaptive-widescreen") == 0) {
        state->adaptive_widescreen = enabled != 0;
        return 1;
    }
    if (std::strcmp(package_id, "mph-mouse-aim") == 0 &&
        std::strcmp(feature_id, "mouse-aim") == 0) {
        state->mouse_aim = enabled != 0;
        return 1;
    }
    return 0;
}

int mod_feature_option_get(void* context, const char* package_id,
                           const char* feature_id, int index,
                           RecompLauncherCModOption* output) {
    if (!context || !package_id || !feature_id || !output || index < 0 ||
        index > 1 || std::strcmp(package_id, "mph-mouse-aim") != 0 ||
        std::strcmp(feature_id, "mouse-aim") != 0) {
        return 0;
    }
    const auto* state = static_cast<const ModState*>(context);
    std::memset(output, 0, sizeof(*output));
    copy_text(output->group, "Mouse Aim");
    if (index == 0) {
        copy_text(output->id, "sensitivity");
        copy_text(output->label, "Sensitivity");
        copy_text(output->description,
                  "Multiplier for the native MPH relative-aim delta.");
        std::snprintf(output->value, sizeof(output->value), "%d",
                      state->mouse_sensitivity);
        copy_text(output->default_value, "100");
        output->type = RECOMP_MOD_OPTION_CHOICE;
        output->choice_count = static_cast<int>(kSensitivityChoices.size());
    } else {
        copy_text(output->id, "invert-y");
        copy_text(output->label, "Invert Y axis");
        copy_text(output->description,
                  "Reverse vertical relative mouse motion.");
        copy_text(output->value,
                  state->mouse_invert_y ? "true" : "false");
        copy_text(output->default_value, "false");
        output->type = RECOMP_MOD_OPTION_BOOLEAN;
    }
    return 1;
}

int mod_feature_choice_get(void*, const char* package_id,
                           const char* feature_id, const char* option_id,
                           int index, RecompLauncherCModChoice* output) {
    if (!package_id || !feature_id || !option_id || !output || index < 0 ||
        index >= static_cast<int>(kSensitivityChoices.size()) ||
        std::strcmp(package_id, "mph-mouse-aim") != 0 ||
        std::strcmp(feature_id, "mouse-aim") != 0 ||
        std::strcmp(option_id, "sensitivity") != 0) {
        return 0;
    }
    std::memset(output, 0, sizeof(*output));
    const SensitivityChoice& choice = kSensitivityChoices[index];
    std::snprintf(output->value, sizeof(output->value), "%d", choice.percent);
    copy_text(output->label, choice.label);
    return 1;
}

int mod_feature_set_option(void* context, const char* package_id,
                           const char* feature_id, const char* option_id,
                           const char* value) {
    if (!context || !package_id || !feature_id || !option_id || !value ||
        std::strcmp(package_id, "mph-mouse-aim") != 0 ||
        std::strcmp(feature_id, "mouse-aim") != 0) {
        return 0;
    }
    auto* state = static_cast<ModState*>(context);
    if (std::strcmp(option_id, "sensitivity") == 0) {
        char* end = nullptr;
        const long parsed = std::strtol(value, &end, 10);
        if (!end || *end != '\0' || parsed < 10 || parsed > 400)
            return 0;
        state->mouse_sensitivity = static_cast<int>(parsed);
        return 1;
    }
    if (std::strcmp(option_id, "invert-y") == 0) {
        if (std::strcmp(value, "true") == 0) state->mouse_invert_y = true;
        else if (std::strcmp(value, "false") == 0)
            state->mouse_invert_y = false;
        else return 0;
        return 1;
    }
    return 0;
}

int mod_commit(void* context, const char*) {
    return context && save_mod_state(*static_cast<ModState*>(context));
}

const char* mod_last_error(void* context) {
    return context ? static_cast<ModState*>(context)->last_error.c_str() : "";
}

RecompLauncherCModProvider make_mod_provider(ModState* state) {
    RecompLauncherCModProvider provider{};
    provider.ctx = state;
    provider.commit = mod_commit;
    provider.last_error = mod_last_error;
    provider.feature_count = mod_feature_count;
    provider.feature_get = mod_feature_get;
    provider.feature_option_get = mod_feature_option_get;
    provider.feature_choice_get = mod_feature_choice_get;
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
                   bool mouse_aim, int mouse_sensitivity,
                   bool mouse_invert_y, int supersampling, int antialiasing) {
    const std::wstring rom_wide = widen(rom);
    if (rom_wide.empty()) return false;

    std::wstring command =
        quote(kRunner) + L" " + quote(kBios) +
        L" --interactive --rom " + quote(rom_wide) +
        L" --config " + quote(kConfig) +
        L" --screen-layout " +
        (adaptive || mouse_aim || display_layout == 1 ? L"separate"
                                                       : L"stacked") +
        L" --adaptive-widescreen " +
        (adaptive ? L"top" : L"none") +
        L" --supersampling " + std::to_wstring(supersampling) +
        L" --antialiasing " + std::to_wstring(antialiasing) +
        L" --relative-mouse-touch " + (mouse_aim ? L"on" : L"off") +
        L" --relative-mouse-sensitivity " +
        std::to_wstring(mouse_sensitivity) +
        L" --relative-mouse-invert-y " +
        (mouse_invert_y ? L"on" : L"off") +
        L" --relative-mouse-fire-key l" +
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
    mod_state.settings_path = mod_settings_path();
    load_mod_state(mod_state);
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
                         mod_state.mouse_aim,
                         mod_state.mouse_sensitivity,
                         mod_state.mouse_invert_y,
                         settings.supersampling,
                         settings.antialiasing) ? 0 : 3;
}
