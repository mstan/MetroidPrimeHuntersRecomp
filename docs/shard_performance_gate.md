# MPH shard performance gate status

This workflow is deprecated for routine validation and releases.

The user has set a permanent validation policy: do not run performance or validation matrices, multi-route runs, multi-repetition runs, cold/warm benchmark legs, or per-platform benchmark legs for routine validation or release qualification.

Gameplay validation is limited to one multiplayer run and one campaign run total unless the user explicitly requests another run. Existing user-confirmed manual runs count toward that limit. Do not rerun gameplay to satisfy a previous matrix or gate requirement.

Release packaging should continue to run artifact checks that do not play the game:

- verify the exact packaged runner contains the expected bank inventory;
- verify staged native shard cache files match the current provider identity when a cache is shipped;
- verify bundled runtime/toolchain files and required licenses are present;
- verify release archives exclude ROMs, BIOS/firmware, saves, raw captures, generated source, and other private payloads;
- verify version metadata, release notes, checksums, and artifact names.

Historical `tools/shard_performance_gate.py` outputs may be useful for diagnostics, but they are not required release evidence. Do not fabricate passing performance-gate JSON for packaging.
