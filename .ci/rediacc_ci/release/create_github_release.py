"""Port of `.ci/scripts/release/create-github-release.sh`.

Creates the GitHub Release for a version and uploads every built asset to it. Runs LAST in cd-v2.yml, after edge deploys, smoke tests and post-publish install validation, so a broken release never gets a Release page pointing at it.

REFUSES RATHER THAN PUBLISHES AN EMPTY RELEASE. `dist/{cli,packages}` matching
nothing means the download step upstream produced nothing, and a Release with no assets looks published and installs nothing. That refusal is the one behaviour here worth more than the `gh` call itself, so it keeps its own exit-1 path and its `::error::` line on STDOUT (the twin's plain `echo`, not `>&2`; reproduced because a workflow annotation is parsed off either stream and
moving it would change what a `2>/dev/null` caller sees).

THE ASSET ORDER IS BASH'S GLOB ORDER, AND `sorted(glob(...))` REPRODUCES IT.
`shopt -s globstar nullglob; assets=(dist/cli/**/* dist/packages/**/*)` sorts
each pattern's matches independently and concatenates, so this port sorts each pattern's matches independently and concatenates too, rather than sorting the union. Driven rather than reasoned about, including the case that separates a plain byte sort from a pre-order directory walk: with `dist/cli/v1/a.bin`, `dist/cli/v1-x` and `dist/cli/v1.y` present, bash emits `v1`, `v1-x`,
`v1.y`, `v1/a.bin` -- `-` (0x2D) and `.` (0x2E) both below `/` (0x2F) -- which is the byte order `sorted()` gives and is NOT the order a walk emitting a directory's children immediately after the directory would give.

ONE KNOWN LOCALE DIVERGENCE, NAMED RATHER THAN PAPERED OVER: bash sorts glob results with `strcoll`, so under a UTF-8 locale whose collation ignores punctuation the twin can order two asset paths differently from this port's codepoint sort. It changes only the order of positional arguments handed to
`gh release create`, which uploads a set; the differential pins `LC_ALL=C` on
both sides so the comparison measures the port rather than the locale.

DIRECTORIES ARE FILTERED OUT AFTER THE GLOB, not during it, matching the twin's
`for f in "${assets[@]}"; do [[ -f "$f" ]] && files+=("$f"); done`. `-f` follows
symlinks and is true only for a regular file, which is what `os.path.isfile` does, so a symlink to a directory is dropped by both and a symlink to a file is kept by both.

THE BODY COMES FROM THE AUTHOR'S `Release-Note:` TRAILERS, NOT FROM `--generate-notes` (PLAN-release-notes RN5, D5-D8). The start tag is the newest `v*` tag older than this version that HAS a GitHub Release, read through the GitHub API and never from local tags; a tag between the two with no Release is an orphan, named in the body and folded into the range. The body is rendered by `release_notes.render_markdown` from one notes document: `--notes-json` (or `RELEASE_NOTES_JSON`) names the file `--write-notes-json` rendered earlier, `publish` uploads the same file to `cli/v<V>/release-notes.json` with `--upload-notes`, and a release with no file collects the range itself. A file whose `start_tag` is not the start tag read now is refused: its groups describe another range. A tag that already exists at a commit other than `GITHUB_SHA` is refused before `gh release create` (D7, the v2.4.0 shape). `--dry-run` prints the orphan warning, the body and the argv and writes nothing, and needs no built assets. `--print-orphan-warning` prints the `::warning::` of D7 and exits 0.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import awscli, common, gh_retry
from rediacc_ci.release import release_notes

SELF = "rediacc_ci.release.create_github_release"

# The twin `cd "$(get_repo_root)"`s, and `get_repo_root` (common.sh:205-210) resolves three levels up from `.ci/scripts/lib`. This file sits at `.ci/rediacc_ci/release/`, which is the same three levels.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# `dist/cli/**/* dist/packages/**/*`, in the twin's order.
ASSET_PATTERNS = ("dist/cli/**/*", "dist/packages/**/*")

NO_ASSETS = "::error::No release assets matched dist/{cli,packages}/**/*"

# Where the rendered body is written for `--notes-file`: relative to the repo root, outside both asset patterns, and the same path on every run.
BODY_REL = "dist/release-notes.md"
NOTES_KEY = "cli/v%s/release-notes.json"
IMMUTABLE = "public, max-age=31536000, immutable"
_SEMVER = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


class NotesError(RuntimeError):
    """The notes cannot be built or the release cannot go ahead; the message says why."""


def _require_cmd(name: str) -> int | None:
    """`require_cmd` (common.sh:141-147): log and exit 1, message byte-identical."""
    try:
        common.require_cmd(name)
    except common.RefusalError as exc:
        log.error(str(exc))
        return 1
    return None


def _require_var(name: str) -> str:
    """`${NAME:?message}`: unset AND empty both refuse, with exit 1.

    The wording is the port's, not bash's `<script>: line N: NAME: ...`; the exit code and the named variable are what the differential compares, as in every sibling port here.
    """
    value = os.environ.get(name)
    if not value:
        print("%s: %s must be set" % (SELF, name), file=sys.stderr)
        raise SystemExit(1)
    return value


def release_assets(root: str = _ROOT) -> list[str]:
    """Every regular file under `dist/cli` and `dist/packages`, in glob order.

    Exported for the differential, which drives it directly against fixture trees a subprocess comparison could only reach through `gh`'s argv.
    """
    files: list[str] = []
    for pattern in ASSET_PATTERNS:
        matched = sorted(glob.glob(os.path.join(root, pattern), recursive=True))
        files.extend(os.path.relpath(m, root) for m in matched if os.path.isfile(m))
    return files


def _failure_text(done: subprocess.CompletedProcess[str]) -> str | None:
    """None for success, else the text `gh_retry.is_transient` judges, so only a 5xx or a connection fault is retried."""
    return None if done.returncode == 0 else (done.stderr or "failed")


def _gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    """`gh <args>`, retried on a transient failure only (a 404 or an auth failure returns at once). Every caller here is a read."""
    return gh_retry.retry_transient(
        lambda: subprocess.run(
            ["gh", *args], cwd=_ROOT, capture_output=True, text=True, check=False
        ),
        _failure_text,
    )


def _semver(tag: str) -> tuple[int, int, int] | None:
    m = _SEMVER.match(tag)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def release_state(repo: str) -> tuple[list[str], list[str], str | None]:
    """(tags with a Release, every `v*` tag, the tag marked Latest), read through the GitHub API."""
    listed = _gh(
        ["release", "list", "--repo", repo, "--limit", "1000", "--json", "tagName,isLatest"]
    )
    if listed.returncode != 0:
        msg = "could not list the Releases of %s (rc=%d): %s" % (
            repo,
            listed.returncode,
            listed.stderr.strip(),
        )
        raise NotesError(msg)
    try:
        rows = json.loads(listed.stdout or "[]")
    except ValueError as exc:
        msg = "`gh release list` printed no JSON: %s" % exc
        raise NotesError(msg) from exc
    released = [str(r["tagName"]) for r in rows]
    latest = next((str(r["tagName"]) for r in rows if r.get("isLatest")), None)
    refs = _gh(["api", "--paginate", "repos/%s/git/matching-refs/tags/v" % repo, "--jq", ".[].ref"])
    if refs.returncode != 0:
        msg = "could not list the tags of %s (rc=%d): %s" % (
            repo,
            refs.returncode,
            refs.stderr.strip(),
        )
        raise NotesError(msg)
    tags = [line.removeprefix("refs/tags/") for line in refs.stdout.split() if line.strip()]
    return released, tags, latest


def start_tag(version: str, repo: str) -> tuple[str | None, list[str], str | None]:
    """(start tag, orphan tags, stable tag) for `version` (D5, D7): the newest older tag that has a Release, the older tags after it that have none, and the Release marked Latest."""
    released, tags, latest = release_state(repo)
    new = _semver("v" + version.removeprefix("v"))
    if new is None:
        msg = "version %r is not X.Y.Z" % version
        raise NotesError(msg)
    older = sorted(
        {t for t in [*tags, *released] if (v := _semver(t)) is not None and v < new},
        key=lambda t: _semver(t) or (0, 0, 0),
    )
    with_release = [t for t in older if t in released]
    start = with_release[-1] if with_release else None
    floor = (_semver(start) if start else None) or (-1, -1, -1)
    orphans = [t for t in older if t not in released and (_semver(t) or (0, 0, 0)) > floor]
    return start, orphans, latest


def orphan_warning(tag: str, version: str) -> str:
    """The workflow annotation of D7 for an orphan tag folded into `version`."""
    return "::warning::%s was tagged but not published; its changes are folded into v%s." % (
        tag,
        version.removeprefix("v"),
    )


def render_notes(
    version: str, repo: str, sha: str, notes_json: str | None
) -> tuple[dict, str | None]:
    """The notes document and the start tag it was built for."""
    start, orphans, latest = start_tag(version, repo)
    if notes_json:
        with open(notes_json, encoding="utf-8") as fh:
            doc = json.load(fh)
        if (doc.get("start_tag") or None) != start:
            msg = "%s was rendered for start tag %s, but the start tag now is %s" % (
                notes_json,
                doc.get("start_tag"),
                start,
            )
            raise NotesError(msg)
        doc["version"] = version.removeprefix("v")
        doc.setdefault("repo", repo)
        doc["orphans"] = orphans
        doc["stable"] = latest.removeprefix("v") if latest else None
        return doc, start
    if start is None:
        collection = release_notes.Collection(commits=[], notes=[], none_count=0, warnings=[])
    else:
        collection = release_notes.collect(start, sha, _ROOT)
        for warning in collection.warnings:
            log.warn(warning)
    return (
        release_notes.document(
            version, start or "", collection, orphans=orphans, stable=latest, repo=repo
        ),
        start,
    )


def tag_commit(repo: str, version: str) -> str | None:
    """The commit `v<version>` resolves to, or None when the tag does not exist. Any other failure raises: an unknown is never read as absent."""
    proc = _gh(["api", "repos/%s/commits/v%s" % (repo, version), "--jq", ".sha"])
    if proc.returncode == 0:
        return proc.stdout.strip() or None
    text = proc.stderr + proc.stdout
    if re.search(r"HTTP 404|Not Found|No commit found", text, re.IGNORECASE):
        return None
    msg = "could not resolve tag v%s (rc=%d): %s" % (version, proc.returncode, text.strip())
    raise NotesError(msg)


def upload_notes(path: str, version: str) -> None:
    """Write `cli/v<V>/release-notes.json` to the releases bucket, write-once: an existing object is kept."""
    endpoint = common.require_var("CLOUDFLARE_R2_ENDPOINT")
    env = dict(
        os.environ,
        AWS_ACCESS_KEY_ID=common.require_var("CLOUDFLARE_R2_ACCESS_KEY_ID"),
        AWS_SECRET_ACCESS_KEY=common.require_var("CLOUDFLARE_R2_SECRET_ACCESS_KEY"),
        AWS_DEFAULT_REGION="auto",
    )
    bucket = os.environ.get("RELEASES_BUCKET", "") or "releases"
    key = NOTES_KEY % version
    head = awscli.run(
        [
            awscli.AWS,
            "s3api",
            "head-object",
            "--bucket",
            bucket,
            "--key",
            key,
            "--endpoint-url",
            endpoint,
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if head.returncode == 0:
        log.info("%s already exists; kept (write-once)" % key)
        return
    if not re.search(r"404|Not Found", head.stderr, re.IGNORECASE):
        msg = "could not tell whether %s exists: %s" % (key, head.stderr.strip())
        raise NotesError(msg)
    put = awscli.run(
        [
            awscli.AWS,
            "s3",
            "cp",
            path,
            "s3://%s/%s" % (bucket, key),
            "--endpoint-url",
            endpoint,
            "--content-type",
            "application/json",
            "--cache-control",
            IMMUTABLE,
            "--no-progress",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if put.returncode != 0:
        msg = "upload of %s failed (rc=%d): %s" % (key, put.returncode, put.stderr.strip())
        raise NotesError(msg)
    log.info("uploaded %s" % key)


def _write_notes(args: argparse.Namespace, version: str, sha: str, repo: str) -> None:
    doc, _start = render_notes(version, repo, sha, None)
    with open(args.write_notes_json, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    if args.upload_notes:
        upload_notes(args.write_notes_json, version.removeprefix("v"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=SELF)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--notes-json", default=os.environ.get("RELEASE_NOTES_JSON") or None)
    parser.add_argument("--write-notes-json", default=None, metavar="PATH")
    parser.add_argument("--upload-notes", action="store_true")
    parser.add_argument("--print-orphan-warning", action="store_true")
    args = parser.parse_args(argv)
    if args.upload_notes and not args.write_notes_json:
        parser.error("--upload-notes needs --write-notes-json")
    refusal = _require_cmd("gh")
    if refusal is not None:
        return refusal
    version = _require_var("VERSION")
    github_sha = _require_var("GITHUB_SHA")
    github_repository = _require_var("GITHUB_REPOSITORY")

    try:
        if args.print_orphan_warning:
            _start, orphans, _latest = start_tag(version, github_repository)
            for tag in orphans:
                print(orphan_warning(tag, version))
            return 0
        if args.write_notes_json:
            _write_notes(args, version, github_sha, github_repository)
            return 0
        files = release_assets()
        if not files and not args.dry_run:
            print(NO_ASSETS)
            return 1
        doc, start = render_notes(version, github_repository, github_sha, args.notes_json)
        body = release_notes.render_markdown(doc)
        at = tag_commit(github_repository, version.removeprefix("v"))
    except (NotesError, release_notes.ReleaseNotesError, common.RefusalError) as exc:
        print("%s: %s" % (SELF, exc), file=sys.stderr)
        return 1
    if at is not None and at != github_sha:
        print(
            "::error::Tag v%s already exists at %s, not at %s. Refusing to release one version from two commits."
            % (version, at, github_sha)
        )
        return 1

    gh_argv = [
        "gh",
        "release",
        "create",
        "v%s" % version,
        "--title",
        "v%s" % version,
        "--target",
        github_sha,
        "--notes-file",
        BODY_REL,
        *(["--notes-start-tag", start] if start else []),
        # Latest means production; only mark_production moves it.
        "--latest=false",
        "--repo",
        github_repository,
        *files,
    ]
    if args.dry_run:
        for tag in doc.get("orphans") or ():
            print(orphan_warning(tag, version))
        print(body, end="")
        print("+ " + " ".join(gh_argv))
        return 0
    os.makedirs(os.path.join(_ROOT, os.path.dirname(BODY_REL)), exist_ok=True)
    with open(os.path.join(_ROOT, BODY_REL), "w", encoding="utf-8") as fh:
        fh.write(body)
    proc = subprocess.run(gh_argv, cwd=_ROOT, check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
