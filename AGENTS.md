# Project validation policy

The user has set a permanent validation policy for this workspace:

- Do not run performance or validation matrices for routine validation or releases.
- Do not run multi-route, multi-repetition, cold/warm, or per-platform benchmark legs for routine validation or releases.
- Gameplay validation is limited to one multiplayer run and one campaign run total unless the user explicitly requests another run.
- Existing user-confirmed manual runs count toward that limit; do not rerun them to satisfy internal process preferences.
- Build, packaging, artifact integrity, bank inventory, cache identity, license, and private-payload checks are still allowed because they are artifact checks, not gameplay validation runs.
- Do not fabricate passing performance-gate JSON. If old gate files exist, treat them as historical diagnostics only.
