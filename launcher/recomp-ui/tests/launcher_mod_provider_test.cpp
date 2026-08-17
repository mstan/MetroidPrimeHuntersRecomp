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
        if (!require(legacy_state.mouse_sensitivity == 30,
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
    // Three gameplay mods; the online identity is a dashboard card, not a
    // mod. Index 1 stays prime controls so the assertions below are
    // unaffected by HD rendering being added at index 2.
    const int feature_count = provider.feature_count(provider.ctx);
    if (!require(feature_count == 3, "feature_count == 3")) return 4;

    RecompLauncherCModFeature feature{};
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
    if (!require(feature.option_count == 50, "feature option count")) return 7;

    RecompLauncherCModOption option{};
    if (!require(provider.feature_option_get(
            provider.ctx, "mph-prime-controls", "prime-controls", 0,
            &option), "aim sensitivity option get")) {
        return 8;
    }
    if (!require(std::strcmp(option.id, "aim-sensitivity") == 0,
                 "aim sensitivity option id")) return 9;
    if (!require(std::strcmp(option.value, "30") == 0,
                 "aim sensitivity default value")) return 10;
    if (!require(std::strcmp(option.default_value, "30") == 0,
                 "aim sensitivity declared default")) return 11;
    if (!require(option.choice_count == 11,
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
            provider.ctx, "mph-prime-controls", "prime-controls", 3,
            &option), "pad aim sensitivity option get")) {
        return 14;
    }
    if (!require(std::strcmp(option.id, "pad-aim-sensitivity") == 0,
                 "pad aim sensitivity option id")) return 14;
    if (!require(std::strcmp(option.value, "100") == 0,
                 "pad aim sensitivity default value")) return 14;
    if (!require(std::strcmp(option.default_value, "100") == 0,
                 "pad aim sensitivity declared default")) return 14;
    if (!require(option.choice_count == 11,
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
            provider.ctx, "mph-prime-controls", "prime-controls", 4,
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
            provider.ctx, "mph-prime-controls", "prime-controls", 2,
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
            provider.ctx, "mph-prime-controls", "prime-controls", 4,
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
            provider.ctx, "mph-prime-controls", "prime-controls", 4,
            &option), "move-forward option get after reject")) {
        return 26;
    }
    if (!require(std::strcmp(option.value, "Right Shift") == 0,
                 "move-forward unchanged after reject")) return 27;

    // Gamepad rows follow the keyboard rows: index 27 = pad-move-forward,
    // 34 = pad-scan-visor (defaults None and Pad R3 respectively).
    option = {};
    if (!require(provider.feature_option_get(
            provider.ctx, "mph-prime-controls", "prime-controls", 27,
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
            provider.ctx, "mph-prime-controls", "prime-controls", 34,
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
            provider.ctx, "mph-prime-controls", "prime-controls", 2,
            &option), "virtual stylus sensitivity option get")) {
        return 35;
    }
    if (!require(std::strcmp(option.value, "150") == 0,
                 "virtual stylus sensitivity mutated value")) return 36;

    // The online identity is NOT a mod feature: it lives on the dashboard
    // ONLINE card (GameInfo.has_player_name + the NDS "identity" panel).
    // Exactly the three gameplay mods remain; index 3 must not resolve.
    if (!require(!provider.feature_get(provider.ctx, 3, &feature),
                 "exactly three mod features (identity is not a mod)")) {
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

    return 0;
}
