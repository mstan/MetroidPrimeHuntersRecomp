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

struct ModState {
    bool adaptive_widescreen = true;
    bool mouse_aim = true;
    int mouse_sensitivity = 30;
    bool mouse_invert_y = false;
    bool prime_controls = true;
    int virtual_stylus_sensitivity = 20;
    std::string move_forward = "W";
    std::string move_back = "S";
    std::string move_left = "A";
    std::string move_right = "D";
    std::string jump = "Space";
    std::string morph_ball = "Left Ctrl";
    std::string boost_zoom = "Left Shift";
    std::string scan_visor = "C";
    std::string ui_left = "Q";
    std::string ui_right = "E";
    std::string ui_ok = "F";
    std::string shoot = "Mouse Left";
    std::string scan_shoot = "Mouse Right";
    std::string beam = "Mouse 5";
    std::string missile = "Mouse 4";
    std::string weapon1 = "1";
    std::string weapon2 = "2";
    std::string weapon3 = "3";
    std::string weapon4 = "4";
    std::string weapon5 = "5";
    std::string weapon6 = "6";
    std::string virtual_stylus = "Tab";
    std::string menu = "V";
    std::filesystem::path settings_path;
    std::string last_error;
};

struct SensitivityChoice {
    int percent;
    const char* label;
};

constexpr std::array<SensitivityChoice, 11> kSensitivityChoices{{
    {20, "0.20x"},
    {25, "0.25x"},
    {30, "0.30x"},
    {50, "0.50x"},
    {75, "0.75x"},
    {100, "1.00x"},
    {125, "1.25x"},
    {150, "1.50x"},
    {200, "2.00x"},
    {300, "3.00x"},
    {400, "4.00x"},
}};

struct BindingChoice {
    const char* value;
    const char* label;
};

constexpr std::array<BindingChoice, 29> kBindingChoices{{
    {"None", "Unbound"},
    {"W", "W"}, {"A", "A"}, {"S", "S"}, {"D", "D"},
    {"Q", "Q"}, {"E", "E"}, {"F", "F"}, {"C", "C"},
    {"V", "V"}, {"1", "1"}, {"2", "2"}, {"3", "3"},
    {"4", "4"}, {"5", "5"}, {"6", "6"}, {"Tab", "Tab"},
    {"Space", "Space"},
    {"Left Ctrl", "Left Ctrl"}, {"Right Ctrl", "Right Ctrl"},
    {"Left Shift", "Left Shift"}, {"Right Shift", "Right Shift"},
    {"Mouse Left", "Mouse Left"}, {"Mouse Right", "Mouse Right"},
    {"Mouse Middle", "Mouse Middle"}, {"Mouse 4", "Mouse 4"},
    {"Mouse 5", "Mouse 5"},
    {"Return", "Enter"}, {"Backspace", "Backspace"},
}};

struct BindingOption {
    const char* id;
    const char* label;
    const char* group;
    std::string ModState::* member;
    const char* default_value;
};

