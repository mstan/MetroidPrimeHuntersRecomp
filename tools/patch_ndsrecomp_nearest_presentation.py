#!/usr/bin/env python3
"""Force DS framebuffer presentation to use nearest-neighbor sampling.

The pinned ndsrecomp frontend historically changed SDL_HINT_RENDER_SCALE_QUALITY
to linear whenever presentation supersampling or AA was selected. That makes a
native 256x192 DS framebuffer blurry while scaling. It became especially
visible after the HD direct presenter landed: the top screen can bypass SDL and
stay crisp via OpenGL texelFetch/NEAREST while the bottom screen still passes
through SDL's linear RenderCopy path.

Presentation scaling is pixel-art/framebuffer scaling, not texture enhancement.
Keep it nearest regardless of supersampling/AA settings. Texture upscaling is a
separate, explicit HD Rendering option and is not changed here.
"""

from __future__ import annotations

import argparse
from pathlib import Path

HINT_MARKER = "NDS_MPH_NEAREST_PRESENT_HINT"
TEXTURE_MARKER = "NDS_MPH_NEAREST_PRESENT_TEXTURE"
TARGET_MARKER = "NDS_MPH_NEAREST_PRESENT_TARGET"


def patch_once(path: Path, old: str, new: str, marker: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    if old not in text:
        raise SystemExit(
            f"Refusing nearest-presentation patch for {path}: expected pinned "
            f"preimage for {marker!r} was not found"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch(framework_root: Path) -> None:
    frontend = framework_root / "runner" / "src" / "frontend.cpp"
    if not frontend.is_file():
        raise SystemExit(f"runner source missing: {frontend}")

    # Never let supersampling/AA silently select SDL bilinear filtering. Use
    # OVERRIDE so an inherited/environment hint cannot re-enable smoothing.
    patch_once(
        frontend,
        '''    SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY,\n                (options.supersampling > 1 || options.antialiasing > 0)\n                    ? "1" : "0");\n''',
        '''    // NDS_MPH_NEAREST_PRESENT_HINT: DS framebuffer presentation is\n    // pixel-exact. Supersampling/AA must not silently turn SDL RenderCopy\n    // into bilinear filtering (which especially blurs the native bottom\n    // screen while an HD/OpenGL top screen remains crisp).\n    if (SDL_SetHintWithPriority(SDL_HINT_RENDER_SCALE_QUALITY, "0",\n                                SDL_HINT_OVERRIDE) == SDL_FALSE) {\n        std::fprintf(stderr,\n                     "[sdl] warning: could not force nearest render-scale hint\\n");\n    }\n''',
        HINT_MARKER,
    )

    # The global hint is only a default at texture creation time. Pin the
    # actual source texture explicitly too, so later hint changes or backend
    # defaults cannot alter presentation quality.
    patch_once(
        frontend,
        '''        if (!presentation.textures[screen]) {\n            std::fprintf(stderr, "[sdl] texture failed: %s\\n",\n                         SDL_GetError());\n            destroy_presentation(presentation);\n            return false;\n        }\n        if (presentation.sample_scale > 1) {\n''',
        '''        if (!presentation.textures[screen]) {\n            std::fprintf(stderr, "[sdl] texture failed: %s\\n",\n                         SDL_GetError());\n            destroy_presentation(presentation);\n            return false;\n        }\n        // NDS_MPH_NEAREST_PRESENT_TEXTURE: never smooth DS framebuffer pixels.\n        if (SDL_SetTextureScaleMode(presentation.textures[screen],\n                                    SDL_ScaleModeNearest) != 0) {\n            std::fprintf(stderr,\n                         "[sdl] nearest texture scale mode failed: %s\\n",\n                         SDL_GetError());\n            destroy_presentation(presentation);\n            return false;\n        }\n        if (presentation.sample_scale > 1) {\n''',
        TEXTURE_MARKER,
    )

    # A supersample target is subsequently used as the source of another
    # RenderCopy. It needs an explicit nearest source mode as well, otherwise
    # the second copy can still blur even if the native upload texture is crisp.
    patch_once(
        frontend,
        '''            if (!presentation.sample_targets[screen]) {\n                std::fprintf(stderr,\n                             "[sdl] supersample target failed: %s\\n",\n                             SDL_GetError());\n                destroy_presentation(presentation);\n                return false;\n            }\n        }\n''',
        '''            if (!presentation.sample_targets[screen]) {\n                std::fprintf(stderr,\n                             "[sdl] supersample target failed: %s\\n",\n                             SDL_GetError());\n                destroy_presentation(presentation);\n                return false;\n            }\n            // NDS_MPH_NEAREST_PRESENT_TARGET: the enlarged target is also a\n            // later RenderCopy source, so pin that copy to nearest explicitly.\n            if (SDL_SetTextureScaleMode(presentation.sample_targets[screen],\n                                        SDL_ScaleModeNearest) != 0) {\n                std::fprintf(stderr,\n                             "[sdl] nearest supersample scale mode failed: %s\\n",\n                             SDL_GetError());\n                destroy_presentation(presentation);\n                return false;\n            }\n        }\n''',
        TARGET_MARKER,
    )

    print(
        "Patched SDL framebuffer presentation: nearest-only scaling for native "
        "textures and supersample targets"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework-root", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=False)
    args = parser.parse_args()
    patch(args.framework_root.resolve())


if __name__ == "__main__":
    main()
