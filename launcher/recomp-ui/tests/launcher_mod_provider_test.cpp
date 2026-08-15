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
    if (!require(feature.option_count == 26, "feature option count")) return 7;

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
            provider.ctx, "mph-prime-controls", "prime-controls", 3,
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
            provider.ctx, "mph-prime-controls", "prime-controls", 3,
            &option), "move-forward option get after reject")) {
        return 26;
    }
    if (!require(std::strcmp(option.value, "Right Shift") == 0,
                 "move-forward unchanged after reject")) return 27;

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

    if (!require(!provider.feature_get(provider.ctx, 3, &feature),
                 "no separate mouse aim feature")) {
        return 37;
    }

    // ---- beads-yjp.16: online identity (player name + read-only MAC) ----
    feature = {};
    if (!require(provider.feature_get(provider.ctx, 2, &feature),
                 "identity feature get")) {
        return 38;
    }
    if (!require(std::strcmp(feature.id, "online-identity") == 0,
                 "identity feature id")) return 39;
    if (!require(std::strcmp(feature.package_id,
                             "mph-online-identity") == 0,
                 "identity package id")) return 40;
    // Off by default: an unset name must never silently replace the
    // nickname a firmware dump already carries.
    if (!require(feature.enabled == 0, "identity off by default")) return 41;
    if (!require(feature.option_count == 1,
                 "identity exposes the player-name text option")) {
        return 42;
    }
    if (!require(std::strstr(feature.status, "firmware default") != nullptr,
                 "identity status reports the firmware default")) return 43;

    // The free-text option row (RECOMP_MOD_OPTION_TEXT upstream).
    RecompLauncherCModOption name_option{};
    if (!require(provider.feature_option_get(provider.ctx,
                                             "mph-online-identity",
                                             "online-identity", 0,
                                             &name_option) == 1,
                 "identity option get")) {
        return 60;
    }
    if (!require(name_option.type == RECOMP_MOD_OPTION_TEXT,
                 "player name is a text option")) return 61;
    if (!require(std::strcmp(name_option.id, "player-name") == 0,
                 "player name option id")) return 62;
    if (!require(provider.feature_set_option(provider.ctx,
                                             "mph-online-identity",
                                             "online-identity",
                                             "player-name",
                                             "Way Too Long Name") == 0,
                 "overlong name is rejected")) {
        return 63;
    }
    if (!require(provider.feature_set_option(provider.ctx,
                                             "mph-online-identity",
                                             "online-identity",
                                             "player-name", "Hunter") == 1,
                 "valid name is accepted")) {
        return 64;
    }
    if (!require(provider.feature_option_get(provider.ctx,
                                             "mph-online-identity",
                                             "online-identity", 0,
                                             &name_option) == 1 &&
                     std::strcmp(name_option.value, "Hunter") == 0,
                 "accepted name reads back")) {
        return 65;
    }
    if (!require(provider.feature_set_option(provider.ctx,
                                             "mph-online-identity",
                                             "online-identity",
                                             "player-name", "") == 1,
                 "empty clears back to the firmware default")) {
        return 66;
    }

    // The toggle must always succeed -- returning 0 aborts and rolls back the
    // launcher's bulk enable-all/disable-all edit.
    if (!require(provider.feature_enable(provider.ctx, "mph-online-identity",
                                         "online-identity", 1),
                 "identity enable accepted with no name")) {
        return 44;
    }
    if (!require(state.player_name_override, "identity override set")) {
        return 45;
    }
    if (!require(provider.feature_enable(provider.ctx, "mph-online-identity",
                                         "online-identity", 0),
                 "identity disable accepted")) {
        return 46;
    }
    if (!require(!state.player_name_override, "identity override cleared")) {
        return 47;
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
        saved.player_name_override = true;
        if (!require(save_mod_state(saved), "identity save")) return 56;
        ModState loaded{};
        loaded.settings_path = saved.settings_path;
        load_mod_state(loaded);
        if (!require(loaded.player_name == "Samus",
                     "identity name round trip")) return 57;
        if (!require(loaded.player_name_override,
                     "identity override round trip")) return 58;

        {
            std::ofstream file(saved.settings_path, std::ios::trunc);
            file << "player_name=this name is far too long\n"
                    "player_name_override=true\n";
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

    return 0;
}