constexpr std::array<BindingOption, 23> kBindingOptions{{
    {"move-forward", "Move forward", "Movement",
        &ModState::move_forward, "W"},
    {"move-back", "Move back", "Movement",
        &ModState::move_back, "S"},
    {"move-left", "Move left", "Movement",
        &ModState::move_left, "A"},
    {"move-right", "Move right", "Movement",
        &ModState::move_right, "D"},
    {"jump", "Jump", "Movement",
        &ModState::jump, "Space"},
    {"morph-ball", "Morph ball", "Touchscreen helpers",
        &ModState::morph_ball, "Left Ctrl"},
    {"boost-zoom", "Boost / zoom", "Movement",
        &ModState::boost_zoom, "Left Shift"},
    {"scan-visor", "Scan visor", "Touchscreen helpers",
        &ModState::scan_visor, "C"},
    {"ui-left", "UI left", "Touchscreen helpers",
        &ModState::ui_left, "Q"},
    {"ui-right", "UI right", "Touchscreen helpers",
        &ModState::ui_right, "E"},
    {"ui-ok", "UI OK", "Touchscreen helpers",
        &ModState::ui_ok, "F"},
    {"shoot", "Shoot", "Combat",
        &ModState::shoot, "Mouse Left"},
    {"scan-shoot", "Scan shoot", "Combat",
        &ModState::scan_shoot, "Mouse Right"},
    {"beam", "Beam", "Weapons",
        &ModState::beam, "Mouse 5"},
    {"missile", "Missile", "Weapons",
        &ModState::missile, "Mouse 4"},
    {"weapon1", "Subweapon 1", "Weapons",
        &ModState::weapon1, "1"},
    {"weapon2", "Subweapon 2", "Weapons",
        &ModState::weapon2, "2"},
    {"weapon3", "Subweapon 3", "Weapons",
        &ModState::weapon3, "3"},
    {"weapon4", "Subweapon 4", "Weapons",
        &ModState::weapon4, "4"},
    {"weapon5", "Subweapon 5", "Weapons",
        &ModState::weapon5, "5"},
    {"weapon6", "Subweapon 6", "Weapons",
        &ModState::weapon6, "6"},
    {"virtual-stylus", "Virtual stylus", "Touchscreen helpers",
        &ModState::virtual_stylus, "Tab"},
    {"menu", "Menu", "Movement",
        &ModState::menu, "V"},
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
    int settings_version = 0;
    bool saw_mouse_sensitivity = false;
    bool saw_virtual_stylus_sensitivity = false;
    while (std::getline(file, line)) {
        const size_t equals = line.find('=');
        if (equals == std::string::npos) continue;
        const std::string key = line.substr(0, equals);
        const std::string value = line.substr(equals + 1);
        if (key == "settings_version") {
            char* end = nullptr;
            const long parsed = std::strtol(value.c_str(), &end, 10);
            if (end && *end == '\0' && parsed >= 0)
                settings_version = static_cast<int>(parsed);
        } else if (key == "adaptive_widescreen") {
            state.adaptive_widescreen = value != "false";
        } else if (key == "mouse_aim") {
            state.mouse_aim = value != "false";
        } else if (key == "mouse_sensitivity") {
            saw_mouse_sensitivity = true;
            char* end = nullptr;
            const long parsed = std::strtol(value.c_str(), &end, 10);
            if (end && *end == '\0' && parsed >= 10 && parsed <= 400)
                state.mouse_sensitivity = static_cast<int>(parsed);
        } else if (key == "mouse_invert_y") {
            state.mouse_invert_y = value == "true";
        } else if (key == "prime_controls") {
            state.prime_controls = value != "false";
        } else if (key == "virtual_stylus_sensitivity") {
            saw_virtual_stylus_sensitivity = true;
            char* end = nullptr;
            const long parsed = std::strtol(value.c_str(), &end, 10);
            if (end && *end == '\0' && parsed >= 10 && parsed <= 400)
                state.virtual_stylus_sensitivity = static_cast<int>(parsed);
        } else {
            for (const BindingOption& option : kBindingOptions) {
                if (key == option.id) {
                    state.*(option.member) = value;
                    break;
                }
            }
        }
    }
    if (settings_version < 2) {
        if (saw_mouse_sensitivity && state.mouse_sensitivity == 100)
            state.mouse_sensitivity = 30;
        if (saw_virtual_stylus_sensitivity &&
            state.virtual_stylus_sensitivity == 100) {
            state.virtual_stylus_sensitivity = 20;
        }
    }
    state.mouse_aim = state.prime_controls;
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
        file << "settings_version=2\n"
             << "adaptive_widescreen="
             << (state.adaptive_widescreen ? "true" : "false") << '\n'
             << "mouse_aim=" << (state.prime_controls ? "true" : "false")
             << '\n'
             << "mouse_sensitivity=" << state.mouse_sensitivity << '\n'
             << "mouse_invert_y="
             << (state.mouse_invert_y ? "true" : "false") << '\n'
             << "prime_controls="
             << (state.prime_controls ? "true" : "false") << '\n'
             << "virtual_stylus_sensitivity="
             << state.virtual_stylus_sensitivity << '\n';
        for (const BindingOption& option : kBindingOptions)
            file << option.id << "=" << state.*(option.member) << '\n';
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
        copy_text(output->id, "prime-controls");
        copy_text(output->package_id, "mph-prime-controls");
        copy_text(output->package_version, "0.1.0");
        copy_text(output->package_name, "MPH Prime Controls");
        copy_text(output->name, "Prime Controls");
        copy_text(output->author, "ndsrecomp; based on melonPrimeDS");
        copy_text(
            output->description,
            "Maps keyboard and mouse actions to Metroid Prime Hunters "
            "touchscreen helpers and DS buttons using melonPrimeDS defaults.");
        copy_text(output->source_name, "makinori/melonPrimeDS");
        copy_text(output->source_url,
                  "https://github.com/makinori/melonPrimeDS");
        copy_text(output->group, "Controls");
        copy_text(output->status,
                  state->prime_controls
                      ? "Enabled - click top screen to capture"
                      : "Disabled");
        output->enabled = state->prime_controls ? 1 : 0;
        output->option_count =
            3 + static_cast<int>(kBindingOptions.size());
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
    if (std::strcmp(package_id, "mph-prime-controls") == 0 &&
        std::strcmp(feature_id, "prime-controls") == 0) {
        state->prime_controls = enabled != 0;
        state->mouse_aim = state->prime_controls;
        return 1;
    }
    return 0;
}

bool is_binding_choice(const char* value) {
    if (!value) return false;
    for (const BindingChoice& choice : kBindingChoices) {
        if (std::strcmp(choice.value, value) == 0) return true;
    }
    return false;
}

int mod_feature_option_get(void* context, const char* package_id,
                           const char* feature_id, int index,
                           RecompLauncherCModOption* output) {
    if (!context || !package_id || !feature_id || !output || index < 0 ||
        std::strcmp(package_id, "mph-prime-controls") != 0 ||
        std::strcmp(feature_id, "prime-controls") != 0 ||
        index >= 3 + static_cast<int>(kBindingOptions.size())) {
        return 0;
    }
    const auto* state = static_cast<const ModState*>(context);
    std::memset(output, 0, sizeof(*output));
    if (index == 0) {
        copy_text(output->id, "aim-sensitivity");
        copy_text(output->label, "Aim sensitivity");
        copy_text(output->description,
                  "Multiplier for the native MPH relative-aim delta.");
        copy_text(output->group, "Mouse aim");
        std::snprintf(output->value, sizeof(output->value), "%d",
                      state->mouse_sensitivity);
        copy_text(output->default_value, "30");
        output->type = RECOMP_MOD_OPTION_CHOICE;
        output->choice_count = static_cast<int>(kSensitivityChoices.size());
        return 1;
    }
    if (index == 1) {
        copy_text(output->id, "invert-y");
        copy_text(output->label, "Invert Y axis");
        copy_text(output->description,
                  "Reverse vertical relative mouse motion.");
        copy_text(output->group, "Mouse aim");
        copy_text(output->value,
                  state->mouse_invert_y ? "true" : "false");
        copy_text(output->default_value, "false");
        output->type = RECOMP_MOD_OPTION_BOOLEAN;
        return 1;
    }
    if (index == 2) {
        copy_text(output->id, "virtual-stylus-sensitivity");
        copy_text(output->label, "Virtual stylus sensitivity");
        copy_text(output->description,
                  "Multiplier for mouse motion while holding virtual "
                  "stylus.");
        copy_text(output->group, "Touchscreen helpers");
        std::snprintf(output->value, sizeof(output->value), "%d",
                      state->virtual_stylus_sensitivity);
        copy_text(output->default_value, "20");
        output->type = RECOMP_MOD_OPTION_CHOICE;
        output->choice_count = static_cast<int>(kSensitivityChoices.size());
        return 1;
    }
    const BindingOption& option =
        kBindingOptions[static_cast<size_t>(index - 3)];
    copy_text(output->id, option.id);
    copy_text(output->label, option.label);
    copy_text(output->description,
              "Keyboard or mouse input for this Prime Controls action.");
    copy_text(output->group, option.group);
    copy_text(output->value, (state->*(option.member)).c_str());
    copy_text(output->default_value, option.default_value);
    output->type = RECOMP_MOD_OPTION_CHOICE;
    output->choice_count = static_cast<int>(kBindingChoices.size());
    return 1;
}

int mod_feature_choice_get(void*, const char* package_id,
                           const char* feature_id, const char* option_id,
                           int index, RecompLauncherCModChoice* output) {
    if (!package_id || !feature_id || !option_id || !output || index < 0)
        return 0;
    if (std::strcmp(package_id, "mph-prime-controls") != 0 ||
        std::strcmp(feature_id, "prime-controls") != 0) {
        return 0;
    }
    const bool sensitivity =
        (std::strcmp(option_id, "aim-sensitivity") == 0 ||
         std::strcmp(option_id, "virtual-stylus-sensitivity") == 0);
    if (sensitivity) {
        if (index >= static_cast<int>(kSensitivityChoices.size()))
            return 0;
        std::memset(output, 0, sizeof(*output));
        const SensitivityChoice& choice = kSensitivityChoices[index];
        std::snprintf(output->value, sizeof(output->value), "%d",
                      choice.percent);
        copy_text(output->label, choice.label);
        return 1;
    }
    if (std::strcmp(option_id, "invert-y") == 0) return 0;
    if (index >= static_cast<int>(kBindingChoices.size())) {
        return 0;
    }
    bool known_option = false;
    for (const BindingOption& option : kBindingOptions) {
        if (std::strcmp(option_id, option.id) == 0) known_option = true;
    }
    if (!known_option) return 0;
    std::memset(output, 0, sizeof(*output));
    const BindingChoice& choice = kBindingChoices[index];
    copy_text(output->value, choice.value);
    copy_text(output->label, choice.label);
    return 1;
}

int mod_feature_set_option(void* context, const char* package_id,
                           const char* feature_id, const char* option_id,
                           const char* value) {
    if (!context || !package_id || !feature_id || !option_id || !value ||
        std::strcmp(package_id, "mph-prime-controls") != 0 ||
        std::strcmp(feature_id, "prime-controls") != 0) {
        return 0;
    }
    auto* state = static_cast<ModState*>(context);
    if (std::strcmp(option_id, "aim-sensitivity") == 0 ||
        std::strcmp(option_id, "virtual-stylus-sensitivity") == 0) {
        char* end = nullptr;
        const long parsed = std::strtol(value, &end, 10);
        if (!end || *end != '\0' || parsed < 10 || parsed > 400)
            return 0;
        if (std::strcmp(option_id, "aim-sensitivity") == 0)
            state->mouse_sensitivity = static_cast<int>(parsed);
        else
            state->virtual_stylus_sensitivity = static_cast<int>(parsed);
        return 1;
    }
    if (std::strcmp(option_id, "invert-y") == 0) {
        if (std::strcmp(value, "true") == 0) state->mouse_invert_y = true;
        else if (std::strcmp(value, "false") == 0)
            state->mouse_invert_y = false;
        else return 0;
        return 1;
    }
    if (!is_binding_choice(value)) return 0;
    for (const BindingOption& option : kBindingOptions) {
        if (std::strcmp(option_id, option.id) == 0) {
            state->*(option.member) = value;
            return 1;
        }
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

void append_arg(std::wstring& command, const wchar_t* name,
                const std::wstring& value) {
    command += L" ";
    command += name;
    command += L" ";
    command += quote(value);
}

void append_binding_args(std::wstring& command, const ModState& mods) {
    for (const BindingOption& option : kBindingOptions) {
        std::wstring flag = L"--mph-bind-";
        flag += widen(option.id);
        append_arg(command, flag.c_str(), widen((mods.*(option.member)).c_str()));
    }
}

bool launch_runner(const std::filesystem::path& game_dir, const char* rom,
                   int display_layout, bool adaptive,
                   const ModState& mods,
                   int supersampling, int antialiasing) {
    const std::wstring rom_wide = widen(rom);
    if (rom_wide.empty()) return false;

    const std::filesystem::path runner = game_dir / "nds_runner.exe";
    const std::filesystem::path bios = game_dir / "bios";
    const std::filesystem::path config = game_dir / "game.toml";
    const std::array<std::filesystem::path, 3> firmware_files{{
        bios / "biosnds9.rom",
        bios / "biosnds7.rom",
        bios / "firmware.bin",
    }};
    if (!std::filesystem::is_regular_file(runner) ||
        !std::filesystem::is_regular_file(config)) {
        MessageBoxW(nullptr,
            L"The release is incomplete: nds_runner.exe or game.toml is "
            L"missing. Re-extract the full release ZIP.",
            L"Metroid Prime Hunters Recomp", MB_OK | MB_ICONERROR);
        return false;
    }
    bool dumps_present = true;
    for (const auto& file : firmware_files) {
        if (!std::filesystem::is_regular_file(file)) dumps_present = false;
    }
    bool no_dumps_mode = false;
    if (!dumps_present) {
        // Never a silent fallback: missing dumps surface as an explicit
        // choice between supplying dumps and the built-in no-dump path
        // (FreeBIOS + generated firmware + direct boot, beads-yjp.15).
        const int choice = MessageBoxW(nullptr,
            L"Nintendo DS BIOS/firmware dumps were not found in the bios "
            L"folder.\n\n"
            L"Launch with the built-in FreeBIOS and generated firmware "
            L"instead? Nothing but the game ROM is required; the game boots "
            L"directly (no DS menu) and online play uses an identity created "
            L"for this install.\n\n"
            L"Choose No to supply your own verified biosnds9.rom, "
            L"biosnds7.rom, and firmware.bin dumps in the bios folder for "
            L"the fully faithful path.",
            L"Metroid Prime Hunters Recomp",
            MB_YESNO | MB_ICONINFORMATION | MB_DEFBUTTON1);
        if (choice != IDYES) return false;
        no_dumps_mode = true;
        // The bios folder still hosts the persisted per-install identity.
        std::error_code error;
        std::filesystem::create_directories(bios, error);
    }

    std::wstring command =
        quote(runner.wstring()) + L" " + quote(bios.wstring()) +
        L" --interactive --rom " + quote(rom_wide) +
        L" --config " + quote(config.wstring()) +
        L" --screen-layout " +
        (adaptive || mods.prime_controls || display_layout == 1
            ? L"separate"
            : L"stacked") +
        L" --adaptive-widescreen " +
        (adaptive ? L"top" : L"none") +
        L" --supersampling " + std::to_wstring(supersampling) +
        L" --antialiasing " + std::to_wstring(antialiasing) +
        L" --relative-mouse-touch " +
        (mods.prime_controls ? L"on" : L"off") +
        L" --relative-mouse-sensitivity " +
        std::to_wstring(mods.mouse_sensitivity) +
        L" --relative-mouse-invert-y " +
        (mods.mouse_invert_y ? L"on" : L"off") +
        L" --relative-mouse-fire-key l" +
        L" --mph-prime-controls " +
        (mods.prime_controls ? L"on" : L"off") +
        L" --mph-virtual-stylus-sensitivity " +
        std::to_wstring(mods.virtual_stylus_sensitivity) +
        L" --startup-mode automatic" +
        // The runner's own default keeps networking OFF (probe/CI safety);
        // a player launching through the UI expects Nintendo WFC to work,
        // so the launcher turns it on and points it at Wiimmfi.
        L" --network on --wfc on --wfc-provider wiimmfi";
    if (no_dumps_mode)
        command += L" --freebios --generated-firmware --boot direct";
    append_binding_args(command, mods);

    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    const BOOL ok = CreateProcessW(
        runner.c_str(), command.data(), nullptr, nullptr, FALSE,
        CREATE_NO_WINDOW, nullptr, game_dir.c_str(), &startup, &process);
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

#ifndef MPH_RECOMP_UI_NO_MAIN
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

    const std::filesystem::path exe = std::filesystem::weakly_canonical(
        std::filesystem::absolute(argv[0])).parent_path();
    const std::filesystem::path default_rom =
        exe / "Metroid Prime Hunters.nds";
    char selected_rom[1024]{};
    const int result = recomp_launcher_run_window(
        "Metroid Prime Hunters - Launcher", &settings, &game,
        exe.string().c_str(), default_rom.string().c_str(),
        selected_rom, sizeof(selected_rom));
    if (result == 1) return 0;
    if (result == 2) {
        std::fprintf(stderr, "recomp-ui unavailable\n");
        return 2;
    }
    return launch_runner(exe, selected_rom, settings.display_layout,
                         mod_state.adaptive_widescreen,
                         mod_state,
                         settings.supersampling,
                         settings.antialiasing) ? 0 : 3;
}
#endif
