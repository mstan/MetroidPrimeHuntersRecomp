#!/usr/bin/env python3
"""Add end-user MPH startup diagnostics to the pinned ndsrecomp runner.

This layer intentionally runs after patch_ndsrecomp_mph_runtime_core.py:

* interactive launches write stderr to MetroidPrimeHuntersRecomp.log beside
  nds_runner, so CREATE_NO_WINDOW launcher starts still leave a useful trace;
* runtime-profile selection reports gameCode/revision/executable CRC32,
  authoritative-vs-header-fallback source, selected profile and host-write
  safety state;
* ROM-free builds treat a successfully selected MPH runtime profile as the
  compatibility authority instead of re-applying the legacy US1.0 whole-ROM
  SHA-1 gate. Native/title-bank builds keep the existing exact-content policy.

Whole-ROM SHA-1 remains useful content/cache identity; it is not used as the
base-version detector in the ROM-free Tier-3 path.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(path: Path, old: str, new: str, marker: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{path}: expected exactly one source anchor for {marker!r}, got {count}"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework-root", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=False)
    args = parser.parse_args()
    root = args.framework_root.resolve()

    title_cpp = root / "runner" / "src" / "title_patches.cpp"
    main_cpp = root / "runner" / "src" / "main.cpp"
    for path in (title_cpp, main_cpp):
        if not path.is_file():
            raise SystemExit(f"missing pinned ndsrecomp source: {path}")

    # The launcher intentionally creates no console window. Redirecting stderr
    # from inside the runner is therefore more reliable than relying on the
    # parent's inherited standard handles. Only the normal --interactive UI
    # path gets the persistent file; CLI/scenario runs keep stderr untouched.
    replace_once(
        main_cpp,
        "int main(int argc, char** argv) {\n"
        "    // Wiimmfi: Winsock (Windows only) MUST be initialized before ANY\n",
        "int main(int argc, char** argv) {\n"
        "    // MPH_DIAGNOSTIC_LOG: keep the latest interactive-run log beside\n"
        "    // nds_runner.exe/AppImage payload so a no-console startup failure is\n"
        "    // still diagnosable by the player. CLI/scenario stderr is unchanged.\n"
        "    bool mph_interactive_log = false;\n"
        "    for (int i = 1; i < argc; ++i) {\n"
        "        if (argv[i] && std::strcmp(argv[i], \"--interactive\") == 0) {\n"
        "            mph_interactive_log = true;\n"
        "            break;\n"
        "        }\n"
        "    }\n"
        "    if (mph_interactive_log) {\n"
        "        try {\n"
        "            const std::filesystem::path log_path =\n"
        "                std::filesystem::weakly_canonical(\n"
        "                    std::filesystem::absolute(argv[0])).parent_path() /\n"
        "                \"MetroidPrimeHuntersRecomp.log\";\n"
        "#if defined(_WIN32)\n"
        "            FILE* mph_log = _wfreopen(log_path.wstring().c_str(), L\"w\", stderr);\n"
        "#else\n"
        "            FILE* mph_log = std::freopen(log_path.string().c_str(), \"w\", stderr);\n"
        "#endif\n"
        "            if (mph_log) {\n"
        "                std::setvbuf(stderr, nullptr, _IONBF, 0);\n"
        "                std::fprintf(stderr,\n"
        "                    \"=== Metroid Prime Hunters Recomp diagnostic log ===\\n\"\n"
        "                    \"[startup] interactive runner started\\n\");\n"
        "            }\n"
        "        } catch (...) {\n"
        "            // Logging must never make a previously launchable build fail.\n"
        "        }\n"
        "    }\n\n"
        "    // Wiimmfi: Winsock (Windows only) MUST be initialized before ANY\n",
        "MPH_DIAGNOSTIC_LOG",
    )

    # Turn the previously ignored selector result into an explicit policy
    # signal. The selector itself still performs executable/header validation.
    replace_once(
        main_cpp,
        "        nds_title_patches_select_mph_runtime_profile(\n"
        "            rom.data(), static_cast<uint64_t>(rom.size()), rom_sha1.c_str(),\n"
        "            frontend_options.expected_rom_sha1.c_str());\n",
        "        const bool mph_runtime_profile_selected =\n"
        "            nds_title_patches_select_mph_runtime_profile(\n"
        "                rom.data(), static_cast<uint64_t>(rom.size()),\n"
        "                rom_sha1.c_str(),\n"
        "                frontend_options.expected_rom_sha1.c_str());\n",
        "mph_runtime_profile_selected =",
    )

    # NDS_RETAIL_BIOS_INTERPRETER is defined only by the public ROM-free build
    # policy when proprietary retail BIOS banks are not linked. That is also
    # the build with no MPH native title bank, so Tier-3 + the seven-version
    # runtime detector is the correct authority. Optimized/native-bank builds
    # deliberately retain the stricter content-SHA policy below.
    replace_once(
        main_cpp,
        "        if (!frontend_options.expected_rom_sha1.empty() &&\n"
        "            rom_sha1 != frontend_options.expected_rom_sha1 &&\n"
        "            !nds_title_patches_mph_allows_rom_sha1_mismatch()) {\n",
        "#if defined(NDS_RETAIL_BIOS_INTERPRETER)\n"
        "        // MPH_ROMFREE_MULTIROM_GATE: public Nightly has no ROM-derived\n"
        "        // title bank, so a successfully selected runtime base profile\n"
        "        // is authoritative. This is what permits US1.1/EU/JP/KR and\n"
        "        // compatible modified ROMs to reach Tier-3 execution.\n"
        "        if (!frontend_options.expected_rom_sha1.empty() &&\n"
        "            rom_sha1 != frontend_options.expected_rom_sha1 &&\n"
        "            !mph_runtime_profile_selected) {\n"
        "#else\n"
        "        if (!frontend_options.expected_rom_sha1.empty() &&\n"
        "            rom_sha1 != frontend_options.expected_rom_sha1 &&\n"
        "            !nds_title_patches_mph_allows_rom_sha1_mismatch()) {\n"
        "#endif\n",
        "MPH_ROMFREE_MULTIROM_GATE",
    )

    # Give every rejection enough context to distinguish a malformed ROM from
    # a supported version, a known modified executable, or a header-only mod.
    replace_once(
        title_cpp,
        "    uint32_t checksum = 0;\n"
        "    if (!mph_compute_executable_checksum(rom_data, rom_size, &checksum))\n"
        "        return false;\n",
        "    uint32_t checksum = 0;\n"
        "    if (!mph_compute_executable_checksum(rom_data, rom_size, &checksum)) {\n"
        "        std::fprintf(stderr,\n"
        "                     \"[mph] runtime detector: invalid ROM executable ranges\"\n"
        "                     \" (size=%llu)\\n\",\n"
        "                     static_cast<unsigned long long>(rom_size));\n"
        "        return false;\n"
        "    }\n"
        "    std::fprintf(stderr,\n"
        "                 \"[mph] identity: gameCode=%.4s revision=%u \"\n"
        "                 \"execCRC32=0x%08X\\n\",\n"
        "                 reinterpret_cast<const char*>(rom_data + 0x0Cu),\n"
        "                 static_cast<unsigned>(rom_data[0x1Eu]), checksum);\n",
        "[mph] identity: gameCode=",
    )

    replace_once(
        title_cpp,
        "    if (!profile) return false;\n\n"
        "    // A known clean whole-ROM hash can only describe its own base profile.\n",
        "    if (!profile) {\n"
        "        std::fprintf(stderr,\n"
        "                     \"[mph] runtime detector: unsupported/ambiguous ROM \"\n"
        "                     \"(execCRC32=0x%08X)\\n\", checksum);\n"
        "        return false;\n"
        "    }\n\n"
        "    // A known clean whole-ROM hash can only describe its own base profile.\n",
        "unsupported/ambiguous ROM",
    )

    replace_once(
        title_cpp,
        "    const NdsMphRuntimeProfile* actual_clean = mph_find_clean_sha1(rom_sha1);\n"
        "    if (actual_clean && actual_clean != profile) return false;\n",
        "    const NdsMphRuntimeProfile* actual_clean = mph_find_clean_sha1(rom_sha1);\n"
        "    if (actual_clean && actual_clean != profile) {\n"
        "        std::fprintf(stderr,\n"
        "                     \"[mph] runtime detector: clean SHA/profile conflict \"\n"
        "                     \"shaProfile=%s detectedProfile=%s\\n\",\n"
        "                     actual_clean->key, profile->key);\n"
        "        return false;\n"
        "    }\n",
        "clean SHA/profile conflict",
    )

    replace_once(
        title_cpp,
        "    g_mph_allow_rom_sha1_mismatch =\n"
        "        std::strcmp(rom_sha1, expected_rom_sha1) != 0 &&\n"
        "        expected_clean == profile && checksum == profile->base_checksum;\n"
        "    return true;\n",
        "    g_mph_allow_rom_sha1_mismatch =\n"
        "        std::strcmp(rom_sha1, expected_rom_sha1) != 0 &&\n"
        "        expected_clean == profile && checksum == profile->base_checksum;\n"
        "    std::fprintf(stderr,\n"
        "                 \"[mph] runtime profile: %s detector=%s variant=%s \"\n"
        "                 \"hostWrites=%s legacyShaReuse=%s\\n\",\n"
        "                 profile->key,\n"
        "                 checksum_hit ? \"executable-checksum\" : \"header-fallback\",\n"
        "                 checksum_hit ? checksum_hit->name : \"unknown-mod\",\n"
        "                 g_mph_host_writes_compatible ? \"enabled\" : \"disabled\",\n"
        "                 g_mph_allow_rom_sha1_mismatch ? \"yes\" : \"no\");\n"
        "    return true;\n",
        "[mph] runtime profile:",
    )

    print("Patched MPH runtime diagnostics and ROM-free multi-ROM content gate")


if __name__ == "__main__":
    main()
