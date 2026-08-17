# Prime Hunters bring-up ledger

## Target and references

The project began with the USA revision-0 (`AMHE`) bring-up and now carries a
seven-base-profile runtime layout/detector for US1.0, US1.1, EU1.0, EU1.1,
JP1.0, JP1.1, and KR1.0. Exact clean-content profiles, generated banks,
coverage, and capture artifacts remain content-specific and must not be inferred
from a base layout alone.

The original US1.0 content identity is SHA-1
`90164d1ac127ee5f9815ea4ae7de798c7b5fc629`. Whole-ROM SHA-1 is provenance and
cache/build identity, not the runtime base-profile selector.

## Runtime identity rules

1. Use the melonPrime-compatible executable CRC32 detector as the authoritative
   runtime base-profile signal.
2. An exact supported game-code/revision tuple may identify only a candidate
   base profile when the executable checksum is unknown.
3. Dangerous host RAM/code writes fail closed unless executable compatibility
   is authoritative.
4. Generated title banks, runtime captures, and coverage remain scoped by exact
   content identity.
5. Unknown modified content must never silently fall back to US1.0.

## ROM-free Nightly architecture

Public Windows/Linux Nightly builds are intentionally produced without a
Metroid Prime Hunters ROM, ROM URL/secret, proprietary BIOS or firmware dump,
save file, or generated ROM-derived MPH title bank.

The pinned ndsrecomp runner is patched for an opt-in public-build mode:

- redistributable BSD-2-Clause FreeBIOS images are recompiled into the native
  FreeBIOS ARM9/ARM7 banks using ndsrecomp's documented FreeBIOS pipeline;
- `NDS_RETAIL_BIOS_BANKS=OFF` removes the build-time requirement for generated
  proprietary retail-BIOS banks;
- if a user later supplies retail BIOS dumps, immutable BIOS execution may use
  the existing reference interpreter rather than requiring those generated C
  banks in the distributed binary;
- no MPH title-bank directory is configured, so direct-booted MPH ARM9/ARM7
  code falls through to Tier-3 using guest-written RAM provenance.

This is a correctness-first release path. It is expected to be slower than the
historical optimized US1.0 release, particularly in opening-FMV/runtime-code hot
paths.

## Local optimization cache direction

The preferred future optimization cache is portable-first:

```text
cache/banks/<content-sha1>/
```

beside the executable/AppImage. Linux falls back to XDG cache when that location
is not writable; Windows should fall back to LOCALAPPDATA under the same
condition. Save data and firmware/WFC identity remain persistent app data, not
regenerable optimization cache.

The current static ndsrecomp bank pipeline emits C and links it into the runner,
so the project will not make users run a host C/C++ compiler on first launch.
The intended progression is Tier-3 -> compiler-free local IR/bank support if
useful -> hot-block JIT with a validated persistent cache. See
`docs/LOCAL_BANK_CACHE.md`.

## Adaptive Widescreen

Adaptive Widescreen combines the original ndsrecomp host-side widened
renderer/compositor/HUD anchoring with MPH game-side projection and culling
patches audited against melonPrimeDS/mphCodex. The guest patch addresses are
profile-aware across all seven base layouts and are applied only under the
existing authoritative executable-compatibility gate.

## Upstream launcher/runtime integration

The launcher tracks the upstream MPH recomp-ui feature set including Adaptive
Widescreen, Prime Controls, HD Rendering, and persistent firmware/WFC state.
The launcher does not use whole-ROM SHA-1 as an early acceptance gate; the
runner owns executable compatibility and exact-content decisions.

## Validation gates

- [x] Seven runtime base profiles represented.
- [x] Executable CRC32 runtime detector and strict header fallback.
- [x] Dangerous host writes fail closed for unknown executable content.
- [x] All-seven Adaptive Widescreen address table integrated.
- [x] Upstream launcher HD/Wi-Fi persistence integration retained.
- [x] ROM-free release design avoids ROM/ROM-secret input in GitHub Actions.
- [x] FreeBIOS native-bank generation has a redistributable build path.
- [ ] Windows ROM-free Nightly workflow passes full compile/package CI.
- [ ] Linux ROM-free Nightly workflow passes full compile/AppImage CI.
- [ ] Real-ROM runtime smoke validation of the ROM-free Tier-3 Nightly path.
- [ ] Implement compiler-free dynamic/local optimization-bank ABI or JIT.
- [ ] Complete exact clean-content profiles and sustained gameplay validation
      for US1.1, EU1.0, JP1.0, JP1.1, and KR1.0.
- [ ] Add modified-ROM content profiles only after their actual executable and
      content identities are validated; do not add placeholder identities.

## Release safety

Nightly packaging explicitly rejects ROMs, saves, retail BIOS/firmware dumps,
and generated/capture directories. Windows ZIP and Linux AppImage artifacts are
built first and published to the fixed `nightly-release` prerelease only after
both platform jobs and payload verification succeed. A source-policy check also
rejects reintroduction of repository/environment secret references into the
public build/Nightly workflows.
