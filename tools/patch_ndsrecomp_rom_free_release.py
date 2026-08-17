#!/usr/bin/env python3
"""Make the pinned ndsrecomp runner buildable without proprietary BIOS banks.

The public/no-dump build keeps the BSD-licensed FreeBIOS banks native. Retail
BIOS dumps remain usable when a user supplies them, but their immutable BIOS
code executes through the existing reference interpreter instead of requiring
ROM/BIOS-derived generated C in the distributed build.

This patch is intentionally separate from the MPH title-profile patch stack:
it changes only the shared runner's immutable-BIOS build policy and is useful
for ROM-free CI/release packaging. It is idempotent and pinned to the currently
expected ndsrecomp source shape; drift fails closed.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(path: Path, old: str, new: str, marker: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text and old not in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{path}: expected exactly one source anchor for {marker!r}, got {count}"
        )
    path.write_text(text.replace(old, new), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.framework_root.resolve()

    cmake = root / "runner" / "CMakeLists.txt"
    state = root / "runner" / "src" / "state.h"
    runtime = root / "runner" / "src" / "runtime_arm.cpp"
    tier3 = root / "runner" / "src" / "tier3.cpp"
    main_cpp = root / "runner" / "src" / "main.cpp"
    for path in (cmake, state, runtime, tier3, main_cpp):
        if not path.is_file():
            raise SystemExit(f"missing pinned ndsrecomp source: {path}")

    replace_once(
        cmake,
        '''option(NDS_BOOTSTRAP_FIRMWARE\n    "Build with BIOS banks only so guest-produced firmware RAM can be captured"\n    OFF)\n''',
        '''option(NDS_BOOTSTRAP_FIRMWARE\n    "Build with BIOS banks only so guest-produced firmware RAM can be captured"\n    OFF)\noption(NDS_RETAIL_BIOS_BANKS\n    "Link generated proprietary retail-BIOS banks instead of interpreter fallback"\n    ON)\n''',
        "NDS_RETAIL_BIOS_BANKS",
    )

    replace_once(
        cmake,
        '''add_library(nds_banks STATIC\n    ${GEN}/arm9_bios.c\n    ${GEN}/arm9_bios_dispatch.c\n    ${GEN}/arm7_bios.c\n    ${GEN}/arm7_bios_dispatch.c\n    ${GEN}/freebios_arm9.c\n    ${GEN}/freebios_arm9_dispatch.c\n    ${GEN}/freebios_arm7.c\n    ${GEN}/freebios_arm7_dispatch.c\n    ${FW_BANK_BODIES}\n    ${FW_BANK_DISPATCH}\n    ${SM64DS_BANK_SOURCES}\n    ${TITLE_BANK_SOURCES})\n''',
        '''# Public/no-dump builds need only the redistributable FreeBIOS static banks.\n# Retail BIOS dumps can still be supplied at runtime when NDS_RETAIL_BIOS_BANKS=OFF;\n# their immutable code then uses the reference interpreter instead of generated C.\nset(IMMUTABLE_BIOS_BANK_SOURCES\n    ${GEN}/freebios_arm9.c\n    ${GEN}/freebios_arm9_dispatch.c\n    ${GEN}/freebios_arm7.c\n    ${GEN}/freebios_arm7_dispatch.c)\nif(NDS_RETAIL_BIOS_BANKS)\n    list(APPEND IMMUTABLE_BIOS_BANK_SOURCES\n        ${GEN}/arm9_bios.c\n        ${GEN}/arm9_bios_dispatch.c\n        ${GEN}/arm7_bios.c\n        ${GEN}/arm7_bios_dispatch.c)\nelse()\n    add_compile_definitions(NDS_RETAIL_BIOS_INTERPRETER=1)\nendif()\nadd_library(nds_banks STATIC\n    ${IMMUTABLE_BIOS_BANK_SOURCES}\n    ${FW_BANK_BODIES}\n    ${FW_BANK_DISPATCH}\n    ${SM64DS_BANK_SOURCES}\n    ${TITLE_BANK_SOURCES})\n''',
        "IMMUTABLE_BIOS_BANK_SOURCES",
    )

    replace_once(
        cmake,
        '''set_source_files_properties(\n    ${GEN}/arm9_bios.c ${GEN}/arm9_bios_dispatch.c\n    ${GEN}/arm7_bios.c ${GEN}/arm7_bios_dispatch.c\n    ${GEN}/freebios_arm9.c ${GEN}/freebios_arm9_dispatch.c\n    ${GEN}/freebios_arm7.c ${GEN}/freebios_arm7_dispatch.c\n''',
        '''set_source_files_properties(\n    ${IMMUTABLE_BIOS_BANK_SOURCES}\n''',
        "set_source_files_properties(\n    ${IMMUTABLE_BIOS_BANK_SOURCES}",
    )

    replace_once(
        cmake,
        '''set(ARM9_BANK_SOURCES ${GEN}/arm9_bios.c ${GEN}/arm9_bios_dispatch.c\n    ${GEN}/freebios_arm9.c ${GEN}/freebios_arm9_dispatch.c)\nset(ARM7_BANK_SOURCES ${GEN}/arm7_bios.c ${GEN}/arm7_bios_dispatch.c\n    ${GEN}/freebios_arm7.c ${GEN}/freebios_arm7_dispatch.c)\n''',
        '''set(ARM9_BANK_SOURCES\n    ${GEN}/freebios_arm9.c ${GEN}/freebios_arm9_dispatch.c)\nset(ARM7_BANK_SOURCES\n    ${GEN}/freebios_arm7.c ${GEN}/freebios_arm7_dispatch.c)\nif(NDS_RETAIL_BIOS_BANKS)\n    list(APPEND ARM9_BANK_SOURCES\n        ${GEN}/arm9_bios.c ${GEN}/arm9_bios_dispatch.c)\n    list(APPEND ARM7_BANK_SOURCES\n        ${GEN}/arm7_bios.c ${GEN}/arm7_bios_dispatch.c)\nendif()\n''',
        "if(NDS_RETAIL_BIOS_BANKS)\n    list(APPEND ARM9_BANK_SOURCES",
    )

    replace_once(
        state,
        '''extern bool g_discover_static_misses;\n''',
        '''extern bool g_discover_static_misses;\n// Public ROM-free builds do not carry generated retail-BIOS code. When a\n// user explicitly supplies retail dumps, allow only immutable BIOS addresses\n// to use the same reference interpreter used by coverage discovery.\nextern bool g_allow_static_bios_interpreter;\n''',
        "g_allow_static_bios_interpreter",
    )

    replace_once(
        runtime,
        '''bool        g_discover_static_misses = false;\n''',
        '''bool        g_discover_static_misses = false;\nbool        g_allow_static_bios_interpreter = false;\n''',
        "g_allow_static_bios_interpreter = false",
    )

    replace_once(
        runtime,
        '''        if (g_discover_static_misses && static_bios_pc(pc)) {\n            runtime_discovery_note_static(pc, thumb ? 1u : 0u);\n            tier3_run(pc);\n            return;\n        }\n''',
        '''        if ((g_discover_static_misses || g_allow_static_bios_interpreter) &&\n            static_bios_pc(pc)) {\n            if (g_discover_static_misses)\n                runtime_discovery_note_static(pc, thumb ? 1u : 0u);\n            tier3_run(pc);\n            return;\n        }\n''',
        "g_allow_static_bios_interpreter) &&",
    )

    replace_once(
        tier3,
        '''        if (!bus_range_has_write_provenance(fetch_addr, fetch_size) &&\n            !(g_discover_static_misses && static_bios_pc(pc & ~1u))) {\n''',
        '''        if (!bus_range_has_write_provenance(fetch_addr, fetch_size) &&\n            !((g_discover_static_misses || g_allow_static_bios_interpreter) &&\n              static_bios_pc(pc & ~1u))) {\n''',
        "g_allow_static_bios_interpreter) &&",
    )

    replace_once(
        main_cpp,
        '''extern "C" const DispatchEntry g_dispatch_arm9_bios[];\nextern "C" const unsigned g_dispatch_arm9_bios_len;\nextern "C" const DispatchEntry g_dispatch_arm7_bios[];\nextern "C" const unsigned g_dispatch_arm7_bios_len;\n''',
        '''#if !defined(NDS_RETAIL_BIOS_INTERPRETER)\nextern "C" const DispatchEntry g_dispatch_arm9_bios[];\nextern "C" const unsigned g_dispatch_arm9_bios_len;\nextern "C" const DispatchEntry g_dispatch_arm7_bios[];\nextern "C" const unsigned g_dispatch_arm7_bios_len;\n#endif\n''',
        "#if !defined(NDS_RETAIL_BIOS_INTERPRETER)",
    )

    replace_once(
        main_cpp,
        '''        } else {\n            nds_register_dispatch(NDS_ARM9, g_dispatch_arm9_bios,\n                                  g_dispatch_arm9_bios_len, 0xFFFF0000u);\n            nds_register_dispatch(NDS_ARM7, g_dispatch_arm7_bios,\n                                  g_dispatch_arm7_bios_len, 0x00000000u);\n        }\n''',
        '''        } else {\n#if defined(NDS_RETAIL_BIOS_INTERPRETER)\n            g_allow_static_bios_interpreter = true;\n            std::fprintf(stderr,\n                         "[dispatch] retail BIOS uses reference interpreter "\n                         "(ROM-free build)\\n");\n#else\n            nds_register_dispatch(NDS_ARM9, g_dispatch_arm9_bios,\n                                  g_dispatch_arm9_bios_len, 0xFFFF0000u);\n            nds_register_dispatch(NDS_ARM7, g_dispatch_arm7_bios,\n                                  g_dispatch_arm7_bios_len, 0x00000000u);\n#endif\n        }\n''',
        "retail BIOS uses reference interpreter",
    )

    print(f"Patched ROM-free release support in {root}")


if __name__ == "__main__":
    main()
