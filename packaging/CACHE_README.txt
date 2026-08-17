Metroid Prime Hunters Recomp optimization cache
================================================

This directory is reserved for locally generated optimization banks/caches.
The preferred portable layout is:

  cache/banks/<content-sha1>/

The whole-ROM SHA-1 is used only as the content/cache namespace. Runtime base
profile selection continues to use the executable-compatible MPH detector and
must never guess a base profile from this cache path.

Current ROM-free Nightly builds do not generate native title banks here yet;
missing title banks execute through the ndsrecomp Tier-3 reference interpreter.
A future local JIT/portable-bank backend will populate this directory without
requiring a C/C++ compiler on the player's machine.

If the application directory is not writable, implementations should fall back
to the operating system cache location (LOCALAPPDATA on Windows, XDG cache on
Linux). Saves and firmware identity/state are persistent user data and do not
belong in this regenerable cache.
