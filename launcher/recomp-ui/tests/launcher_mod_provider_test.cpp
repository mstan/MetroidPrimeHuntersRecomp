#include <cstring>
#include <cstdio>

#include "../launcher_main.cpp"

namespace {

bool require(bool condition, const char* label) {
    if (!condition) std::fprintf(stderr, "failed: %s\n", label);
    return condition;
}

}  // namespace

int main() {
    if (!require(std::strcmp(runner_screen_layout_arg(0), "stacked") == 0,
                 "stacked layout arg")) return 88;
    if (!require(std::strcmp(runner_screen_layout_arg(1), "separate") == 0,
                 "separate layout arg")) return 89;
    if (!require(std::strcmp(runner_fullscreen_arg(0), "off") == 0,
                 "fullscreen off arg")) return 90;
    if (!require(std::strcmp(runner_fullscreen_arg(1), "borderless") == 0,
                 "fullscreen borderless arg")) return 91;
    if (!require(std::strcmp(runner_fullscreen_arg(2), "exclusive") == 0,
                 "fullscreen exclusive arg")) return 92;
    if (!require(std::strcmp(runner_fullscreen_arg(99), "off") == 0,
                 "fullscreen invalid clamps to off")) return 93;
    if (!require(renderer_type_to_settings_index("auto") == 0,
                 "renderer auto settings index")) return 141;
    if (!require(renderer_type_to_settings_index("compute") == 1,
                 "renderer compute settings index")) return 142;
    if (!require(renderer_type_to_settings_index("soft") == 2,
                 "renderer software settings index")) return 143;
    if (!require(renderer_type_to_settings_index("vulkan") == 1,
                 "invalid renderer settings index defaults")) return 144;
    if (!require(std::strcmp(settings_index_to_renderer_type(1),
                             "compute") == 0,
                 "settings index compute renderer")) return 145;
    if (!require(std::strcmp(settings_index_to_renderer_type(99),
                             "compute") == 0,
                 "invalid settings index renderer defaults")) return 146;

    {
        const std::filesystem::path root =
            std::filesystem::temp_directory_path() /
            "mph_firmware_state_launcher_test";
        const std::filesystem::path settings = root / "mods.ini";
        const std::filesystem::path generated =
            firmware_state_path(settings, true);
        const std::filesystem::path retail =
            firmware_state_path(settings, false);
        if (!require(generated.filename() == "firmware-generated.bin",
                     "generated firmware state path")) return 85;
        if (!require(retail.filename() == "firmware-retail.bin",
                     "retail firmware state path")) return 86;
        if (!require(diagnostics_dir_path(root / "release") ==
                         root / "release" / "diagnostics",
                     "diagnostics path is release-adjacent")) return 150;
        std::filesystem::create_directories(root);
        std::vector<unsigned char> bytes(128u * 1024u, 0xFFu);
        const unsigned char mac[6] = {0x00, 0x09, 0xBF, 0x12, 0x34, 0x56};
        std::memcpy(bytes.data() + 0x36, mac, sizeof(mac));
        {
            std::ofstream file(generated, std::ios::binary);
            file.write(reinterpret_cast<const char*>(bytes.data()),
                       static_cast<std::streamsize>(bytes.size()));
        }
        if (!require(read_firmware_state_mac(generated) ==
                         "00:09:BF:12:34:56",
                     "firmware state identity display")) return 87;
        std::filesystem::remove_all(root);
    }

    {
        ModState legacy_state{};
        legacy_state.settings_path =
            std::filesystem::temp_directory_path() /
            "mph_mod_provider_legacy_settings.ini";
        {
            std::ofstream file(legacy_state.settings_path);
            file << "prime_controls=true\n"
                    "mouse_sensitivity=100\n"
                    "virtual_stylus_sensitivity=100\n";
        }
        load_mod_state(legacy_state);
        std::filesystem::remove(legacy_state.settings_path);
        if (!require(legacy_state.mouse_sensitivity == 13,
                     "legacy aim sensitivity migration")) {
            return 1;
        }
        if (!require(legacy_state.virtual_stylus_sensitivity == 20,
                     "legacy virtual stylus migration")) {
            return 2;
        }
    }

    ModState state{};
    RecompLauncherCModProvider provider = make_mod_provider(&state);

    if (!require(provider.feature_count != nullptr, "feature_count callback"))
        return 3;
    // Gameplay mods plus diagnostics; the online identity is a dashboard
    // card, not a mod. Index 1 stays prime controls so the assertions below
    // are unaffected by HD rendering being added at index 2.
    const int feature_count = provider.feature_count(provider.ctx);
    if (!require(feature_count == 5, "feature_count == 5")) return 4;

    RecompLauncherCModFeature feature{};
    if (!require(provider.feature_get(provider.ctx, 0, &feature),
                 "feature_get widescreen")) {
        return 3;
    }
    if (!require(std::strcmp(feature.id, "widescreen") == 0,
                 "widescreen feature id")) {
        return 4;
    }
    if (!require(std::strcmp(feature.package_id, "mph-widescreen") == 0,
                 "widescreen package id")) {
        return 4;
    }
    if (!require(std::strcmp(feature.name, "Widescreen") == 0,
                 "widescreen feature name")) {
        return 4;
    }
    if (!require(feature.option_count == 1,
                 "widescreen has mode option")) {
        return 4;
    }
    if (!require(!provider.feature_set_option(
            provider.ctx, "mph-widescreen", "widescreen",
            "renderer-type", "soft"),
            "widescreen rejects renderer type option")) {
        return 4;
    }
    RecompLauncherCModOption widescreen_option{};
    if (!require(provider.feature_option_get(
            provider.ctx, "mph-widescreen", "widescreen", 0,
            &widescreen_option), "widescreen mode option get")) {
        return 4;
    }
    if (!require(std::strcmp(widescreen_option.id, "widescreen-mode") == 0,
                 "widescreen mode option id")) return 4;
    if (!require(std::strcmp(widescreen_option.value, "adaptive") == 0,
                 "widescreen mode default value")) return 4;
    if (!require(widescreen_option.choice_count == 5,
                 "widescreen mode choice count")) return 4;
    RecompLauncherCModChoice widescreen_choice{};
    if (!require(provider.feature_choice_get(
            provider.ctx, "mph-widescreen", "widescreen",
            "widescreen-mode", 0, &widescreen_choice),
            "widescreen dynamic choice get")) return 4;
    if (!require(std::strcmp(widescreen_choice.label, "Dynamic") == 0,
                 "widescreen dynamic choice label")) return 4;
    if (!require(provider.feature_choice_get(
            provider.ctx, "mph-widescreen", "widescreen",
            "widescreen-mode", 2, &widescreen_choice),
            "widescreen 5:3 choice get")) return 4;
    if (!require(std::strcmp(widescreen_choice.value, "fixed-5-3") == 0,
                 "widescreen 5:3 choice value")) return 4;
    if (!require(provider.feature_set_option(
            provider.ctx, "mph-widescreen", "widescreen",
            "widescreen-mode", "fixed-5-3"),
            "widescreen mode set")) return 4;
    if (!require(state.widescreen_mode == "fixed-5-3",
                 "widescreen mode state set")) return 4;
    if (!require(runner_widescreen_width_arg(state) == 320,
                 "widescreen fixed 5:3 launch width")) return 4;
    if (!require(provider.feature_enable(
            provider.ctx, "mph-widescreen", "widescreen", 0),
            "disable widescreen")) return 4;
    if (!require(runner_widescreen_width_arg(state) == 0,
                 "disabled widescreen has no width")) return 4;
    if (!require(provider.feature_enable(
            provider.ctx, "mph-adaptive-widescreen", "adaptive-widescreen", 1),
            "legacy widescreen package enables")) return 4;

    feature = {};
    if (!require(provider.feature_get(provider.ctx, 1, &feature),
                 "feature_get prime controls")) {
        return 3;
    }
    if (!require(std::strcmp(feature.id, "prime-controls") == 0,
                 "feature id")) {
        return 4;
    }
    if (!require(std::strcmp(feature.package_id,
                             "mph-prime-controls") == 0,
                 "feature package id")) {
        return 5;
    }
    if (!require(feature.enabled == 1, "feature enabled default")) return 6;
    if (!require(feature.option_count == 51, "feature option count")) return 7;

    feature = {};
    if (!require(provider.feature_get(provider.ctx, 3, &feature),
                 "feature_get diagnostics")) {
        return 7;
    }
    if (!require(std::strcmp(feature.id, "diagnostics") == 0,
                 "diagnostics feature id")) return 7;
    if (!require(std::strcmp(feature.package_id, "mph-diagnostics") == 0,
                 "diagnostics package id")) return 7;
    if (!require(feature.enabled == 1, "diagnostics default enabled"))
        return 7;
    if (!require(provider.feature_enable(
            provider.ctx, "mph-diagnostics", "diagnostics", 0),
            "disable diagnostics")) {
        return 7;
    }
    feature = {};
    if (!require(provider.feature_get(provider.ctx, 3, &feature),
                 "feature_get diagnostics disabled")) {
        return 7;
    }
    if (!require(feature.enabled == 0, "diagnostics disabled")) return 7;

    RecompLauncherCModOption option{};
    option = {};
    if (!require(provider.feature_option_get(
            provider.ctx, "mph-prime-controls", "prime-controls", 0,
            &option), "aim sensitivity option get")) {
        return 8;
    }
    if (!require(std::strcmp(option.id, "aim-sensitivity") == 0,
                 "aim sensitivity option id")) return 9;
    if (!require(std::strcmp(option.value, "13") == 0,
                 "aim sensitivity default value")) return 10;
    if (!require(std::strcmp(option.default_value, "13") == 0,
                 "aim sensitivity declared default")) return 11;
    if (!require(option.choice_count == 12,
                 "aim sensitivity choice count")) return 12;

    option = {};
    if (!require(provider.feature_option_get(
            provider.ctx, "mph-prime-controls", "prime-controls", 1,
            &option), "invert-y option get")) {
        return 11;
    }
    if (!require(std::strcmp(option.id, "invert-y") == 0,
                 "invert-y option id")) return 12;
    if (!require(option.type == RECOMP_MOD_OPTION_BOOLEAN,
                 "invert-y boolean type")) return 13;

    option = {};
    if (!require(provider.feature_option_get(
            provider.ctx, "mph-prime-controls", "prime-controls", 2,
            &option), "cross-window mouse capture option get")) {
        return 14;
    }
    if (!require(std::strcmp(option.id,
                             "cross-window-mouse-capture") == 0,
                 "cross-window mouse capture option id")) return 14;
    if (!require(std::strcmp(option.value, "false") == 0,
                 "cross-window mouse capture default value")) return 14;
    if (!require(option.type == RECOMP_MOD_OPTION_BOOLEAN,
                 "cross-window mouse capture boolean type")) return 14;
    if (!require(provider.feature_set_option(
            provider.ctx, "mph-prime-controls", "prime-controls",
            "cross-window-mouse-capture", "true"),
            "set cross-window mouse capture")) {
        return 14;
    }

    option = {};
    if (!require(provider.feature_option_get(
            provider.ctx, "mph-prime-controls", "prime-controls", 4,
            &option), "pad aim sensitivity option get")) {
        return 14;
    }
    if (!require(std::strcmp(option.id, "pad-aim-sensitivity") == 0,
                 "pad aim sensitivity option id")) return 14;
    if (!require(std::strcmp(option.value, "100") == 0,
                 "pad aim sensitivity default value")) return 14;
    if (!require(std::strcmp(option.default_value, "100") == 0,
                 "pad aim sensitivity declared default")) return 14;
    if (!require(option.choice_count == 12,
                 "pad aim sensitivity choice count")) return 14;
    if (!require(provider.feature_set_option(
            provider.ctx, "mph-prime-controls", "prime-controls",
            "pad-aim-sensitivity", "150"), "set pad aim sensitivity"))
        return 14;
    if (!require(!provider.feature_set_option(
            provider.ctx, "mph-prime-controls", "prime-controls",
            "pad-aim-sensitivity", "5"),
                 "reject out-of-range pad aim sensitivity"))
        return 14;

    option = {};
    if (!require(provider.feature_option_get(
            provider.ctx, "mph-prime-controls", "prime-controls", 5,
            &option), "move-forward option get")) {
        return 14;
    }
    if (!require(std::strcmp(option.id, "move-forward") == 0,
                 "move-forward option id")) return 15;
    if (!require(std::strcmp(option.value, "W") == 0,
                 "move-forward default value")) return 16;
    if (!require(std::strcmp(option.default_value, "W") == 0,
                 "move-forward declared default")) return 17;
    if (!require(option.type == RECOMP_MOD_OPTION_CHOICE,
                 "move-forward choice type")) return 18;
    if (!require(option.choice_count == 29,
                 "move-forward choice count")) return 19;

    option = {};
    if (!require(provider.feature_option_get(
            provider.ctx, "mph-prime-controls", "prime-controls", 3,
            &option), "virtual stylus sensitivity option get default")) {
        return 20;
    }
    if (!require(std::strcmp(option.value, "20") == 0,
                 "virtual stylus sensitivity default value")) return 21;
    if (!require(std::strcmp(option.default_value, "20") == 0,
                 "virtual stylus sensitivity declared default")) return 22;

    RecompLauncherCModChoice choice{};
    if (!require(provider.feature_choice_get(
            provider.ctx, "mph-prime-controls", "prime-controls",
            "move-forward", 21, &choice), "choice get Right Shift")) {
        return 20;
    }
    if (!require(std::strcmp(choice.value, "Right Shift") == 0,
                 "choice value Right Shift")) return 21;

    if (!require(provider.feature_set_option(
            provider.ctx, "mph-prime-controls", "prime-controls",
            "move-forward", "Right Shift"), "set move-forward")) {
        return 22;
    }
    option = {};
    if (!require(provider.feature_option_get(
            provider.ctx, "mph-prime-controls", "prime-controls", 5,
            &option), "move-forward option get after set")) {
        return 23;
    }
    if (!require(std::strcmp(option.value, "Right Shift") == 0,
                 "move-forward mutated value")) return 24;

    if (!require(!provider.feature_set_option(
            provider.ctx, "mph-prime-controls", "prime-controls",
            "move-forward", "Unknown Key"), "reject unknown binding")) {
        return 25;
    }
    option = {};
    if (!require(provider.feature_option_get(
            provider.ctx, "mph-prime-controls", "prime-controls", 5,
            &option), "move-forward option get after reject")) {
        return 26;
    }
    if (!require(std::strcmp(option.value, "Right Shift") == 0,
                 "move-forward unchanged after reject")) return 27;

    // Gamepad rows follow the keyboard rows: index 28 = pad-move-forward,
    // 35 = pad-scan-visor (defaults None and Pad R3 respectively).
    option = {};
    if (!require(provider.feature_option_get(
            provider.ctx, "mph-prime-controls", "prime-controls", 28,
            &option), "pad-move-forward option get")) {
        return 28;
    }
    if (!require(std::strcmp(option.id, "pad-move-forward") == 0,
                 "pad-move-forward option id")) return 28;
    if (!require(std::strcmp(option.value, "None") == 0,
                 "pad-move-forward default value")) return 28;
    if (!require(option.choice_count == 17,
                 "pad option choice count")) return 28;
    option = {};
    if (!require(provider.feature_option_get(
            provider.ctx, "mph-prime-controls", "prime-controls", 35,
            &option), "pad-scan-visor option get")) {
        return 28;
    }
    if (!require(std::strcmp(option.id, "pad-scan-visor") == 0,
                 "pad-scan-visor option id")) return 28;
    if (!require(std::strcmp(option.value, "Pad R3") == 0,
                 "pad-scan-visor default value")) return 28;
    if (!require(provider.feature_set_option(
            provider.ctx, "mph-prime-controls", "prime-controls",
            "pad-scan-visor", "Pad L3"), "set pad-scan-visor")) return 28;
    if (!require(!provider.feature_set_option(
            provider.ctx, "mph-prime-controls", "prime-controls",
            "pad-scan-visor", "Mouse Left"),
                 "reject keyboard value on pad row")) return 28;
    RecompLauncherCModChoice pad_choice{};
    if (!require(provider.feature_choice_get(
            provider.ctx, "mph-prime-controls", "prime-controls",
            "pad-scan-visor", 10, &pad_choice),
                 "pad choice get R3")) return 28;
    if (!require(std::strcmp(pad_choice.value, "Pad R3") == 0,
                 "pad choice value R3")) return 28;

    if (!require(provider.feature_set_option(
            provider.ctx, "mph-prime-controls", "prime-controls",
            "aim-sensitivity", "125"), "set aim sensitivity")) {
        return 28;
    }
    option = {};
    if (!require(provider.feature_option_get(
            provider.ctx, "mph-prime-controls", "prime-controls", 0,
            &option), "aim sensitivity option get after set")) {
        return 29;
    }
    if (!require(std::strcmp(option.value, "125") == 0,
                 "aim sensitivity mutated value")) return 30;

    if (!require(provider.feature_set_option(
            provider.ctx, "mph-prime-controls", "prime-controls",
            "invert-y", "true"), "set invert-y")) {
        return 31;
    }
    option = {};
    if (!require(provider.feature_option_get(
            provider.ctx, "mph-prime-controls", "prime-controls", 1,
            &option), "invert-y option get after set")) {
        return 32;
    }
    if (!require(std::strcmp(option.value, "true") == 0,
                 "invert-y mutated value")) return 33;

    if (!require(provider.feature_set_option(
            provider.ctx, "mph-prime-controls", "prime-controls",
            "virtual-stylus-sensitivity", "150"),
            "set virtual stylus sensitivity")) {
        return 34;
    }
    option = {};
    if (!require(provider.feature_option_get(
            provider.ctx, "mph-prime-controls", "prime-controls", 3,
            &option), "virtual stylus sensitivity option get")) {
        return 35;
    }
    if (!require(std::strcmp(option.value, "150") == 0,
                 "virtual stylus sensitivity mutated value")) return 36;

    // The online identity is NOT a mod feature: it lives on the dashboard
    // ONLINE card (GameInfo.has_player_name + the NDS "identity" panel).
    // Five Mods-page features remain; index 5 must not resolve.
    if (!require(!provider.feature_get(provider.ctx, 5, &feature),
                 "exactly five mod features (identity is not a mod)")) {
        return 37;
    }

    // Same rule set as the runner's nds_validate_player_name().
    if (!require(valid_player_name("Samus"), "plain name valid")) return 48;
    if (!require(valid_player_name("0123456789"), "10 chars valid")) return 49;
    if (!require(!valid_player_name("01234567890"),
                 "11 chars rejected, never truncated")) return 50;
    if (!require(!valid_player_name(""), "empty rejected")) return 51;
    if (!require(!valid_player_name(" x"), "leading space rejected")) {
        return 52;
    }
    if (!require(!valid_player_name("x "), "trailing space rejected")) {
        return 53;
    }
    if (!require(!valid_player_name("a\"b"), "quote rejected")) return 54;
    if (!require(!valid_player_name("\xc3\xa9"), "non-ASCII rejected")) {
        return 55;
    }

    // mods.ini round trip, plus the rule that an invalid persisted name is
    // DROPPED rather than repaired into a different name.
    {
        ModState saved{};
        saved.settings_path = std::filesystem::temp_directory_path() /
                              "mph_mod_provider_identity_settings.ini";
        saved.player_name = "Samus";
        if (!require(save_mod_state(saved), "identity save")) return 56;
        ModState loaded{};
        loaded.settings_path = saved.settings_path;
        load_mod_state(loaded);
        if (!require(loaded.player_name == "Samus",
                     "identity name round trip")) return 57;

        {
            std::ofstream file(saved.settings_path, std::ios::trunc);
            file << "player_name=this name is far too long\n";
        }
        ModState bad{};
        bad.settings_path = saved.settings_path;
        load_mod_state(bad);
        if (!require(bad.player_name.empty(),
                     "invalid persisted name dropped, not truncated")) {
            return 59;
        }
        std::filesystem::remove(saved.settings_path);
    }

    // Full Mods-page persistence sweep: all feature toggles, all scalar
    // options, and every keyboard/mouse + gamepad binding row.
    {
        ModState saved{};
        saved.settings_path =
            std::filesystem::temp_directory_path() /
            "mph_mod_provider_all_mod_settings.ini";
        saved.adaptive_widescreen = false;
        saved.widescreen_mode = "fixed-5-3";
        saved.hd_rendering = true;
        saved.internal_resolution = 4;
        saved.texture_upscale = 4;
        saved.prime_controls = false;
        saved.frame_interpolation = true;
        saved.diagnostics = false;
        saved.renderer_type = "soft";
        saved.mouse_sensitivity = 200;
        saved.mouse_invert_y = true;
        saved.cross_window_mouse_capture = true;
        saved.virtual_stylus_sensitivity = 300;
        saved.pad_aim_sensitivity = 150;

        for (size_t i = 0; i < kBindingOptions.size(); ++i) {
            const BindingChoice& choice =
                kBindingChoices[(i % (kBindingChoices.size() - 1)) + 1];
            saved.*(kBindingOptions[i].member) = choice.value;
        }
        for (size_t i = 0; i < kPadBindingOptions.size(); ++i) {
            const BindingChoice& choice =
                kPadChoices[(i % (kPadChoices.size() - 1)) + 1];
            saved.*(kPadBindingOptions[i].member) = choice.value;
        }

        if (!require(save_mod_state(saved), "all mod settings save"))
            return 128;
        ModState loaded{};
        loaded.settings_path = saved.settings_path;
        load_mod_state(loaded);
        if (!require(!loaded.adaptive_widescreen,
                     "adaptive widescreen round trip")) return 129;
        if (!require(loaded.widescreen_mode == "fixed-5-3",
                     "widescreen mode round trip")) return 129;
        if (!require(loaded.hd_rendering,
                     "hd rendering feature round trip")) return 130;
        if (!require(loaded.internal_resolution == 4,
                     "all-mod internal resolution round trip")) return 131;
        if (!require(loaded.texture_upscale == 4,
                     "all-mod texture upscale round trip")) return 132;
        if (!require(!loaded.prime_controls,
                     "prime controls feature round trip")) return 133;
        if (!require(loaded.frame_interpolation,
                     "frame interpolation feature round trip")) return 133;
        if (!require(!loaded.diagnostics,
                     "diagnostics feature round trip")) return 133;
        if (!require(loaded.renderer_type == "soft",
                     "renderer type round trip")) return 133;
        if (!require(std::strcmp(runner_renderer_policy_arg(loaded),
                                 "soft") == 0,
                     "renderer type launch env round trip")) return 133;
        if (!require(!loaded.mouse_aim,
                     "mouse aim mirrors prime controls on load")) return 134;
        if (!require(loaded.mouse_sensitivity == 200,
                     "aim sensitivity round trip")) return 135;
        if (!require(loaded.mouse_invert_y,
                     "invert y round trip")) return 136;
        if (!require(loaded.cross_window_mouse_capture,
                     "cross-window mouse capture round trip")) return 136;
        if (!require(loaded.virtual_stylus_sensitivity == 300,
                     "virtual stylus sensitivity round trip")) return 137;
        if (!require(loaded.pad_aim_sensitivity == 150,
                     "pad aim sensitivity round trip")) return 138;

        for (size_t i = 0; i < kBindingOptions.size(); ++i) {
            if (!require(loaded.*(kBindingOptions[i].member) ==
                             saved.*(kBindingOptions[i].member),
                         kBindingOptions[i].id)) {
                return 139;
            }
        }
        for (size_t i = 0; i < kPadBindingOptions.size(); ++i) {
            if (!require(loaded.*(kPadBindingOptions[i].member) ==
                             saved.*(kPadBindingOptions[i].member),
                         kPadBindingOptions[i].id)) {
                return 140;
            }
        }

        std::filesystem::remove(saved.settings_path);
    }

    // HD rendering: off by default, so a player who never opens the Mods
    // page gets the faithful native output.
    {
        RecompLauncherCModFeature hd{};
        if (!require(provider.feature_get(provider.ctx, 2, &hd),
                     "feature_get hd rendering")) return 60;
        if (!require(std::strcmp(hd.id, "hd-rendering") == 0,
                     "hd feature id")) return 61;
        if (!require(std::strcmp(hd.package_id, "mph-hd-rendering") == 0,
                     "hd package id")) return 62;
        if (!require(hd.enabled == 0, "hd disabled by default")) return 63;
        if (!require(hd.option_count == 2, "hd option count")) return 64;

        // Both options must reject values outside their choice list, so a
        // hand-edited mods.ini cannot hand the runner a scale it refuses.
        if (!require(provider.feature_set_option(
                         provider.ctx, "mph-hd-rendering", "hd-rendering",
                         "internal-resolution", "4") == 1,
                     "hd internal resolution accepts 4")) return 65;
        if (!require(provider.feature_set_option(
                         provider.ctx, "mph-hd-rendering", "hd-rendering",
                         "internal-resolution", "8") == 0,
                     "hd internal resolution rejects 8")) return 66;
        if (!require(provider.feature_set_option(
                         provider.ctx, "mph-hd-rendering", "hd-rendering",
                         "texture-upscale", "3") == 0,
                     "hd texture upscale rejects 3")) return 67;
        if (!require(provider.feature_set_option(
                         provider.ctx, "mph-hd-rendering", "hd-rendering",
                         "texture-upscale", "4") == 1,
                     "hd texture upscale accepts 4")) return 68;

        ModState hd_saved{};
        hd_saved.settings_path =
            std::filesystem::temp_directory_path() /
            "mph_mod_provider_hd_settings.ini";
        hd_saved.hd_rendering = true;
        hd_saved.internal_resolution = 3;
        hd_saved.texture_upscale = 4;
        if (!require(save_mod_state(hd_saved), "hd save")) return 69;
        ModState hd_loaded{};
        hd_loaded.settings_path = hd_saved.settings_path;
        load_mod_state(hd_loaded);
        if (!require(hd_loaded.hd_rendering, "hd enable round trip"))
            return 70;
        if (!require(hd_loaded.internal_resolution == 3,
                     "hd internal resolution round trip")) return 71;
        if (!require(hd_loaded.texture_upscale == 4,
                     "hd texture upscale round trip")) return 72;
        std::filesystem::remove(hd_saved.settings_path);
    }

    // Frame interpolation: off by default, so a player who never opens the
    // Mods page gets the untouched 60 Hz frame train.
    {
        RecompLauncherCModFeature fi{};
        if (!require(provider.feature_get(provider.ctx, 4, &fi),
                     "feature_get frame interpolation")) return 73;
        if (!require(std::strcmp(fi.id, "frame-interpolation") == 0,
                     "frame interpolation feature id")) return 74;
        if (!require(
                std::strcmp(fi.package_id, "mph-frame-interpolation") == 0,
                "frame interpolation package id")) return 75;
        if (!require(fi.enabled == 0,
                     "frame interpolation disabled by default")) return 76;
        if (!require(fi.option_count == 0,
                     "frame interpolation is a bare toggle")) return 77;

        if (!require(provider.feature_enable(
                         provider.ctx, "mph-frame-interpolation",
                         "frame-interpolation", 1) == 1,
                     "enable frame interpolation")) return 78;
        if (!require(provider.feature_get(provider.ctx, 4, &fi),
                     "feature_get frame interpolation enabled")) return 79;
        if (!require(fi.enabled == 1, "frame interpolation enabled"))
            return 80;
        if (!require(provider.feature_enable(
                         provider.ctx, "mph-frame-interpolation",
                         "frame-interpolation", 0) == 1,
                     "disable frame interpolation")) return 81;

        ModState fi_saved{};
        fi_saved.settings_path =
            std::filesystem::temp_directory_path() /
            "mph_mod_provider_frame_interpolation_settings.ini";
        fi_saved.frame_interpolation = true;
        if (!require(save_mod_state(fi_saved), "frame interpolation save"))
            return 82;
        ModState fi_loaded{};
        fi_loaded.settings_path = fi_saved.settings_path;
        load_mod_state(fi_loaded);
        if (!require(fi_loaded.frame_interpolation,
                     "frame interpolation enable round trip")) return 83;

        // A hand-edited mods.ini with a value that is neither true nor
        // false must keep the safe default rather than read as an enable.
        {
            std::ofstream bad(fi_saved.settings_path, std::ios::trunc);
            bad << "frame_interpolation=blend\n";
        }
        ModState fi_bad{};
        fi_bad.settings_path = fi_saved.settings_path;
        load_mod_state(fi_bad);
        if (!require(!fi_bad.frame_interpolation,
                     "frame interpolation rejects non-boolean")) return 84;
        std::filesystem::remove(fi_saved.settings_path);
    }

    // Issue #14 follow-up: every setting MPH exposes through the shared
    // launcher must survive a launcher restart, not just the two launch
    // arguments that were originally fixed.
    {
        const std::filesystem::path settings_path =
            std::filesystem::temp_directory_path() /
            "mph_mod_provider_launcher_settings.ini";

        ModState saved{};
        saved.settings_path = settings_path;
        saved.window_scale = 5;
        saved.display_layout = 0;
        saved.fullscreen = 2;
        saved.supersampling = 4;
        saved.antialiasing = 8;
        saved.renderer_type = "compute";
        saved.volume = 35;
        saved.player_src = 1;
        saved.player_gamepad_guid = "030000005e0400008e02000014010000";
        if (!require(save_mod_state(saved), "launcher settings save"))
            return 94;

        ModState loaded{};
        loaded.settings_path = settings_path;
        load_mod_state(loaded);
        if (!require(loaded.window_scale == 5,
                     "window scale round trip")) return 101;
        if (!require(loaded.display_layout == 0,
                     "display layout round trip")) return 95;
        if (!require(loaded.fullscreen == 2,
                     "fullscreen round trip")) return 96;
        if (!require(loaded.supersampling == 4,
                     "supersampling round trip")) return 102;
        if (!require(loaded.antialiasing == 8,
                     "antialiasing round trip")) return 103;
        if (!require(loaded.renderer_type == "compute",
                     "renderer type launcher round trip")) return 147;
        if (!require(loaded.volume == 35,
                     "volume round trip")) return 104;
        if (!require(loaded.player_src == 1,
                     "player source round trip")) return 105;
        if (!require(loaded.player_gamepad_guid ==
                         "030000005e0400008e02000014010000",
                     "player gamepad guid round trip")) return 106;

        RecompLauncherCSettings applied{};
        applied.window_scale = 3;
        applied.display_layout = 1;
        applied.fullscreen = 0;
        applied.supersampling = 1;
        applied.antialiasing = 0;
        applied.renderer = 0;
        applied.volume = 100;
        applied.player_src[0] = 2;
        apply_saved_launcher_settings(loaded, &applied);
        if (!require(applied.window_scale == 5,
                     "saved window scale applied")) return 107;
        if (!require(applied.display_layout == 0,
                     "saved display layout applied")) return 108;
        if (!require(applied.fullscreen == 2,
                     "saved fullscreen applied")) return 109;
        if (!require(applied.supersampling == 4,
                     "saved supersampling applied")) return 110;
        if (!require(applied.antialiasing == 8,
                     "saved antialiasing applied")) return 111;
        if (!require(applied.renderer == 1,
                     "saved renderer applied")) return 148;
        if (!require(applied.volume == 35,
                     "saved volume applied")) return 112;
        if (!require(applied.player_src[0] == 1,
                     "saved player source applied")) return 113;
        if (!require(std::strcmp(
                         applied.player_gamepad_guid[0],
                         "030000005e0400008e02000014010000") == 0,
                     "saved player gamepad guid applied")) return 114;

        applied.window_scale = 2;
        applied.display_layout = 1;
        applied.fullscreen = 1;
        applied.supersampling = 3;
        applied.antialiasing = 4;
        applied.renderer = 2;
        applied.volume = 80;
        applied.player_src[0] = 2;
        copy_text(applied.player_gamepad_guid[0],
                  "050000004c050000e60c000000010000");
        capture_launcher_settings(&loaded, applied);
        if (!require(loaded.window_scale == 2,
                     "changed window scale captured")) return 115;
        if (!require(loaded.display_layout == 1,
                     "changed display layout captured")) return 116;
        if (!require(loaded.fullscreen == 1,
                     "changed fullscreen captured")) return 117;
        if (!require(loaded.supersampling == 3,
                     "changed supersampling captured")) return 118;
        if (!require(loaded.antialiasing == 4,
                     "changed antialiasing captured")) return 119;
        if (!require(loaded.renderer_type == "soft",
                     "changed renderer captured")) return 149;
        if (!require(loaded.volume == 80,
                     "changed volume captured")) return 120;
        if (!require(loaded.player_src == 2,
                     "changed player source captured")) return 121;
        if (!require(loaded.player_gamepad_guid ==
                         "050000004c050000e60c000000010000",
                     "changed player gamepad guid captured")) return 122;

        if (!require(std::strcmp(runner_screen_layout_arg(
                         loaded.display_layout), "separate") == 0,
                     "captured separate launch arg")) return 97;
        if (!require(std::strcmp(runner_fullscreen_arg(
                         loaded.fullscreen), "borderless") == 0,
                     "captured fullscreen launch arg")) return 98;

        {
            std::ofstream file(settings_path, std::ios::trunc);
            file << "settings_version=4\n"
                    "window_scale=0\n"
                    "display_layout=99\n"
                    "fullscreen=-1\n"
                    "supersampling=9\n"
                    "antialiasing=6\n"
                    "volume=101\n"
                    "player_src=3\n"
                    "renderer_type=vulkan\n";
        }
        ModState invalid{};
        invalid.settings_path = settings_path;
        load_mod_state(invalid);
        if (!require(invalid.window_scale == 3,
                     "invalid window scale keeps default")) return 123;
        if (!require(invalid.display_layout == 1,
                     "invalid display layout keeps default")) return 99;
        if (!require(invalid.fullscreen == 0,
                     "invalid fullscreen keeps default")) return 100;
        if (!require(invalid.supersampling == 1,
                     "invalid supersampling keeps default")) return 124;
        if (!require(invalid.antialiasing == 0,
                     "invalid antialiasing keeps default")) return 125;
        if (!require(invalid.volume == 100,
                     "invalid volume keeps default")) return 126;
        if (!require(invalid.player_src == 2,
                     "invalid player source keeps default")) return 127;
        if (!require(invalid.renderer_type == "compute",
                     "invalid renderer keeps default")) return 127;

        std::filesystem::remove(settings_path);
    }

    // beads-lqa.3: the chosen ROM must survive a relaunch. It used to be
    // discarded in nds_persist_setup, so every launch fell back to the bundled
    // default path and anyone whose dump lived elsewhere saw "ROM not found"
    // forever.
    {
        const std::filesystem::path settings_path =
            std::filesystem::temp_directory_path() /
            "mph_mod_provider_rom_settings.ini";

        ModState saved{};
        saved.settings_path = settings_path;
        saved.rom_path = "D:\\Games\\NDS\\Metroid Prime Hunters.nds";
        saved.bios_path = "D:\\Games\\NDS\\bios\\biosnds9.rom";
        if (!require(save_mod_state(saved), "rom save")) return 73;

        ModState loaded{};
        loaded.settings_path = settings_path;
        load_mod_state(loaded);
        if (!require(loaded.rom_path == saved.rom_path,
                     "rom path round trip")) return 74;

        // The callback fires on BIOS browse too, with no ROM. An empty value
        // means "nothing selected right now", never "forget the pick" --
        // clearing here would reintroduce the original bug.
        if (!require(nds_persist_setup(&loaded, "", "E:\\dumps\\biosnds7.rom")
                         == 0,
                     "persist_setup with empty rom succeeds")) return 75;
        if (!require(loaded.rom_path == saved.rom_path,
                     "empty persist_setup rom does not clear the pick"))
            return 76;
        if (!require(loaded.bios_path == "E:\\dumps\\biosnds7.rom",
                     "persist_setup still updates bios")) return 77;

        if (!require(nds_persist_setup(&loaded, "E:\\other\\MPH.nds", "") == 0,
                     "persist_setup with a rom succeeds")) return 78;
        if (!require(loaded.rom_path == "E:\\other\\MPH.nds",
                     "persist_setup records a new rom pick")) return 79;

        // A path containing '=' must survive: load_mod_state splits on the
        // FIRST '=', so everything after it is the value.
        ModState equals_saved{};
        equals_saved.settings_path = settings_path;
        equals_saved.rom_path = "D:\\ROMs\\a=b\\Metroid Prime Hunters.nds";
        if (!require(save_mod_state(equals_saved), "rom save with equals"))
            return 80;
        ModState equals_loaded{};
        equals_loaded.settings_path = settings_path;
        load_mod_state(equals_loaded);
        if (!require(equals_loaded.rom_path == equals_saved.rom_path,
                     "rom path with '=' round trip")) return 81;

        // A pre-existing version-2 file has no rom_path key. It must load
        // cleanly with an empty pick and keep everything else.
        {
            std::ofstream file(settings_path, std::ios::trunc);
            file << "settings_version=2\n"
                    "bios_path=F:\\keepme\\biosnds9.rom\n"
                    "player_name=Samus\n";
        }
        ModState migrated{};
        migrated.settings_path = settings_path;
        load_mod_state(migrated);
        if (!require(migrated.rom_path.empty(),
                     "version 2 settings have no remembered rom")) return 82;
        if (!require(migrated.bios_path == "F:\\keepme\\biosnds9.rom",
                     "version 2 migration keeps bios_path")) return 83;
        if (!require(migrated.player_name == "Samus",
                     "version 2 migration keeps player_name")) return 84;

        std::filesystem::remove(settings_path);
    }

    // beads-q7fj: the title owns only the stable storage root. The runner
    // appends the exact ROM SHA-1, so the launcher must not duplicate it.
    // Keep testing the actual platform representation: UTF-16 plus Windows
    // command-line escaping, or a discrete UTF-8 argv element on POSIX.
    {
#ifdef _WIN32
        const std::filesystem::path data_dir =
            L"C:\\Users\\Test User\\Saved Games\\Metroid Тest";
        std::wstring command;
        append_savestate_dir_arg(command, data_dir);
        const std::filesystem::path expected = data_dir / "savestates";
        if (!require(command ==
                         L" --savestate-dir " + quote(expected.wstring()),
                     "Windows savestate root is one quoted argument"))
            return 171;
        if (!require(command.find(L"90164d1ac127ee5f9815ea4ae7de798c7b5fc629") ==
                         std::wstring::npos,
                     "Windows launcher does not append ROM SHA-1"))
            return 172;
#else
        const std::filesystem::path data_dir =
            std::filesystem::u8path("/tmp/Metroid Test Ω/data");
        std::vector<std::string> args;
        append_savestate_dir_arg(args, data_dir);
        const std::filesystem::path expected = data_dir / "savestates";
        if (!require(args.size() == 2 && args[0] == "--savestate-dir" &&
                         args[1] == expected.string(),
                     "POSIX savestate root is one argv element"))
            return 171;
        if (!require(args[1].find(
                         "90164d1ac127ee5f9815ea4ae7de798c7b5fc629") ==
                         std::string::npos,
                     "POSIX launcher does not append ROM SHA-1"))
            return 172;
#endif
    }

#ifdef _WIN32
    // Live-overlay gate. The regression this pins: a shipped extract sitting
    // anywhere near a sibling provider checkout used to be handed that
    // checkout's cache and compile command, so the bundled shards were never
    // scanned and every shard the stale provider built was rejected on ABI.
    {
        const std::filesystem::path root =
            std::filesystem::temp_directory_path() /
            "mph_live_overlay_gate_test";
        std::filesystem::remove_all(root);
        const std::filesystem::path game = root / "game";
        std::filesystem::create_directories(game);

        // A sibling provider tree of exactly the shape the old probe hunted
        // for. Nothing below may react to its existence.
        const std::filesystem::path provider =
            root / "ndsrecomp-live-overlay-provider";
        std::filesystem::create_directories(provider / "tools");
        std::filesystem::create_directories(
            provider / "runner" / "build-live-provider-mph");
        std::filesystem::create_directories(
            provider / "recompiler" / "build-live-provider");
        { std::ofstream f(provider / "tools" / "compile_live_shards.py"); }
        { std::ofstream f(provider / "recompiler" / "build-live-provider" /
                          "nds_recompile.exe"); }

        SetEnvironmentVariableW(L"NDS_LIVE_OVERLAY_COMMAND", nullptr);
        SetEnvironmentVariableW(L"NDS_LIVE_OVERLAY_CACHE", nullptr);

        // No bundled toolchain and no explicit opt-in: a bare runner must not
        // be pointed at a cache directory it has no way to fill.
        {
            std::wstring command;
            append_live_overlay_args(command, game);
            if (!require(command.empty(),
                         "no toolchain and no opt-in emits nothing"))
                return 160;
        }

        // Shipped layout: the bundled toolchain wins, the cache sits beside
        // the game, and NO command is passed -- the runner synthesizes the
        // bundled one itself from paths beside its own exe.
        std::filesystem::create_directories(game / "overlay_toolchain");
        { std::ofstream f(game / "overlay_toolchain" /
                          "compile_live_shards.py"); }
        {
            std::wstring command;
            append_live_overlay_args(command, game);
            if (!require(command.find(L"--live-overlay-enable") !=
                             std::wstring::npos,
                         "bundled toolchain enables the tier")) return 161;
            if (!require(command.find(L"--live-overlay-command") ==
                             std::wstring::npos,
                         "bundled toolchain passes no command")) return 162;
            const std::wstring want =
                L"--live-overlay-cache " +
                quote((game / "live-shard-cache").wstring());
            if (!require(command.find(want) != std::wstring::npos,
                         "bundled cache is beside the game")) return 163;
            // The stale dev default. Neither the redirect nor the ABI-stamped
            // name may ever come back.
            if (!require(command.find(L"live-shard-cache-v4") ==
                             std::wstring::npos,
                         "no ABI-stamped cache name")) return 164;
            if (!require(command.find(L"ndsrecomp-live-overlay-provider") ==
                             std::wstring::npos,
                         "sibling provider checkout is ignored")) return 165;
        }

        // Explicit opt-in overrides both halves independently.
        SetEnvironmentVariableW(L"NDS_LIVE_OVERLAY_COMMAND",
                                L"py -3 myprovider.py --max-pages 6");
        SetEnvironmentVariableW(L"NDS_LIVE_OVERLAY_CACHE",
                                L"D:\\dev\\my-shards");
        {
            std::wstring command;
            append_live_overlay_args(command, game);
            if (!require(command.find(
                             L"--live-overlay-command " +
                             quote(L"py -3 myprovider.py --max-pages 6")) !=
                             std::wstring::npos,
                         "env command opt-in is honoured")) return 166;
            if (!require(command.find(L"--live-overlay-cache " +
                                      quote(L"D:\\dev\\my-shards")) !=
                             std::wstring::npos,
                         "env cache opt-in is honoured")) return 167;
        }

        // Opt-in alone qualifies an install that has no bundled toolchain.
        std::filesystem::remove_all(game / "overlay_toolchain");
        {
            std::wstring command;
            append_live_overlay_args(command, game);
            if (!require(command.find(L"--live-overlay-enable") !=
                             std::wstring::npos,
                         "env opt-in enables without a bundled toolchain"))
                return 168;
        }

        // Cache-only opt-in leaves compilation to the runner's own policy.
        SetEnvironmentVariableW(L"NDS_LIVE_OVERLAY_COMMAND", nullptr);
        {
            std::wstring command;
            append_live_overlay_args(command, game);
            if (!require(command.find(L"--live-overlay-command") ==
                             std::wstring::npos,
                         "cache-only opt-in passes no command")) return 169;
            if (!require(command.find(L"--live-overlay-cache " +
                                      quote(L"D:\\dev\\my-shards")) !=
                             std::wstring::npos,
                         "cache-only opt-in still repoints the cache"))
                return 170;
        }

        SetEnvironmentVariableW(L"NDS_LIVE_OVERLAY_CACHE", nullptr);
        std::filesystem::remove_all(root);
    }
#endif

    return 0;
}
