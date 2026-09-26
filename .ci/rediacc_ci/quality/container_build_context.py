"""Every Cloudflare Container image in a wrangler config builds from a context that holds what its Dockerfile copies.

WHY. `workers/proxy/wrangler.toml` named `image = "./Dockerfile"` and nothing else, so wrangler built from `workers/proxy/` while the Dockerfile copies `packages/*` from the repo root. The image could never build, and nothing noticed: CI never runs deploy-proxy, and wrangler's `--dry-run` does not build container images. The first real deploy (2026-09-24, W7P5-a M-live item 1) stopped at `"/packages/cli": not found`.

WHAT IT CHECKS. For each `[[containers]]` entry whose `image` is a Dockerfile path, in every tracked `wrangler*.toml`: the context is `image_build_context` when set, else the Dockerfile's directory (wrangler's default). Every `COPY`/`ADD` source that is not from another stage (`--from=`) and is not a URL must exist under that context, globs included.

Exit 0 clean, 1 on findings, 2 when the gate's own controls fail (controls_first convention).
"""

from __future__ import annotations

import glob
import pathlib
import shlex
import subprocess
import sys
import tempfile
import tomllib

from rediacc_ci import paths
from rediacc_ci.controls import controls_first


def copy_sources(dockerfile_text: str) -> list[str]:
    """The local sources of every COPY/ADD instruction, continuation lines joined."""
    joined = dockerfile_text.replace("\\\n", " ")
    out: list[str] = []
    for raw in joined.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if parts[0].upper() not in ("COPY", "ADD") or len(parts) < 2:
            continue
        args = shlex.split(parts[1])
        if any(a.startswith("--from") for a in args):
            continue
        words = [a for a in args if not a.startswith("--")]
        out.extend(w for w in words[:-1] if "://" not in w)
    return out


def missing(context: pathlib.Path, sources: list[str]) -> list[str]:
    return [s for s in sources if not glob.glob(str(context / s))]


def findings(root: pathlib.Path) -> list[str]:
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "*wrangler*.toml"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    out: list[str] = []
    for rel in tracked:
        cfg_path = root / rel
        cfg = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
        for c in cfg.get("containers") or []:
            image = str(c.get("image") or "")
            if not image.endswith("Dockerfile"):
                continue
            dockerfile = (cfg_path.parent / image).resolve()
            context = (
                (cfg_path.parent / c["image_build_context"]).resolve()
                if c.get("image_build_context")
                else dockerfile.parent
            )
            gone = missing(context, copy_sources(dockerfile.read_text(encoding="utf-8")))
            out.extend(
                "%s: container %s copies %s, which is not under its build context %s"
                % (
                    rel,
                    c.get("class_name", "?"),
                    s,
                    context.relative_to(root) if context.is_relative_to(root) else context,
                )
                for s in gone
            )
    return out


def selftest() -> bool:
    """True when a control FAILED."""
    failed = False
    text = "FROM node\nCOPY --from=build /x /x\nCOPY package.json \\\n  lib/ ./\nADD https://e.x/f /f\n"
    if copy_sources(text) != ["package.json", "lib/"]:
        print("✗ control: COPY source parsing is wrong: %r" % copy_sources(text), file=sys.stderr)
        failed = True
    with tempfile.TemporaryDirectory() as d:
        ctx = pathlib.Path(d)
        (ctx / "package.json").write_text("{}")
        if missing(ctx, ["package.json"]):
            print("✗ control: a present source read as missing", file=sys.stderr)
            failed = True
        if missing(ctx, ["packages/cli"]) != ["packages/cli"]:
            print(
                "✗ control: an absent source (the 2026-09-24 defect) was not reported",
                file=sys.stderr,
            )
            failed = True
    return failed


def main(argv: list[str]) -> int:
    rc = controls_first("container build context", selftest)
    if rc or "--selftest" in argv:
        return rc
    found = findings(paths.repo_root())
    if found:
        print("✗ %d container build-context finding(s):" % len(found), file=sys.stderr)
        for f in found:
            print("    %s" % f, file=sys.stderr)
        return 1
    print(
        "✓ every wrangler container image builds from a context holding what its Dockerfile copies"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
