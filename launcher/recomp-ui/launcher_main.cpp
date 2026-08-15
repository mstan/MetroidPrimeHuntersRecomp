#include "recomp_launcher.h"
#include "launcher_profile.h"
#include "sha1.h"

#include <windows.h>

#include <array>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace {

struct ModState {
    bool adaptive_widescreen = true;
    bool mouse_aim = true;
    int mouse_sensitivity = 30;
    bool mouse_invert_y = false;
    bool prime_controls = true;
    int virtual_stylus_sensitivity = 20;
    int pad_aim_sensitivity = 100;
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
    // Gamepad bindings for the same actions (runner
    // nds_default_mph_pad_bindings defaults). "None" = unbound; movement
    // stays on the left stick / D-pad natively.
    std::string pad_move_forward = "None";
    std::string pad_move_back = "None";
    std::string pad_move_left = "None";
    std::string pad_move_right = "None";
    std::string pad_jump = "Pad A";
    std::string pad_morph_ball = "Pad B";
    std::string pad_boost_zoom = "Pad RB";
    std::string pad_scan_visor = "Pad R3";
    std::string pad_ui_left = "Pad Left";
    std::string pad_ui_right = "Pad Right";
    std::string pad_ui_ok = "Pad Y";
    std::string pad_shoot = "Pad RT";
    std::string pad_scan_shoot = "Pad LT";
    std::string pad_beam = "Pad LB";
    std::string pad_missile = "Pad X";
    std::string pad_weapon1 = "None";
    std::string pad_weapon2 = "None";
    std::string pad_weapon3 = "None";
    std::string pad_weapon4 = "None";
    std::string pad_weapon5 = "None";
    std::string pad_weapon6 = "None";
    std::string pad_virtual_stylus = "None";
    std::string pad_menu = "Pad Start";
    // Persisted BIOS choice, psxrecomp-style: any one of the three retail
    // dump files (its folder is used at launch). Empty = the built-in
    // FreeBIOS + generated firmware.
    std::string bios_path;
    // beads-yjp.16 -- host-owned online identity. player_name is the DS
    // firmware console nickname the runner writes into its in-memory
    // firmware image (--player-name); it is what a game surfaces as the
    // player's default name and what WFC/Wiimmfi shows to peers. Edited on
    // the dashboard ONLINE card (GameInfo.has_player_name). Defaults to the
    // project identity (owner directive) on both boot paths; clearing the
    // field keeps the firmware's own name (a retail dump's real console
    // nickname, or the generated image's built-in default).
    std::string player_name = "ndsrecomp";
    // Where the runner will look for dumps and for generated-identity.bin
    // when bios_path is empty (the release's own bios folder). Captured once
    // at startup so the identity row can show the MAC without re-deriving
    // the launch-time path.
    std::filesystem::path default_bios_dir;
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

// Gamepad rows: the same actions, bound to pad buttons and passed to the
// runner as --mph-pad-bind-<action>. The runner id is this id without the
// "pad-" prefix.
constexpr std::array<BindingOption, 23> kPadBindingOptions{{
    {"pad-move-forward", "Move forward", "Gamepad",
        &ModState::pad_move_forward, "None"},
    {"pad-move-back", "Move back", "Gamepad",
        &ModState::pad_move_back, "None"},
    {"pad-move-left", "Move left", "Gamepad",
        &ModState::pad_move_left, "None"},
    {"pad-move-right", "Move right", "Gamepad",
        &ModState::pad_move_right, "None"},
    {"pad-jump", "Jump", "Gamepad",
        &ModState::pad_jump, "Pad A"},
    {"pad-morph-ball", "Morph ball", "Gamepad",
        &ModState::pad_morph_ball, "Pad B"},
    {"pad-boost-zoom", "Boost / zoom", "Gamepad",
        &ModState::pad_boost_zoom, "Pad RB"},
    {"pad-scan-visor", "Scan visor", "Gamepad",
        &ModState::pad_scan_visor, "Pad R3"},
    {"pad-ui-left", "UI left", "Gamepad",
        &ModState::pad_ui_left, "Pad Left"},
    {"pad-ui-right", "UI right", "Gamepad",
        &ModState::pad_ui_right, "Pad Right"},
    {"pad-ui-ok", "UI OK", "Gamepad",
        &ModState::pad_ui_ok, "Pad Y"},
    {"pad-shoot", "Shoot", "Gamepad",
        &ModState::pad_shoot, "Pad RT"},
    {"pad-scan-shoot", "Scan shoot", "Gamepad",
        &ModState::pad_scan_shoot, "Pad LT"},
    {"pad-beam", "Beam", "Gamepad",
        &ModState::pad_beam, "Pad LB"},
    {"pad-missile", "Missile", "Gamepad",
        &ModState::pad_missile, "Pad X"},
    {"pad-weapon1", "Subweapon 1", "Gamepad",
        &ModState::pad_weapon1, "None"},
    {"pad-weapon2", "Subweapon 2", "Gamepad",
        &ModState::pad_weapon2, "None"},
    {"pad-weapon3", "Subweapon 3", "Gamepad",
        &ModState::pad_weapon3, "None"},
    {"pad-weapon4", "Subweapon 4", "Gamepad",
        &ModState::pad_weapon4, "None"},
    {"pad-weapon5", "Subweapon 5", "Gamepad",
        &ModState::pad_weapon5, "None"},
    {"pad-weapon6", "Subweapon 6", "Gamepad",
        &ModState::pad_weapon6, "None"},
    {"pad-virtual-stylus", "Virtual stylus", "Gamepad",
        &ModState::pad_virtual_stylus, "None"},
    {"pad-menu", "Menu", "Gamepad",
        &ModState::pad_menu, "Pad Start"},
}};

constexpr std::array<BindingChoice, 17> kPadChoices{{
    {"None", "Unbound"},
    {"Pad A", "A"}, {"Pad B", "B"}, {"Pad X", "X"}, {"Pad Y", "Y"},
    {"Pad LB", "Left bumper"}, {"Pad RB", "Right bumper"},
    {"Pad LT", "Left trigger"}, {"Pad RT", "Right trigger"},
    {"Pad L3", "Left stick click"}, {"Pad R3", "Right stick click"},
    {"Pad Up", "D-pad up"}, {"Pad Down", "D-pad down"},
    {"Pad Left", "D-pad left"}, {"Pad Right", "D-pad right"},
    {"Pad Start", "Start"}, {"Pad Back", "Back / Select"},
}};

// EXACTLY the runner's nds_validate_player_name() rule set
// (runner/src/firmware_user_settings.cpp): 1..10 characters, letters,
// digits, spaces and a fixed punctuation set, no leading/trailing space.
// Duplicated rather than shared because the launcher links no runner code;
// if one side changes, change both. Nothing here truncates -- an invalid
// persisted value is dropped, never silently reshaped into a different name
// than the player asked for.
bool valid_player_name(const std::string& name) {
    static const char kExtraAllowed[] = " -_.,!?'()[]{}+=@#&*:;/";
    if (name.empty() || name.size() > 10) return false;
    if (name.front() == ' ' || name.back() == ' ') return false;
    for (const char c : name) {
        const unsigned char u = static_cast<unsigned char>(c);
        const bool alnum = (u >= '0' && u <= '9') ||
                           (u >= 'A' && u <= 'Z') || (u >= 'a' && u <= 'z');
        if (alnum) continue;
        if (c != '\0' && std::strchr(kExtraAllowed, c) != nullptr) continue;
        return false;
    }
    return true;
}

// Read-only console identity: the per-install MAC the runner generates and
// persists next to the BIOS dumps on the first no-dumps launch. Formatted
// for display only -- the launcher never edits it (a hand-typed MAC could
// be multicast, which is never a valid station address). Empty when the
// file does not exist yet, i.e. before the first generated-firmware launch,
// or when the player selected retail dumps (which carry their console's own
// real MAC and are left untouched, LLE-faithful).
std::filesystem::path bios_dir_from_setting(const char* setting);

std::string read_identity_mac(const std::filesystem::path& bios_dir) {
    std::ifstream file(bios_dir / "generated-identity.bin", std::ios::binary);
    if (!file) return {};
    unsigned char mac[6]{};
    file.read(reinterpret_cast<char*>(mac), sizeof(mac));
    if (file.gcount() != static_cast<std::streamsize>(sizeof(mac))) return {};
    char text[32];
    std::snprintf(text, sizeof(text), "%02X:%02X:%02X:%02X:%02X:%02X",
                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    return text;
}

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
        } else if (key == "bios_path") {
            state.bios_path = value;
        } else if (key == "player_name_override") {
            // Legacy key from the short-lived mods-page identity row;
            // ignored (the dashboard field's emptiness is the only gate).
        } else if (key == "player_name") {
            // A present-but-empty value is a deliberate clear (firmware
            // default), distinct from a missing key (the "ndsrecomp"
            // default). An unrepresentable value is dropped to empty, not
            // repaired: the runner would refuse it anyway, and a silently
            // altered name is worse than no name at all.
            state.player_name = valid_player_name(value) ? value
                                                         : std::string();
        } else if (key == "virtual_stylus_sensitivity") {
            saw_virtual_stylus_sensitivity = true;
            char* end = nullptr;
            const long parsed = std::strtol(value.c_str(), &end, 10);
            if (end && *end == '\0' && parsed >= 10 && parsed <= 400)
                state.virtual_stylus_sensitivity = static_cast<int>(parsed);
        } else if (key == "pad_aim_sensitivity") {
            char* end = nullptr;
            const long parsed = std::strtol(value.c_str(), &end, 10);
            if (end && *end == '\0' && parsed >= 10 && parsed <= 400)
                state.pad_aim_sensitivity = static_cast<int>(parsed);
        } else {
            for (const BindingOption& option : kBindingOptions) {
                if (key == option.id) {
                    state.*(option.member) = value;
                    break;
                }
            }
            for (const BindingOption& option : kPadBindingOptions) {
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
             << state.virtual_stylus_sensitivity << '\n'
             << "pad_aim_sensitivity=" << state.pad_aim_sensitivity << '\n'
             << "bios_path=" << state.bios_path << '\n'
             << "player_name=" << state.player_name << '\n';
        for (const BindingOption& option : kBindingOptions)
            file << option.id << "=" << state.*(option.member) << '\n';
        for (const BindingOption& option : kPadBindingOptions)
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

// The online identity is NOT a mod: it lives on the dashboard's ONLINE
// card (GameInfo.has_player_name + the NDS profile's "identity" panel),
// directly under the controller card. Only the two real gameplay mods
// remain here.
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
            4 + static_cast<int>(kBindingOptions.size()) +
            static_cast<int>(kPadBindingOptions.size());
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
    if (!context || !package_id || !feature_id || !output || index < 0)
        return 0;
    if (std::strcmp(package_id, "mph-prime-controls") != 0 ||
        std::strcmp(feature_id, "prime-controls") != 0 ||
        index >= 4 + static_cast<int>(kBindingOptions.size()) +
                     static_cast<int>(kPadBindingOptions.size())) {
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
    if (index == 3) {
        copy_text(output->id, "pad-aim-sensitivity");
        copy_text(output->label, "Pad aim sensitivity");
        copy_text(output->description,
                  "Multiplier for right-stick camera aim on a gamepad.");
        copy_text(output->group, "Gamepad");
        std::snprintf(output->value, sizeof(output->value), "%d",
                      state->pad_aim_sensitivity);
        copy_text(output->default_value, "100");
        output->type = RECOMP_MOD_OPTION_CHOICE;
        output->choice_count = static_cast<int>(kSensitivityChoices.size());
        return 1;
    }
    const bool pad_row =
        index >= 4 + static_cast<int>(kBindingOptions.size());
    const BindingOption& option = pad_row
        ? kPadBindingOptions[static_cast<size_t>(
              index - 4 - static_cast<int>(kBindingOptions.size()))]
        : kBindingOptions[static_cast<size_t>(index - 4)];
    copy_text(output->id, option.id);
    copy_text(output->label, option.label);
    copy_text(output->description,
              pad_row
                  ? "Gamepad button for this Prime Controls action."
                  : "Keyboard or mouse input for this Prime Controls "
                    "action.");
    copy_text(output->group, option.group);
    copy_text(output->value, (state->*(option.member)).c_str());
    copy_text(output->default_value, option.default_value);
    output->type = RECOMP_MOD_OPTION_CHOICE;
    output->choice_count = static_cast<int>(
        pad_row ? kPadChoices.size() : kBindingChoices.size());
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
         std::strcmp(option_id, "virtual-stylus-sensitivity") == 0 ||
         std::strcmp(option_id, "pad-aim-sensitivity") == 0);
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
    for (const BindingOption& option : kPadBindingOptions) {
        if (std::strcmp(option_id, option.id) != 0) continue;
        if (index >= static_cast<int>(kPadChoices.size())) return 0;
        std::memset(output, 0, sizeof(*output));
        const BindingChoice& choice = kPadChoices[index];
        copy_text(output->value, choice.value);
        copy_text(output->label, choice.label);
        return 1;
    }
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
    if (!context || !package_id || !feature_id || !option_id || !value)
        return 0;
    if (std::strcmp(package_id, "mph-prime-controls") != 0 ||
        std::strcmp(feature_id, "prime-controls") != 0) {
        return 0;
    }
    auto* state = static_cast<ModState*>(context);
    if (std::strcmp(option_id, "aim-sensitivity") == 0 ||
        std::strcmp(option_id, "virtual-stylus-sensitivity") == 0 ||
        std::strcmp(option_id, "pad-aim-sensitivity") == 0) {
        char* end = nullptr;
        const long parsed = std::strtol(value, &end, 10);
        if (!end || *end != '\0' || parsed < 10 || parsed > 400)
            return 0;
        if (std::strcmp(option_id, "aim-sensitivity") == 0)
            state->mouse_sensitivity = static_cast<int>(parsed);
        else if (std::strcmp(option_id, "virtual-stylus-sensitivity") == 0)
            state->virtual_stylus_sensitivity = static_cast<int>(parsed);
        else
            state->pad_aim_sensitivity = static_cast<int>(parsed);
        return 1;
    }
    if (std::strcmp(option_id, "invert-y") == 0) {
        if (std::strcmp(value, "true") == 0) state->mouse_invert_y = true;
        else if (std::strcmp(value, "false") == 0)
            state->mouse_invert_y = false;
        else return 0;
        return 1;
    }
    for (const BindingOption& option : kPadBindingOptions) {
        if (std::strcmp(option_id, option.id) != 0) continue;
        for (const BindingChoice& choice : kPadChoices) {
            if (std::strcmp(choice.value, value) == 0) {
                state->*(option.member) = value;
                return 1;
            }
        }
        return 0;
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

// ── BIOS handling, psxrecomp-style ─────────────────────────────────────
// The persisted BIOS setting names any ONE of the three retail dump files;
// its folder is what the runner receives. Empty = built-in FreeBIOS +
// generated firmware. No startup prompts: the choice lives in settings and
// the first-run wizard's BIOS row, and bios_verify explains each state.

struct NdsDump {
    const char* file;
    size_t size;
    const char* sha1;
};

constexpr std::array<NdsDump, 3> kNdsDumps{{
    {"biosnds9.rom", 4096, "bfaac75f101c135e32e2aaf541de6b1be4c8c62d"},
    {"biosnds7.rom", 16384, "24f67bdea115a2c847c8813a262502ee1607b7df"},
    {"firmware.bin", 262144, "ae22de59fbf3f35ccfbeacaeba6fa87ac5e7b14b"},
}};

std::filesystem::path bios_dir_from_setting(const char* setting) {
    if (!setting || !setting[0]) return {};
    std::error_code error;
    const std::filesystem::path picked(setting);
    if (std::filesystem::is_directory(picked, error)) return picked;
    return picked.parent_path();
}

// 0 = dump missing, 1 = verified, 2 = present but wrong size/hash.
int check_dump(const std::filesystem::path& dir, const NdsDump& dump) {
    std::ifstream file(dir / dump.file, std::ios::binary | std::ios::ate);
    if (!file.is_open()) return 0;
    const std::streamoff size = file.tellg();
    if (size != static_cast<std::streamoff>(dump.size)) return 2;
    std::vector<uint8_t> data(dump.size);
    file.seekg(0);
    if (!file.read(reinterpret_cast<char*>(data.data()),
                   static_cast<std::streamsize>(data.size()))) {
        return 2;
    }
    return gba::sha1(data.data(), data.size()).hex() == dump.sha1 ? 1 : 2;
}

int nds_bios_verify(const char* bios_path, RecompLauncherCBiosVerify* out) {
    if (!out) return 0;
    std::memset(out, 0, sizeof(*out));
    if (!bios_path || !bios_path[0]) {
        // Empty = the no-dump default; always launchable, like OpenBIOS.
        out->ok = 1;
        std::snprintf(out->detail, sizeof(out->detail),
                      "Using built-in FreeBIOS + generated firmware "
                      "(no dumps required).");
        return 1;
    }
    try {
        const std::filesystem::path dir = bios_dir_from_setting(bios_path);
        int missing = 0, mismatched = 0;
        for (const NdsDump& dump : kNdsDumps) {
            const int state = check_dump(dir, dump);
            if (state == 0) ++missing;
            if (state == 2) ++mismatched;
        }
        if (missing == 0 && mismatched == 0) {
            out->ok = 1;
            std::snprintf(out->detail, sizeof(out->detail),
                          "Retail BIOS + firmware dumps verified (SHA-1 ok).");
            return 1;
        }
        if (missing > 0) {
            std::snprintf(out->detail, sizeof(out->detail),
                          "Folder must contain biosnds9.rom, biosnds7.rom "
                          "and firmware.bin (%d missing). Clear the "
                          "selection to use FreeBIOS.", missing);
            return 1;
        }
        out->warn = 1;
        std::snprintf(out->detail, sizeof(out->detail),
                      "%d dump(s) fail SHA-1 verification; the game will "
                      "refuse to start. Clear the selection to use FreeBIOS.",
                      mismatched);
        return 1;
    } catch (...) {
        std::snprintf(out->detail, sizeof(out->detail),
                      "Could not read the selected BIOS folder.");
        return 1;
    }
}

int nds_persist_setup(void* context, const char* rom_path,
                      const char* bios_path) {
    (void)rom_path;
    if (!context) return 1;
    auto* state = static_cast<ModState*>(context);
    state->bios_path = bios_path ? bios_path : "";
    return save_mod_state(*state) ? 0 : 1;
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
    for (const BindingOption& option : kPadBindingOptions) {
        // Row id "pad-<action>" maps to --mph-pad-bind-<action>.
        std::wstring flag = L"--mph-pad-bind-";
        flag += widen(option.id + std::strlen("pad-"));
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
    const std::filesystem::path config = game_dir / "game.toml";
    if (!std::filesystem::is_regular_file(runner) ||
        !std::filesystem::is_regular_file(config)) {
        MessageBoxW(nullptr,
            L"The release is incomplete: nds_runner.exe or game.toml is "
            L"missing. Re-extract the full release ZIP.",
            L"Metroid Prime Hunters Recomp", MB_OK | MB_ICONERROR);
        return false;
    }

    // BIOS selection is a persisted setting (psxrecomp model), never a
    // launch-time prompt. A configured folder means the retail dumps; an
    // empty setting means the built-in FreeBIOS + generated firmware —
    // unless the release's own bios folder already holds all three dumps
    // (the pre-settings convention), which keeps existing installs on the
    // faithful path without reconfiguration.
    std::filesystem::path bios = bios_dir_from_setting(
        mods.bios_path.c_str());
    bool no_dumps_mode = false;
    if (bios.empty()) {
        bios = game_dir / "bios";
        bool conventional_dumps = true;
        for (const NdsDump& dump : kNdsDumps) {
            if (!std::filesystem::is_regular_file(bios / dump.file))
                conventional_dumps = false;
        }
        if (!conventional_dumps) {
            no_dumps_mode = true;
            // The bios folder still hosts the persisted per-install identity.
            std::error_code error;
            std::filesystem::create_directories(bios, error);
        }
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
        L" --mph-pad-aim-sensitivity " +
        std::to_wstring(mods.pad_aim_sensitivity) +
        L" --startup-mode automatic" +
        // The runner's own default keeps networking OFF (probe/CI safety);
        // a player launching through the UI expects Nintendo WFC to work,
        // so the launcher turns it on and points it at Wiimmfi.
        L" --network on --wfc on --wfc-provider wiimmfi";
    // beads-yjp.16: the firmware console nickname. Passed only when the
    // player both configured a name and left the identity feature on;
    // otherwise the runner leaves the firmware's own name alone (a retail
    // dump keeps its console's real nickname, a generated image keeps
    // "ndsrecomp"). Re-validated here so a hand-edited mods.ini can never
    // hand the runner a name it will refuse to start on.
    if (valid_player_name(mods.player_name))
        append_arg(command, L"--player-name", widen(mods.player_name.c_str()));
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
    const std::filesystem::path exe = std::filesystem::weakly_canonical(
        std::filesystem::absolute(argv[0])).parent_path();
    ModState mod_state{};
    mod_state.settings_path = mod_settings_path();
    mod_state.default_bios_dir = exe / "bios";
    load_mod_state(mod_state);
    RecompLauncherCModProvider mod_provider = make_mod_provider(&mod_state);
    copy_text(settings.bios_path, mod_state.bios_path.c_str());
    copy_text(settings.player_name, mod_state.player_name.c_str());

    // Read-only identity detail for the dashboard ONLINE card. Captured once
    // at startup: the MAC only changes on the first-ever no-dump launch.
    const std::string identity_mac = read_identity_mac(
        mod_state.bios_path.empty()
            ? mod_state.default_bios_dir
            : bios_dir_from_setting(mod_state.bios_path.c_str()));
    const std::string identity_detail =
        !identity_mac.empty()
            ? "Console MAC: " + identity_mac + " (generated identity)"
            : std::string("Console MAC: from the firmware dump, or created "
                          "on the first no-dump launch.");

    RecompLauncherCGameInfo game{};
    launcher_profile_apply("nds", &game);
    // MPH has Nintendo WFC online play, so it opts into the dashboard
    // ONLINE identity card (most DS titles never set this).
    game.has_player_name = 1;
    game.identity_detail = identity_detail.c_str();
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
    game.bios_verify = nds_bios_verify;
    game.persist_setup = nds_persist_setup;
    game.persist_setup_ctx = &mod_state;

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
    // The UI's final BIOS selection is authoritative for this launch even if
    // a persist callback was missed (persistence is best-effort UX).
    mod_state.bios_path = settings.bios_path;
    // Same for the ONLINE card's player name. An invalid entry is surfaced
    // and dropped rather than silently reshaped or allowed to block launch.
    {
        const std::string typed = settings.player_name;
        if (!typed.empty() && !valid_player_name(typed)) {
            MessageBoxW(nullptr,
                L"The player name must be 1-10 characters: letters, digits, "
                L"spaces, and common punctuation. Launching with the default "
                L"name instead.",
                L"Metroid Prime Hunters Recomp",
                MB_OK | MB_ICONINFORMATION);
            mod_state.player_name.clear();
        } else {
            mod_state.player_name = typed;
        }
        save_mod_state(mod_state);
    }
    return launch_runner(exe, selected_rom, settings.display_layout,
                         mod_state.adaptive_widescreen,
                         mod_state,
                         settings.supersampling,
                         settings.antialiasing) ? 0 : 3;
}
#endif
