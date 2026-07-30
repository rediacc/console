"""[6000] Render the storyboard to MP4 via Remotion.

Reads:  5000_storyboard.json, audio/voiceover.mp3
Writes: video/<slug>.en.mp4, 6000_render.json

The step stages audio into remotion/public/<slug>/, resolves any iconScene
SVG manifest IDs to recolored SVG files staged into remotion/public/<slug>/svg/,
rewrites the storyboard audio path to a public/-relative value, writes
props.json, and shells out to npx remotion render.

SVG recolor rules (baked into the file so Remotion <Img> sees a real color):
  - source in {lucide, feather, tabler, heroicons}: string-replace every
    occurrence of "currentColor" with the target hex. These are stroke-based
    icons; replacing currentColor handles both stroke="currentColor" and the
    rare fill="currentColor" dot/circle variant without touching fill="none".
  - source == "simple-icons" (brand logos, monochrome path, no color attribute):
    inject fill="<hex>" into the opening <svg ...> tag so the root fill
    cascades to all child paths.

Role-to-color mapping:
  - primaryIcon    -> teal "#2dd4bf"
  - supportingIcon -> slate "#94a3b8"
  - brandBadge     -> near-white "#f1f5f9"

Reference: https://www.remotion.dev/docs/cli/render
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ..config import (
    END_HOLD_SECONDS,
    PIPELINE_DIR,
    PROCESSING_DIR,
    REMOTION_DIR,
    REPO_ROOT,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_HEIGHT_VERTICAL,
    VIDEO_WIDTH,
    VIDEO_WIDTH_VERTICAL,
    lang_suffix,
)
from ..models import SolutionRecord
from ..storyboard_normalize import normalize_scenes

log = logging.getLogger(__name__)

# ── SVG library path ───────────────────────────────────────────────────────

_SVG_LIBRARY_DIR = PIPELINE_DIR / "assets" / "svg-library"
_SVG_MANIFEST_PATH = _SVG_LIBRARY_DIR / "manifest.json"

# ── Color constants for icon roles ────────────────────────────────────────
# primaryIcon -> teal (brand accent, matches BRAND.accent in Remotion)
# supportingIcon -> slate (matches BRAND.textSecondary in Remotion)
# brandBadge -> near-white (legible on dark card, matches BRAND.textPrimary)
_COLOR_PRIMARY = "#2dd4bf"
_COLOR_SUPPORTING = "#94a3b8"
_COLOR_BRAND_BADGE = "#f1f5f9"
# Danger red for the primary icon on hook/problem beats, so an alert/warning icon
# on a danger-coded scene reads alarming (not success-teal). Mirrors the emotional
# color convention used everywhere else (Scene.tsx accent by scene_type).
_COLOR_DANGER = "#f87171"
_PROBLEM_SCENE_TYPES = ("hook", "problem")


def _load_svg_manifest() -> dict[str, dict]:
    """Load manifest.json once and return a dict keyed by id."""
    if not _SVG_MANIFEST_PATH.exists():
        raise RuntimeError(
            f"[6000] SVG manifest not found: {_SVG_MANIFEST_PATH}. "
            "Expected assets/svg-library/manifest.json inside the pipeline dir."
        )
    entries = json.loads(_SVG_MANIFEST_PATH.read_text(encoding="utf-8"))
    return {e["id"]: e for e in entries}


def _recolor_svg(svg_text: str, source: str, color: str) -> str:
    """Return a recolored copy of the SVG string.

    Recolor strategy by source:
    - lucide, feather, tabler, heroicons: replace every occurrence of
      "currentColor" with the target hex (handles stroke="currentColor"
      and fill="currentColor"; does not touch fill="none").
    - simple-icons: inject fill="<color>" into the opening <svg ...> tag
      so the root fill cascades to all child path elements.
    """
    source = source.lower()
    if source in ("lucide", "feather", "tabler", "heroicons"):
        return svg_text.replace("currentColor", color)
    if source == "simple-icons":
        # Insert fill="<color>" into the first <svg tag.
        # Matches <svg followed by anything up to the first >.
        # We add the attribute right after the opening <svg to be safe.
        return re.sub(r"(<svg\b)", rf'\1 fill="{color}"', svg_text, count=1)
    # Unknown source: attempt currentColor replacement as best effort
    log.warning("[6000] Unknown SVG source %r; attempting currentColor replace", source)
    return svg_text.replace("currentColor", color)


def _stage_icon_svg(
    manifest_lookup: dict[str, dict],
    icon_id: str,
    color: str,
    svg_out_dir: Path,
    slug: str,
) -> str | None:
    """Resolve a manifest id, recolor the SVG, stage it, return public-relative path.

    Returns None (and logs a warning) if the id is not in the manifest.
    The public-relative path is "<slug>/svg/<id>.svg".
    """
    entry = manifest_lookup.get(icon_id)
    if entry is None:
        log.warning(
            "[6000] iconScene: manifest id %r not found -- skipping this icon",
            icon_id,
        )
        return None

    src_svg_path = _SVG_LIBRARY_DIR / entry["path"]
    if not src_svg_path.exists():
        log.warning(
            "[6000] iconScene: SVG file not found for id %r at %s -- skipping",
            icon_id,
            src_svg_path,
        )
        return None

    svg_text = src_svg_path.read_text(encoding="utf-8")
    recolored = _recolor_svg(svg_text, entry["source"], color)

    dst_path = svg_out_dir / f"{icon_id}.svg"
    dst_path.write_text(recolored, encoding="utf-8")

    # public-relative path for Remotion staticFile()
    return f"{slug}/svg/{icon_id}.svg"


def _stage_illustration_svg(
    manifest_lookup: dict[str, dict],
    illustration_id: str,
    svg_out_dir: Path,
    slug: str,
) -> tuple[str | None, bool]:
    """Resolve an illustration manifest id, copy the pre-recolored SVG, return
    (public_relative_path, needs_light_bg).

    No recolor is applied; illustrations are pre-recolored at import time with
    the brand teal accent already baked in via color="#2dd4bf" on the SVG root.

    Returns (None, True) and logs a warning if the id is not found.
    The public-relative path is "<slug>/svg/<id>.svg".
    """
    entry = manifest_lookup.get(illustration_id)
    if entry is None:
        log.warning(
            "[6000] illustrationScene: manifest id %r not found -- skipping",
            illustration_id,
        )
        return None, True

    if entry.get("category") != "illustration":
        log.warning(
            "[6000] illustrationScene: manifest id %r has category=%r (expected 'illustration') -- skipping",
            illustration_id,
            entry.get("category"),
        )
        return None, True

    src_svg_path = _SVG_LIBRARY_DIR / entry["path"]
    if not src_svg_path.exists():
        log.warning(
            "[6000] illustrationScene: SVG file not found for id %r at %s -- skipping",
            illustration_id,
            src_svg_path,
        )
        return None, True

    dst_path = svg_out_dir / f"{illustration_id}.svg"
    shutil.copy2(src_svg_path, dst_path)

    needs_light_bg: bool = entry.get("needs_light_bg", True)
    return f"{slug}/svg/{illustration_id}.svg", needs_light_bg


def _resolve_illustration_scenes(
    scenes: list,
    slug: str,
    public_slug_dir: Path,
) -> None:
    """For every illustrationScene in scenes, resolve illustrationId to a staged SVG.

    Mutates each scene's visual.params in-place:
    - Resolves illustrationId -> illustrationSrc
    - Sets needsLightBg from the manifest entry
    - Removes illustrationId after resolution
    - Copies the pre-recolored SVG into public_slug_dir/svg/<id>.svg

    Scenes referencing missing or non-illustration manifest IDs receive a graceful
    fallback: illustrationSrc is set to "" so the component renders but shows
    nothing rather than crashing. A warning is logged for every missing id.
    """
    illustration_ids_needed = set()
    for scene in scenes:
        visual = scene.get("visual") if isinstance(scene, dict) else None
        if not isinstance(visual, dict):
            continue
        params = visual.get("params") if isinstance(visual, dict) else None
        if not isinstance(params, dict):
            continue
        if params.get("template") != "illustrationScene":
            continue
        ill_id = params.get("illustrationId")
        if ill_id:
            illustration_ids_needed.add(ill_id)

    if not illustration_ids_needed:
        return

    manifest_lookup = _load_svg_manifest()
    svg_out_dir = public_slug_dir / "svg"
    svg_out_dir.mkdir(parents=True, exist_ok=True)

    staged_count = 0
    for scene in scenes:
        visual = scene.get("visual") if isinstance(scene, dict) else None
        if not isinstance(visual, dict):
            continue
        params = visual.get("params") if isinstance(visual, dict) else None
        if not isinstance(params, dict):
            continue
        if params.get("template") != "illustrationScene":
            continue

        ill_id = params.pop("illustrationId", None)
        if ill_id:
            src, needs_light_bg = _stage_illustration_svg(
                manifest_lookup, ill_id, svg_out_dir, slug
            )
            if src is not None:
                params["illustrationSrc"] = src
                params["needsLightBg"] = needs_light_bg
                staged_count += 1
            else:
                params.setdefault("illustrationSrc", "")
                params.setdefault("needsLightBg", True)
        elif "illustrationSrc" not in params:
            params["illustrationSrc"] = ""

    log.info("[6000] Staged %d illustration SVG(s) -> %s", staged_count, svg_out_dir)


def _resolve_icon_scenes(
    scenes: list,
    slug: str,
    public_slug_dir: Path,
) -> None:
    """For every iconScene in scenes, resolve manifest IDs to staged SVG paths.

    Mutates each scene's visual.params in-place:
    - Resolves primaryIconId -> primaryIconSrc
    - Resolves each id in supportingIconIds -> supportingIconSrcs
    - Removes the *Id fields after resolution
    - Stages recolored SVG files into public_slug_dir/svg/<id>.svg

    Scenes that reference missing manifest IDs receive a graceful fallback:
    the missing *Src field is omitted and the scene can still render if the
    component receives an empty string (Remotion <Img> will show nothing but
    not crash). A warning is logged for every missing id.
    """
    # Collect ids from any iconScene before loading the manifest
    icon_ids_needed = set()
    for scene in scenes:
        visual = scene.get("visual") if isinstance(scene, dict) else None
        if not isinstance(visual, dict):
            continue
        params = visual.get("params") if isinstance(visual, dict) else None
        if not isinstance(params, dict):
            continue
        if params.get("template") != "iconScene":
            continue
        primary_id = params.get("primaryIconId")
        if primary_id:
            icon_ids_needed.add(primary_id)
        for sid in params.get("supportingIconIds") or []:
            icon_ids_needed.add(sid)

    if not icon_ids_needed:
        return

    manifest_lookup = _load_svg_manifest()
    svg_out_dir = public_slug_dir / "svg"
    svg_out_dir.mkdir(parents=True, exist_ok=True)

    for scene in scenes:
        visual = scene.get("visual") if isinstance(scene, dict) else None
        if not isinstance(visual, dict):
            continue
        params = visual.get("params") if isinstance(visual, dict) else None
        if not isinstance(params, dict):
            continue
        if params.get("template") != "iconScene":
            continue

        layout = params.get("layout", "single")
        is_brand_badge = layout == "brandBadge"
        tone = params.get("tone")

        # Determine the primary-icon color. Priority:
        #  1) brandBadge -> near-white.
        #  2) explicit semantic `tone` (set by the storyboard because it knows the
        #     icon's MEANING): success -> teal (a green check stays green even on a
        #     problem beat, e.g. an ironic "Backup OK"), danger -> red, neutral -> teal.
        #  3) else fall back to the scene's emotional accent: danger red on
        #     hook/problem (so an alert icon reads alarming), teal elsewhere.
        if is_brand_badge:
            primary_color = _COLOR_BRAND_BADGE
        elif tone == "success" or tone == "neutral":
            primary_color = _COLOR_PRIMARY
        elif tone == "danger":
            primary_color = _COLOR_DANGER
        elif scene.get("scene_type") in _PROBLEM_SCENE_TYPES:
            primary_color = _COLOR_DANGER
        else:
            primary_color = _COLOR_PRIMARY

        # Resolve primaryIconId
        primary_id = params.pop("primaryIconId", None)
        if primary_id:
            primary_src = _stage_icon_svg(
                manifest_lookup, primary_id, primary_color, svg_out_dir, slug
            )
            if primary_src is not None:
                params["primaryIconSrc"] = primary_src
            else:
                # Fallback: empty string so the component renders but shows nothing
                params.setdefault("primaryIconSrc", "")
        elif "primaryIconSrc" not in params:
            params["primaryIconSrc"] = ""

        # Resolve supportingIconIds
        supporting_ids = params.pop("supportingIconIds", None) or []
        if supporting_ids:
            supporting_srcs = []
            for sid in supporting_ids:
                src = _stage_icon_svg(
                    manifest_lookup, sid, _COLOR_SUPPORTING, svg_out_dir, slug
                )
                if src is not None:
                    supporting_srcs.append(src)
            params["supportingIconSrcs"] = supporting_srcs

    log.info("[6000] Staged %d icon SVG(s) -> %s", len(list(svg_out_dir.iterdir())), svg_out_dir)


def _remotion_concurrency() -> int:
    """Cores to give ONE Remotion render.

    Remotion defaults to about half the machine's cores per render. That is right for a
    render running alone and wrong the moment two run together next to a narration job,
    which is now the normal case. RDC_REMOTION_CONCURRENCY overrides for a one-off.
    """
    override = os.environ.get("RDC_REMOTION_CONCURRENCY")
    if override and override.isdigit() and int(override) > 0:
        return int(override)
    return max(1, min(4, (os.cpu_count() or 4) // 4))


def _check_remotion_installed() -> None:
    """Raise a clear error if remotion/node_modules is missing."""
    node_modules = REMOTION_DIR / "node_modules"
    remotion_pkg = node_modules / "remotion"
    if not remotion_pkg.exists():
        raise RuntimeError(
            f"Remotion node_modules not found at {node_modules}. "
            "Run: cd private/growth/video_pipeline/remotion && npm install"
        )


def _ffprobe_duration(mp4_path: Path) -> float:
    """Return the duration in seconds of an mp4 file using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(mp4_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    text = result.stdout.strip()
    if not text:
        # Fallback: try format-level duration
        result2 = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(mp4_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        text = result2.stdout.strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


async def run(record: SolutionRecord, *, lang: str = "en") -> Path:
    proc = PROCESSING_DIR / record.slug
    suf = lang_suffix(lang)
    # English keeps the bare slug everywhere (byte-identical to the original render);
    # other languages read the translated/re-synced artifacts, stage into an isolated
    # public dir, and emit a lang-suffixed mp4 so nothing clobbers the English output.
    public_name = record.slug if lang == "en" else f"{record.slug}__{lang}"
    audio_subdir = "audio" if lang == "en" else f"audio/{lang}"
    output_json = proc / f"6000_render{suf}.json"

    if output_json.exists() and output_json.stat().st_size > 0:
        log.info("  [6000] Using cached render")
        return output_json

    log.info("  [6000] Rendering video (%s)...", lang)

    _check_remotion_installed()

    # Read storyboard
    storyboard_path = proc / f"5000_storyboard{suf}.json"
    if not storyboard_path.exists():
        raise RuntimeError(f"[6000] Missing storyboard: {storyboard_path}")

    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))

    # Read the voiceover doc for caption word-timings, per-scene pause (used to
    # flag held crisis beats for the time-passing clock), and the AUDIO-TRUE
    # per-scene timing. All optional.
    voiceover_path = proc / f"4000_voiceover{suf}.json"
    word_timings: list[dict] = []
    pause_by_id: dict[int, float] = {}
    timing_by_id: dict[int, tuple[float, float]] = {}
    vo_total_seconds: float | None = None
    if voiceover_path.exists():
        try:
            vo = json.loads(voiceover_path.read_text(encoding="utf-8"))
            word_timings = vo.get("word_timings", []) or []
            for s in vo.get("scenes", []):
                pause_by_id[s.get("id")] = float(s.get("pause_after_seconds", 0.0) or 0.0)
                timing_by_id[s.get("id")] = (
                    float(s.get("start", 0.0) or 0.0),
                    float(s.get("duration", 0.0) or 0.0),
                )
            if "total_seconds" in vo:
                vo_total_seconds = float(vo["total_seconds"])
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            log.warning("[6000] Could not read 4000_voiceover.json for captions/pauses/timing")

    # Stage assets into remotion/public/<public_name>/ (per-lang dir for non-en)
    public_slug_dir = REMOTION_DIR / "public" / public_name
    public_slug_dir.mkdir(parents=True, exist_ok=True)

    # Stage the brand logo bug once into remotion/public/brand/logo.png (global,
    # not per-slug). Best-effort: a missing source just means no logo overlay.
    try:
        brand_dir = REMOTION_DIR / "public" / "brand"
        brand_dir.mkdir(parents=True, exist_ok=True)
        logo_dst = brand_dir / "logo.png"
        if not logo_dst.exists():
            logo_candidates = sorted((REPO_ROOT / "bin" / "assets").glob("logo_white-*.png"))
            if logo_candidates:
                shutil.copy2(logo_candidates[0], logo_dst)
                log.info("[6000] Staged brand logo -> %s", logo_dst)
            else:
                log.info("[6000] No brand logo source found; skipping logo bug")
    except Exception as exc:  # noqa: BLE001
        log.warning("[6000] Logo staging failed (%s); continuing", exc)

    # Audio: processing/<slug>/<audio_subdir>/voiceover.mp3 (per-lang for non-en)
    src_audio = proc / audio_subdir / "voiceover.mp3"
    if not src_audio.exists():
        raise RuntimeError(f"[6000] Missing voiceover: {src_audio}")
    dst_audio = public_slug_dir / "voiceover.mp3"
    shutil.copy2(src_audio, dst_audio)
    log.info(f"  [6000] Staged audio -> {dst_audio}")

    # Build props JSON with public/-relative asset paths.
    # Remotion staticFile() resolves paths relative to remotion/public/.
    # Reference: https://www.remotion.dev/docs/staticfile
    props = dict(storyboard)
    props["audio"] = f"{public_name}/voiceover.mp3"
    # Remove legacy illustration field if present (v1 storyboards)
    props.pop("illustration", None)

    # Canonicalize each scene's visual so the Remotion dispatcher (which switches
    # on visual.params.template, a discriminated union) always finds a populated
    # params with its discriminator. Handles both the nested agent shape and the
    # FLAT shape (param fields directly on visual, no params object) that some
    # models emit; an undefined params would crash the renderer.
    normalize_scenes(props.get("scenes", []))

    # Resolve iconScene manifest IDs to staged, recolored SVG files.
    # Must run AFTER template normalization so every iconScene params has
    # params.template == "iconScene" already set.
    _resolve_icon_scenes(props.get("scenes", []), public_name, public_slug_dir)

    # Resolve illustrationScene manifest IDs to staged pre-recolored SVG files.
    # Must run AFTER template normalization (same reason as iconScene above).
    # NOTE: stockVideo `videoSrc` (e.g. "<slug>/clips/N.mp4") is kept as-is and shared
    # from the English public dir (Remotion staticFile is global to public/).
    _resolve_illustration_scenes(props.get("scenes", []), public_name, public_slug_dir)

    # Language drives text direction and font selection in the renderer.
    props["lang"] = lang

    # Stage bundled fonts. For Arabic this is a HARD failure, not the best-effort the
    # logo staging uses: Chrome does not error on a missing glyph, it substitutes a
    # last-resort face and draws tofu boxes, so a missing font would publish a broken
    # Arabic video with a zero exit code the whole way.
    if lang == "ar":
        fonts_src = PIPELINE_DIR / "assets" / "fonts"
        fonts_dst = REMOTION_DIR / "public" / "fonts"
        fonts_dst.mkdir(parents=True, exist_ok=True)
        for name in ("NotoSansArabic-Regular.ttf", "NotoSansArabic-Bold.ttf"):
            src_font = fonts_src / name
            if not src_font.exists():
                raise RuntimeError(
                    f"[6000] Arabic render needs {src_font}, which is missing. "
                    f"See assets/fonts/README.md; do NOT render Arabic without it."
                )
            shutil.copy2(src_font, fonts_dst / name)
        log.info("  [6000] Staged Arabic fonts -> %s", fonts_dst)

    # Lock render constants to canonical config values
    props["fps"] = VIDEO_FPS
    props["width"] = VIDEO_WIDTH
    props["height"] = VIDEO_HEIGHT

    # Make the render AUDIO-TRUE: take per-scene start/duration and total_seconds
    # from 4000_voiceover (measured from the synthesized waveform) rather than from
    # the storyboard, whose values were copied by hand by an agent and drift.
    #
    # This is the same id-keyed join step_translate.resync_storyboard_timing does
    # for localized renders, applied here so it covers ENGLISH too. Before this,
    # English timing lived only in the Opus-written storyboard, so any change to
    # the audio timeline required a paid storyboard regeneration to take effect.
    # Applied BEFORE the END_HOLD extension below, which must remain the last word
    # on the final scene's duration.
    if timing_by_id:
        missing = []
        for scene in props.get("scenes") or []:
            t = timing_by_id.get(scene.get("id"))
            if t is None:
                missing.append(scene.get("id"))
                continue
            scene["start"], scene["duration"] = t
        if vo_total_seconds is not None:
            props["total_seconds"] = vo_total_seconds
        if missing:
            log.warning(
                "  [6000] No audio timing for scene(s) %s; kept storyboard values",
                ", ".join(str(m) for m in missing),
            )
        log.info(
            "  [6000] Synced %d scene(s) to audio-true timing (total=%.2fs)",
            len(timing_by_id) - len(missing),
            props.get("total_seconds", 0.0),
        )

    # Extend the last scene and total duration so the final CTA holds on
    # screen after narration ends, giving viewers time to read the card.
    scenes_list = props.get("scenes") or []
    if scenes_list:
        last_scene = max(scenes_list, key=lambda s: s.get("start", 0))
        last_scene["duration"] = last_scene.get("duration", 0) + END_HOLD_SECONDS
    props["total_seconds"] = props.get("total_seconds", 0) + END_HOLD_SECONDS
    log.info(
        "  [6000] Applied END_HOLD_SECONDS=%.1f -> total_seconds=%.1f",
        END_HOLD_SECONDS,
        props["total_seconds"],
    )

    # Word-synced captions: convert absolute-second word timings to absolute
    # frames. END_HOLD only extends the final scene's tail, so earlier caption
    # timings stay valid.
    captions_prop = []
    for w in word_timings:
        try:
            captions_prop.append({
                "word": str(w["word"]),
                "startFrame": round(float(w["start_sec"]) * VIDEO_FPS),
                "endFrame": round(float(w["end_sec"]) * VIDEO_FPS),
                # Which scene this word belongs to. Act-level synthesis removed the
                # inter-scene silence that used to force a caption line break at every
                # cut, so without this a line straddles a visual cut.
                "sceneId": w.get("scene_id"),
            })
        except (KeyError, TypeError, ValueError):
            continue
    props["captions"] = captions_prop
    if captions_prop:
        log.info("  [6000] Captions: %d word(s)", len(captions_prop))

    # Flag held crisis beats (hook/problem with a deliberate pause >= 1.0s) so the
    # renderer shows the time-passing clock instead of a frozen frame.
    for scene in props.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        if scene.get("scene_type") in ("hook", "problem") and pause_by_id.get(scene.get("id"), 0.0) >= 1.0:
            scene["showClock"] = True

    props_path = public_slug_dir / "props.json"
    props_path.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"  [6000] Wrote props -> {props_path}")

    # Output path
    video_dir = proc / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    mp4_path = video_dir / f"{record.slug}.{lang}.mp4"

    # Shell out to Remotion CLI.
    # Exact syntax from: https://www.remotion.dev/docs/cli/render
    #   npx remotion render <entry> <composition-id> <output> --props=<file>
    # cwd must be REMOTION_DIR so staticFile() resolves public/ correctly.
    #
    # --concurrency and --gl are BOUNDS, not tuning. Localized renders now run
    # concurrently with each other and alongside a GPU narration job (main.py phase B),
    # and Remotion's default concurrency is roughly half the machine's cores PER RENDER,
    # so two unbounded renders oversubscribe the box and starve the narration process's
    # own CPU work. --gl=swangle pins headless Chrome to SwiftShader, a SOFTWARE
    # rasterizer, keeping it off the very GPU the narration needs -- the same reason
    # tutorial renders leave RDC_TUTORIAL_HWENC at 0. Do NOT "upgrade" this to angle-egl
    # or vulkan: those are the hardware paths and put the render back on the contended
    # device. Valid values are pinned by the installed renderer
    # (@remotion/renderer/dist/client.d.ts:14 -- swangle, angle, egl, swiftshader,
    # vulkan, angle-egl).
    render_bounds = [
        f"--concurrency={_remotion_concurrency()}",
        "--gl=swangle",
    ]
    cmd = [
        "npx", "remotion", "render",
        "src/index.ts",
        "SolutionVideo",
        str(mp4_path.resolve()),
        f"--props={props_path.resolve()}",
        "--log=verbose",
        *render_bounds,
    ]

    log.info(f"  [6000] Running: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        cwd=str(REMOTION_DIR),
        capture_output=False,  # let stdout/stderr stream to the caller's console
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"[6000] Remotion render failed (exit {result.returncode}). "
            f"Check the output above for details."
        )

    if not mp4_path.exists():
        raise RuntimeError(f"[6000] Render claimed success but output not found: {mp4_path}")

    # Collect stats
    file_bytes = mp4_path.stat().st_size
    duration_s = _ffprobe_duration(mp4_path)

    # ── Vertical 9:16 render (best-effort) ──────────────────────────────────
    # Same props with dimensions swapped, rendered through the SolutionVideoVertical
    # composition (scenes adapt via useOrientation). A failure here logs and does NOT
    # fail the run; the landscape video + QA are already complete.
    output_vertical: str | None = None
    try:
        vprops = dict(props)
        vprops["width"] = VIDEO_WIDTH_VERTICAL
        vprops["height"] = VIDEO_HEIGHT_VERTICAL
        vprops_path = public_slug_dir / "props.vertical.json"
        vprops_path.write_text(json.dumps(vprops, ensure_ascii=False, indent=2), encoding="utf-8")
        vmp4_path = video_dir / f"{record.slug}.vertical.{lang}.mp4"
        vcmd = [
            "npx", "remotion", "render",
            "src/index.ts",
            "SolutionVideoVertical",
            str(vmp4_path.resolve()),
            f"--props={vprops_path.resolve()}",
            "--log=verbose",
            *render_bounds,
        ]
        log.info(f"  [6000] Running vertical: {' '.join(vcmd)}")
        vresult = subprocess.run(vcmd, cwd=str(REMOTION_DIR), capture_output=False, check=False)
        if vresult.returncode == 0 and vmp4_path.exists():
            output_vertical = f"video/{vmp4_path.name}"
            log.info(
                f"  [6000] Vertical render complete: {vmp4_path.name} "
                f"({vmp4_path.stat().st_size / 1_048_576:.1f} MB)"
            )
        else:
            log.warning(f"  [6000] Vertical render failed (exit {vresult.returncode}); continuing")
    except Exception as exc:  # noqa: BLE001
        log.warning(f"  [6000] Vertical render error ({exc}); continuing")

    render_record = {
        "slug": record.slug,
        "lang": lang,
        "output": f"video/{record.slug}.{lang}.mp4",
        "output_vertical": output_vertical,
        "duration_seconds": duration_s,
        "width": VIDEO_WIDTH,
        "height": VIDEO_HEIGHT,
        "fps": VIDEO_FPS,
        "bytes": file_bytes,
        "rendered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    output_json.write_text(
        json.dumps(render_record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    log.info(
        f"  [6000] Render complete: {mp4_path.name} "
        f"({file_bytes / 1_048_576:.1f} MB, {duration_s:.1f}s)"
    )
    return output_json
