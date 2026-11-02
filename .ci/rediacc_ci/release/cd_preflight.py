"""Predict, BEFORE a merge or a release, the CD failures that today only show up after one (PLAN-cd-errors-in-ci W3).

READ-ONLY. Nothing here writes to R2, to git or to GitHub, except the homebrew dry-run's fetch of origin main in the tap. It reads live state through injected READERS and judges it with pure functions:

  (a) the release-state bijection NOW, live R2 sentinels against `git ls-remote --tags`, through the gate's own `release_state.assert_bijection`;
  (b) the bijection AFTER the next housekeeping runs and the release this merge triggers, from THIS checkout's keep rules (`retention_contract.tag_retention_plan` and `tracker_retention_plan`) applied to live state;
  (c) floor and pointer consistency: the contract-floor ratchet against the live sentinels, and each channel pointer through `release_state.assert_channel_pointer_tagged`;
  (d) the release version is neither tagged nor released (phase `pr`), or is sealed and not tagged elsewhere (phase `cd`);
  plus `homebrew` (`update_homebrew_tap --dry-run`, then the formula rewrite on a scratch copy, checked by an oracle that is not the rewrite's own awk) and `promotion` (Validate Promotion's object count at the measured copy rate, against its 20-minute cap).

THE VERSION UNDER RELEASE IS EXCLUDED FROM (a), and this is load-bearing. Every CD run starts with that version's sentinel already sealed (ci.yml `finalize-release-sentinel`) and its tag not yet created (cd-v2 init's `Create version tag`), so a bijection that judged it would red every release. `--release-version` names it, and (d) is where that version IS judged, with a rule per phase.

THE LIVE SENTINEL LIST IS PASSED TO THE TAG PLAN. `test_release_retention_contract.py` found that the matching keep window alone does not guarantee the bijection (a promotion between an upload and a housekeeping run moves `in_walk` past a candidate R2 still holds); housekeeping's per-tag sentinel probe is what saves it, and the projection's equivalent is the full listing.

UNKNOWN IS NEVER FINE. A reader that cannot answer (no `aws`, no credentials, R2 or GitHub unreachable, a malformed object) raises `UnreadableError`, and every check that needed it reports UNCHECKED, which exits non-zero like DRIFT. The same goes for an answer with nothing in it: zero sentinels, zero release tags or an empty edge channel means the preflight is not seeing the release state, so its green would mean nothing. `release_state.list_sentinels` is NOT called for this reason: it swallows a failed `aws` into an empty list. Its argv and its parse are reused, with the exit code read.

SEVERITY, from the plan's tunables: current drift (a, c, d) is blocking; projected drift (b) is a WARNING plus an annotation, because the hard refusal for it lives in housekeeping itself. Validate Promotion warns at 80% of its cap and fails at 100%.

REPLAY. `--json` prints the state every reader returned; `--state <file>` feeds the readers from such a snapshot instead of R2 and GitHub, which is how the 2026-10-07 state is replayed on a live runner. `--dry-run` prints the reads it would make and judges nothing; it is not a verdict and must never be what a workflow step runs.

Usage:
  PYTHONPATH=.ci python3 -m rediacc_ci.release.cd_preflight --phase pr|cd --release-version X.Y.Z
      [--checks a,b,c,d,homebrew,promotion] [--remote origin] [--release-sha SHA]
      [--checksums-dir DIR] [--state FILE] [--json] [--dry-run]

R2 credentials come from `CLOUDFLARE_R2_ACCESS_KEY_ID`, `CLOUDFLARE_R2_SECRET_ACCESS_KEY` and `CLOUDFLARE_R2_ENDPOINT` (locally: `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile <p> -- ...`), and the bucket from `RELEASES_BUCKET` through `release_state.bucket()`.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from typing import Any

from rediacc_ci import paths
from rediacc_ci.core import awscli
from rediacc_ci.deploy.simulate_promotion import CHANNEL_DIRS
from rediacc_ci.quality import release_state
from rediacc_ci.release import retention_contract, update_homebrew_tap

SELF = "cd-preflight"

# The checks, in report order. `--checks` selects a subset; an unselected check is still PRINTED as SKIPPED, so a narrowed run cannot read as a full one.
CHECK_IDS = ("a", "b", "c", "d", "homebrew", "promotion")
CHECK_TITLES = {
    "a": "bijection now",
    "b": "bijection after the next housekeeping runs and this release",
    "c": "floor and channel pointers",
    "d": "release version",
    "homebrew": "homebrew formula",
    "promotion": "Validate Promotion budget",
}

OK = "OK"
WARN = "WARN"
DRIFT = "DRIFT"
UNCHECKED = "UNCHECKED"
SKIPPED = "SKIPPED"
FAILING = (DRIFT, UNCHECKED)

PHASES = ("pr", "cd")

# Validate Promotion: 1,123 objects took 11.2-14.6 min on main (6f17924d1), so 75 objects/min is the measured lower bound (1,123 objects in 14.6 min is 77/min); the watchdog cap is 20 min (`JOB_BUDGET_CAPS`, `validate-promote`).
PROMOTION_CHANNEL = "edge"
PROMOTION_RATE_PER_MIN = 75
PROMOTION_CAP_MIN = 20.0
PROMOTION_WARN_FRACTION = 0.8

CREDENTIAL_VARS = (
    "CLOUDFLARE_R2_ACCESS_KEY_ID",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY",
    "CLOUDFLARE_R2_ENDPOINT",
)

MIN_SHA_PREFIX = 7
_SHA_PREFIX_RE = re.compile(r"^[0-9a-fA-F]{%d,40}$" % MIN_SHA_PREFIX)
_VERSION_RE = re.compile(r"^v?([0-9]+\.[0-9]+\.[0-9]+)$")


class UnreadableError(Exception):
    """A reader could not answer. Never a "no": every check that needed the answer reports UNCHECKED."""

    def __init__(self, reader: str, why: str) -> None:
        super().__init__("%s: %s" % (reader, why))
        self.reader = reader
        self.why = why


@dataclasses.dataclass(frozen=True)
class Result:
    check: str
    status: str
    lines: tuple[str, ...]


def bare(version: str) -> str:
    """`v1.2.3` and `1.2.3` as `1.2.3`."""
    return version.removeprefix("v")


def tag(version: str) -> str:
    """`v1.2.3` and `1.2.3` as `v1.2.3`."""
    return "v" + bare(version)


def newest_first(names: Sequence[str]) -> list[str]:
    """Tags newest first, the order housekeeping hands `tag_retention_plan`. Release tags by version; every other tag ahead of them. Only the position WITHIN each group matters to the plan, so this stands in for housekeeping's dates."""
    release = sorted(
        (n for n in names if retention_contract.is_release_tag(n)),
        key=release_state.version_key,
        reverse=True,
    )
    other = sorted(n for n in names if not retention_contract.is_release_tag(n))
    return other + release


# --------------------------------------------------------------------------- state ---------------------------------------------------------------------------


@dataclasses.dataclass
class Readers:
    """The live state, one callable per question, each raising `UnreadableError` rather than guessing: `sentinels()` is the strict-semver `vX.Y.Z` of every `cli/v*/.released` on R2, `tags()` maps every remote tag to the commit it points at (peeled), `tracker()` is `cli/versions.json` newest first as `X.Y.Z`, `pointer(channel, file)` is the `vX.Y.Z` a `cli/<channel>/<file>` pointer advertises, `channel_objects(channel)` is how many objects Validate Promotion copies for that channel, and `ratchet()` is the contract-floor file's version ("" when it holds none)."""

    sentinels: Callable[[], list[str]]
    tags: Callable[[], dict[str, str]]
    tracker: Callable[[], list[str]]
    pointer: Callable[[str, str], str]
    channel_objects: Callable[[str], int]
    ratchet: Callable[[], str]


class State:
    """Every answer, asked once. A failure is cached too, so two checks needing one reader name the same cause, and `snapshot()` is the replayable record of what was seen."""

    def __init__(self, readers: Readers) -> None:
        self._readers = readers
        self._cache: dict[str, Any] = {}

    def _ask(self, key: str, fn: Callable[[], Any]) -> Any:
        if key not in self._cache:
            try:
                self._cache[key] = fn()
            except UnreadableError as exc:
                self._cache[key] = exc
        value = self._cache[key]
        if isinstance(value, UnreadableError):
            raise value
        return value

    def sentinels(self) -> list[str]:
        return self._ask("sentinels", self._readers.sentinels)

    def tags(self) -> dict[str, str]:
        return self._ask("tags", self._readers.tags)

    def release_tags(self) -> list[str]:
        return release_state.sort_unique_versions(
            [t for t in self.tags() if retention_contract.is_release_tag(t)]
        )

    def tracker(self) -> list[str]:
        return self._ask("tracker", self._readers.tracker)

    def pointer(self, channel: str, name: str) -> str:
        return self._ask(
            "pointers/%s/%s" % (channel, name), lambda: self._readers.pointer(channel, name)
        )

    def stable(self) -> str:
        """The stable version as `in_walk` reads it, `X.Y.Z`. An unreadable manifest is UnreadableError here, never "" (which would silently hold everything)."""
        return bare(self.pointer("stable", "manifest.json"))

    def channel_objects(self, channel: str) -> int:
        return self._ask(
            "channel_objects/%s" % channel, lambda: self._readers.channel_objects(channel)
        )

    def ratchet(self) -> str:
        return self._ask("ratchet", self._readers.ratchet)

    def snapshot(self) -> dict[str, Any]:
        """The answers in `--state` form; an unreadable one is recorded as `{"unchecked": why}`, which a replay reads back as UnreadableError."""
        out: dict[str, Any] = {}
        for key, value in sorted(self._cache.items()):
            node = out
            parts = key.split("/", 1)
            if len(parts) == 2:
                node = out.setdefault(parts[0], {})
            node[parts[-1]] = (
                {"unchecked": value.why} if isinstance(value, UnreadableError) else value
            )
        return out


def replay_readers(state: dict[str, Any]) -> Readers:
    """Readers answering from a `--state` snapshot. A key the snapshot lacks, or one recorded as unchecked, is UnreadableError."""

    def get(*keys: str) -> Any:
        node: Any = state
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                raise UnreadableError("/".join(keys), "not in the replayed state")
            node = node[key]
        if isinstance(node, dict) and "unchecked" in node:
            # Verbatim, so a live run's --json and its replay report the same reason.
            raise UnreadableError("/".join(keys), str(node["unchecked"]))
        return node

    return Readers(
        sentinels=lambda: [str(v) for v in get("sentinels")],
        tags=lambda: {str(k): str(v) for k, v in dict(get("tags")).items()},
        tracker=lambda: [str(v) for v in get("tracker")],
        pointer=lambda ch, name: str(get("pointers", "%s/%s" % (ch, name))),
        channel_objects=lambda ch: int(get("channel_objects", ch)),
        ratchet=lambda: str(get("ratchet")),
    )


# --------------------------------------------------------------------------- live readers ---------------------------------------------------------------------------

Runner = Callable[[list[str], "dict[str, str] | None"], subprocess.CompletedProcess]


def run_process(argv: list[str], env: dict[str, str] | None) -> subprocess.CompletedProcess:
    """`subprocess.run` (an `aws` argv through `core.awscli`), with a missing binary as exit 127 rather than an exception."""
    try:
        return awscli.run(argv, capture_output=True, text=True, env=env)
    except FileNotFoundError:
        return subprocess.CompletedProcess(argv, 127, "", "%s: command not found\n" % argv[0])
    except awscli.AwsCliMissingError as exc:
        return subprocess.CompletedProcess(argv, 127, "", "%s\n" % exc)


def _tail(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else "<no output>"


class LiveReaders:
    """R2 through the `aws` CLI (the same argv `release_state` runs) and tags through `git ls-remote`."""

    def __init__(
        self,
        root: pathlib.Path,
        remote: str,
        environ: dict[str, str],
        runner: Runner = run_process,
    ) -> None:
        self.root = root
        self.remote = remote
        self.environ = environ
        self.runner = runner
        self.bucket = release_state.bucket()

    def _aws_env(self, reader: str) -> tuple[dict[str, str], str]:
        # Each name read by its literal, so the env registry records three names rather than one opaque read.
        given = {
            "CLOUDFLARE_R2_ACCESS_KEY_ID": self.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID", ""),
            "CLOUDFLARE_R2_SECRET_ACCESS_KEY": self.environ.get(
                "CLOUDFLARE_R2_SECRET_ACCESS_KEY", ""
            ),
            "CLOUDFLARE_R2_ENDPOINT": self.environ.get("CLOUDFLARE_R2_ENDPOINT", ""),
        }
        missing = [name for name in CREDENTIAL_VARS if not given[name]]
        if missing:
            raise UnreadableError(
                reader,
                "%s not set, so R2 cannot be asked. Locally: PYTHONPATH=.ci python3 -m "
                "rediacc_ci.core.bws_env exec --profile <profile with R2> -- <this command>"
                % ", ".join(missing),
            )
        env = dict(self.environ)
        env["AWS_ACCESS_KEY_ID"] = given["CLOUDFLARE_R2_ACCESS_KEY_ID"]
        env["AWS_SECRET_ACCESS_KEY"] = given["CLOUDFLARE_R2_SECRET_ACCESS_KEY"]
        env["AWS_DEFAULT_REGION"] = "auto"
        return env, given["CLOUDFLARE_R2_ENDPOINT"]

    def _aws(self, reader: str, args: list[str]) -> subprocess.CompletedProcess:
        env, endpoint = self._aws_env(reader)
        proc = self.runner([awscli.AWS, *args, "--endpoint-url", endpoint], env)
        if proc.returncode == 127:
            raise UnreadableError(
                reader,
                "the aws CLI is not installed (install the pin: %s)" % awscli.INSTALL_HINT,
            )
        return proc

    def sentinels(self) -> list[str]:
        proc = self._aws(
            "sentinels",
            [
                "s3api",
                "list-objects-v2",
                "--bucket",
                self.bucket,
                "--prefix",
                "cli/v",
                "--query",
                "Contents[?ends_with(Key, `/%s`)].Key" % release_state.SENTINEL_KEY,
                "--output",
                "text",
            ],
        )
        if proc.returncode != 0:
            raise UnreadableError(
                "sentinels", "aws exited %d: %s" % (proc.returncode, _tail(proc.stderr))
            )
        return parse_sentinels(proc.stdout)

    def tags(self) -> dict[str, str]:
        proc = self.runner(["git", "ls-remote", "--tags", self.remote], None)
        if proc.returncode != 0:
            raise UnreadableError(
                "tags",
                "git ls-remote --tags %s exited %d: %s"
                % (self.remote, proc.returncode, _tail(proc.stderr)),
            )
        return parse_ls_remote(proc.stdout)

    def _object(self, reader: str, key: str) -> str:
        proc = self._aws(reader, ["s3", "cp", "s3://%s/%s" % (self.bucket, key), "-"])
        if proc.returncode != 0:
            raise UnreadableError(
                reader, "aws s3 cp %s exited %d: %s" % (key, proc.returncode, _tail(proc.stderr))
            )
        return proc.stdout

    def tracker(self) -> list[str]:
        text = self._object("tracker", "cli/versions.json")
        try:
            value = json.loads(text)
        except ValueError as exc:
            raise UnreadableError("tracker", "cli/versions.json is not JSON (%s)" % exc) from exc
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise UnreadableError("tracker", "cli/versions.json is not a JSON list of versions")
        return [bare(v) for v in value]

    def pointer(self, channel: str, name: str) -> str:
        reader = "pointers/%s/%s" % (channel, name)
        version = release_state.pointer_version(self._object(reader, "cli/%s/%s" % (channel, name)))
        if not version:
            raise UnreadableError(reader, "the pointer names no version")
        return version

    def channel_objects(self, channel: str) -> int:
        """`aws s3 ls --recursive` per channel directory, the listing `simulate_promotion` copies from. Exit 1 with nothing on either stream is an empty prefix (simulate_promotion fact 3); any other failure is UnreadableError."""
        reader = "channel_objects/%s" % channel
        total = 0
        for directory in CHANNEL_DIRS:
            prefix = "%s/%s/" % (directory, channel)
            proc = self._aws(
                reader, ["s3", "ls", "s3://%s/%s" % (self.bucket, prefix), "--recursive"]
            )
            empty = proc.returncode == 1 and not proc.stdout.strip() and not proc.stderr.strip()
            if proc.returncode != 0 and not empty:
                raise UnreadableError(
                    reader,
                    "aws s3 ls %s exited %d: %s" % (prefix, proc.returncode, _tail(proc.stderr)),
                )
            total += sum(1 for line in proc.stdout.splitlines() if line.strip())
        return total

    def ratchet(self) -> str:
        path = self.root / release_state.FLOOR_FILE_REL
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise UnreadableError("ratchet", "%s unreadable (%s)" % (path, exc.strerror)) from exc
        return parse_ratchet(text)

    def readers(self) -> Readers:
        return Readers(
            sentinels=self.sentinels,
            tags=self.tags,
            tracker=self.tracker,
            pointer=self.pointer,
            channel_objects=self.channel_objects,
            ratchet=self.ratchet,
        )


def parse_sentinels(text: str) -> list[str]:
    """`release_state.list_sentinels`' parse of `--output text`: tabs to records, the sentinel key shape, then strict semver."""
    pattern = re.compile(
        release_state.SENTINEL_LINE.pattern % ("cli", re.escape(release_state.SENTINEL_KEY))
    )
    found = []
    for line in text.replace("\t", "\n").splitlines():
        match = pattern.match(line.strip())
        if match and release_state.STRICT_SEMVER.match(match.group(1)):
            found.append(match.group(1))
    return release_state.sort_unique_versions(found)


def parse_ls_remote(text: str) -> dict[str, str]:
    """`<sha>\\trefs/tags/<name>[^{}]` lines as name -> commit. The peeled `^{}` line of an annotated tag wins, because it names the commit."""
    out: dict[str, str] = {}
    peeled: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 2 or not parts[1].startswith("refs/tags/"):
            continue
        name = parts[1][len("refs/tags/") :]
        if name.endswith("^{}"):
            peeled[name[:-3]] = parts[0]
        else:
            out[name] = parts[0]
    out.update({name: sha for name, sha in peeled.items() if name in out})
    return out


def parse_ratchet(text: str) -> str:
    for line in text.splitlines():
        if release_state.STRICT_SEMVER.match(line.strip()):
            return line.strip()
    return ""


# --------------------------------------------------------------------------- the judgements ---------------------------------------------------------------------------


def bijection(
    sentinels: Sequence[str], tags: Sequence[str], in_flight: str, ratchet: str
) -> tuple[list[str], int]:
    """`release_state.assert_bijection` with the ratchet pinned to `ratchet`: the floor file is written into a scratch root, which is the first place the gate looks. `RSV_FLOOR_FILE` and `RSV_GRANDFATHER_BEFORE` still override it, exactly as they override the gate."""
    with tempfile.TemporaryDirectory(prefix="cd-preflight-") as tmp:
        floor = pathlib.Path(tmp) / release_state.FLOOR_FILE_REL
        floor.parent.mkdir(parents=True)
        floor.write_text(ratchet + "\n", encoding="utf-8")
        semver = [t for t in tags if retention_contract.is_release_tag(t)]
        return release_state.assert_bijection(
            release_state.sort_unique_versions(list(sentinels)),
            release_state.sort_unique_versions(semver),
            in_flight,
            pathlib.Path(tmp),
        )


def _seen(state: State) -> tuple[list[str], list[str]]:
    """Sentinels and release tags, refusing an empty answer: zero of either means the preflight is not seeing the release state."""
    sentinels = state.sentinels()
    if not sentinels:
        raise UnreadableError(
            "sentinels",
            "R2 listed ZERO cli sentinels; the preflight is not seeing the release state",
        )
    tags = state.release_tags()
    if not tags:
        raise UnreadableError(
            "tags",
            "the remote listed ZERO release tags; the preflight is not seeing the release state",
        )
    return release_state.sort_unique_versions(sentinels), tags


def healed_by_release(state: State, sentinels: Sequence[str], version: str) -> set[str]:
    """The sentinel versions the release of `version` prunes itself (`tracker_retention_plan`, the rule upload_to_r2 applies). Empty when no release follows: `version` must be newer than every other sentinel, which housekeeping's `0.0.0` never is. Empty too when the tracker or the stable pointer cannot be read, so the drift stays blocking."""
    others = [tag(v) for v in sentinels if tag(v) != tag(version)]
    if not others or release_state.sort_unique_versions([*others, tag(version)])[-1] != tag(
        version
    ):
        return set()
    try:
        plan = retention_contract.tracker_retention_plan(
            [bare(v) for v in state.tracker()], bare(version), state.stable()
        )
    except UnreadableError:
        return set()
    return {tag(v) for v in plan.pruned}


def check_a(state: State, version: str, phase: str, release_sha: str) -> Result:
    """The bijection now, excluding the version under release (module docstring).

    Drift the release itself heals is a WARNING, not a DRIFT: a sentinel without its tag that the release's own prune removes would otherwise refuse the one run that repairs it (measured 2026-10-08: v1.3.2, and (b) projecting "holds" after the release of v2.2.1). Drift on any version the release keeps stays blocking."""
    del phase, release_sha
    sentinels, tags = _seen(state)
    ratchet = state.ratchet()
    lines, code = bijection(sentinels, tags, tag(version), ratchet)
    shape = (
        "%d sentinels, %d release tags, ratchet %s, excluding %s (the version under release)"
        % (
            len(sentinels),
            len(tags),
            ratchet or "<none>",
            tag(version),
        )
    )
    if code:
        healed = healed_by_release(state, sentinels, version)
        if healed:
            kept = [v for v in sentinels if tag(v) not in healed]
            _, kept_code = bijection(kept, tags, tag(version), ratchet)
            if not kept_code:
                note = "the release of %s prunes %s itself, so this drift heals in that release" % (
                    tag(version),
                    ", ".join(release_state.sort_unique_versions(sorted(healed))),
                )
                return Result("a", WARN, (shape, *lines, note))
    return Result("a", DRIFT if code else OK, (shape, *lines))


def project(
    sentinels: Sequence[str],
    tags: Sequence[str],
    tracker: Sequence[str],
    stable: str,
    version: str,
) -> list[tuple[str, set[str], set[str], str]]:
    """The states after housekeeping, then the release of `version`, then housekeeping again: the two-run horizon, judged in both orders (a 03:00 run before the release and one after it).

    Each step is `(name, sentinels, tags, in_flight)`. Housekeeping deletes what `tag_retention_plan` calls DELETE, handed the full sentinel list. The release prunes `cli/v<V>/` (sentinel included) for each version `tracker_retention_plan` prunes, and seals and tags `version`. Before the release, `version` is in flight: in phase cd its sentinel is already sealed.
    """
    sealed = {tag(v) for v in sentinels}
    names = set(tags)
    steps: list[tuple[str, set[str], set[str], str]] = []

    def housekeeping(label: str, in_flight: str) -> None:
        plan = retention_contract.tag_retention_plan(
            newest_first(sorted(names)), stable=stable, sentinels=sorted(sealed)
        )
        names.difference_update(v.name for v in plan.delete)
        steps.append((label, set(sealed), set(names), in_flight))

    housekeeping("housekeeping before the release", tag(version))
    plan = retention_contract.tracker_retention_plan(
        [bare(v) for v in tracker], bare(version), stable
    )
    sealed.difference_update(tag(v) for v in plan.pruned)
    sealed.add(tag(version))
    names.add(tag(version))
    steps.append(("the release of %s" % tag(version), set(sealed), set(names), ""))
    housekeeping("housekeeping after the release", "")
    return steps


def check_b(state: State, version: str, phase: str, release_sha: str) -> Result:
    """Projected drift is a WARNING (plan tunables); an unreadable input is still UNCHECKED."""
    del phase, release_sha
    sentinels, release_tags = _seen(state)
    # EVERY remote tag, `production` included: the keep rule under test decides what a pointer tag costs, so filtering here would hide exactly the 10-07 defect.
    tags = sorted(state.tags())
    tracker = state.tracker()
    stable = state.stable()
    ratchet = state.ratchet()
    lines = [
        "projected from %d sentinels, %d release tags (%d tags in all), a %d-entry tracker, "
        "stable %s, keep %d"
        % (
            len(sentinels),
            len(release_tags),
            len(tags),
            len(tracker),
            stable,
            retention_contract.KEEP_RELEASES,
        )
    ]
    drift = False
    for label, sealed, names, in_flight in project(sentinels, tags, tracker, stable, version):
        found, code = bijection(sorted(sealed), sorted(names), in_flight, ratchet)
        if code:
            drift = True
            lines.append("after %s:" % label)
            lines.extend("  " + line for line in found)
        else:
            lines.append(
                "after %s: holds (%d sentinels, %d tags)" % (label, len(sealed), len(names))
            )
    return Result("b", WARN if drift else OK, tuple(lines))


def check_c(state: State, version: str, phase: str, release_sha: str) -> Result:
    del phase, release_sha
    sentinels, tags = _seen(state)
    ratchet = state.ratchet()
    key = release_state.version_key
    lines: list[str] = []
    status = OK
    newest, oldest = sentinels[-1], sentinels[0]
    if not ratchet:
        lines.append(
            "ratchet: %s holds no version; the bijection floor is the oldest sentinel alone"
            % release_state.FLOOR_FILE_REL
        )
        status = WARN
    elif key(ratchet) > key(newest):
        lines.append(
            "DRIFT ratchet %s is newer than the newest sentinel %s, so every sentinel is below "
            "the floor and the bijection compares NOTHING" % (ratchet, newest)
        )
        status = DRIFT
    elif key(ratchet) > key(oldest):
        below = [v for v in sentinels if key(v) < key(ratchet)]
        lines.append(
            "ratchet %s is above %d sentinel(s) (%s): those are outside the bijection"
            % (ratchet, len(below), ", ".join(below))
        )
        status = WARN
    elif key(ratchet) < key(oldest):
        lines.append(
            "ratchet %s lags the oldest sentinel %s: `release.advance_contract_floor` writes the "
            "new floor into the working tree, and it is committed in the next PR"
            % (ratchet, oldest)
        )
        status = WARN
    else:
        lines.append("ratchet %s, sentinels %s..%s" % (ratchet, oldest, newest))

    advertised: dict[str, str] = {}
    for channel in release_state.CHANNELS:
        latest = state.pointer(channel, "latest.json")
        manifest = state.pointer(channel, "manifest.json")
        found, code = release_state.assert_channel_pointer_tagged(
            channel, latest, manifest, tags, tag(version)
        )
        lines.extend(found)
        if code:
            status = DRIFT
        advertised[channel] = manifest
    edge = advertised["edge"]
    if edge != tag(version) and edge not in sentinels:
        lines.append("DRIFT edge: the pointer names %s, which has NO sentinel on R2" % edge)
        status = DRIFT
    if key(advertised["stable"]) > key(edge):
        lines.append(
            "DRIFT stable %s is NEWER than edge %s; stable is only ever promoted from edge"
            % (advertised["stable"], edge)
        )
        status = DRIFT
    return Result("c", status, tuple(lines))


def check_d(state: State, version: str, phase: str, release_sha: str) -> Result:
    """Phase pr: the predicted version has neither tag nor sentinel, and is newer than every release. Phase cd: its sentinel is sealed, and a tag, if one exists, is at `release_sha` when that is given."""
    if phase == "cd" and release_sha and not _SHA_PREFIX_RE.match(release_sha):
        raise UnreadableError(
            "release-sha",
            "%r is not a hex commit prefix of at least %d characters; a shorter stub matches "
            "almost any tag sha" % (release_sha, MIN_SHA_PREFIX),
        )
    sentinels, tags = _seen(state)
    remote = state.tags()
    name = tag(version)
    has_tag, has_sentinel = name in remote, name in sentinels
    lines = [
        "%s: tag %s, sentinel %s (phase %s)"
        % (
            name,
            "present" if has_tag else "absent",
            "sealed" if has_sentinel else "absent",
            phase,
        )
    ]
    status = OK
    if phase == "pr":
        if has_tag:
            lines.append(
                "DRIFT %s is already TAGGED; the release this merge triggers would collide with it"
                % name
            )
            status = DRIFT
        if has_sentinel:
            lines.append("DRIFT %s is already RELEASED (cli/%s/.released exists)" % (name, name))
            status = DRIFT
        newest = release_state.sort_unique_versions([*sentinels, *tags])[-1]
        key = release_state.version_key
        if newest != name and key(name) < key(newest):
            lines.append(
                "DRIFT %s is older than %s, the newest release; the version prediction is behind"
                % (name, newest)
            )
            status = DRIFT
    else:
        if not has_sentinel:
            lines.append(
                "DRIFT CD for %s, but cli/%s/.released is not sealed; ci.yml "
                "finalize-release-sentinel never ran for it" % (name, name)
            )
            status = DRIFT
        if has_tag and release_sha and not remote[name].lower().startswith(release_sha.lower()):
            lines.append(
                "DRIFT %s already exists at %s, not at the release commit %s; init's Create "
                "version tag refuses one version from two commits"
                % (name, remote[name], release_sha)
            )
            status = DRIFT
        elif not has_tag:
            lines.append("init's Create version tag creates %s" % name)
    return Result("d", status, tuple(lines))


# --------------------------------------------------------------------------- homebrew ---------------------------------------------------------------------------


def formula_path(root: pathlib.Path) -> pathlib.Path:
    return root / update_homebrew_tap.TAP_SUBMODULE / update_homebrew_tap.HOMEBREW_FORMULA_PATH


def synthetic_checksums() -> dict[str, str]:
    """A distinct 64-hex value per platform: exercises the rewrite and its placement, not the PR's binaries."""
    return {
        name: hashlib.sha256(name.encode()).hexdigest() for name in update_homebrew_tap.BINARY_NAMES
    }


def read_checksums(directory: pathlib.Path) -> dict[str, str]:
    """One checksum per platform from `<name>.sha256` (first field) or the binary itself. A platform with neither is UnreadableError."""
    out: dict[str, str] = {}
    for name in update_homebrew_tap.BINARY_NAMES:
        sidecar, binary = directory / ("%s.sha256" % name), directory / name
        if sidecar.is_file():
            fields = sidecar.read_text(encoding="utf-8").split()
            if not fields:
                raise UnreadableError("checksums", "%s is empty" % sidecar)
            out[name] = fields[0]
        elif binary.is_file():
            out[name] = hashlib.sha256(binary.read_bytes()).hexdigest()
        else:
            raise UnreadableError("checksums", "neither %s nor %s exists" % (sidecar, binary))
    return out


def formula_findings(
    original: str, rewritten: str, version: str, checksums: dict[str, str]
) -> list[str]:
    """The rewritten formula, judged WITHOUT the rewrite's awk: each binary's `url` line must be followed by a `sha256` line carrying THAT binary's checksum, the version line must name `version`, and nothing else may change."""
    found: list[str] = []
    lines = rewritten.splitlines()
    if not re.search(r'^\s*version "%s"\s*$' % re.escape(bare(version)), rewritten, re.MULTILINE):
        found.append('the formula does not say version "%s" after the rewrite' % bare(version))
    for name, digest in checksums.items():
        at = [i for i, ln in enumerate(lines) if re.search(r'url ".*/%s"' % re.escape(name), ln)]
        if len(at) != 1:
            found.append("%d url lines name %s; expected exactly one" % (len(at), name))
            continue
        following = next((ln for ln in lines[at[0] + 1 :] if "sha256" in ln), "")
        if digest not in following:
            found.append(
                "the sha256 after %s's url is %r, not its checksum" % (name, following.strip())
            )
    before = original.splitlines()
    if len(before) != len(lines):
        found.append("the rewrite changed the line count (%d -> %d)" % (len(before), len(lines)))
    else:
        changed = [b for a, b in zip(before, lines, strict=True) if a != b]
        stray = [ln for ln in changed if not re.match(r'^\s*(version|sha256) "', ln)]
        if stray:
            found.append(
                "the rewrite changed a line that is neither version nor sha256: %r"
                % stray[0].strip()
            )
    return found


def rewrite_formula(formula_text: str, version: str, checksums: dict[str, str]) -> tuple[int, str]:
    """`update_homebrew_tap.update_formula` on a scratch copy: the real sed and awk, never the tap."""
    with tempfile.TemporaryDirectory(prefix="cd-preflight-brew-") as tmp:
        work = pathlib.Path(tmp)
        formula = work / "formula.rb"
        formula.write_text(formula_text, encoding="utf-8")
        sums = work / "sums"
        sums.mkdir()
        for name, digest in checksums.items():
            (sums / ("%s.sha256" % name)).write_text("%s  %s\n" % (digest, name), encoding="utf-8")
        rc = update_homebrew_tap.update_formula(sums, formula, bare(version), dry_run=False)
        return rc, formula.read_text(encoding="utf-8")


DryRun = Callable[[str], subprocess.CompletedProcess]


def homebrew_dry_run(root: pathlib.Path) -> DryRun:
    """`update_homebrew_tap --version X --dry-run` as a subprocess. Its dry run still fetches `origin main` inside the tap (its own docstring), which moves a remote-tracking ref there and nothing else."""

    def run(version: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(root / ".ci")
        # The caller matches git's English "unknown revision" text, so the locale is pinned.
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        env.pop("LANGUAGE", None)
        argv = [sys.executable, "-m", "rediacc_ci.release.update_homebrew_tap"]
        return run_process([*argv, "--version", bare(version), "--dry-run"], env)

    return run


def check_homebrew(root: pathlib.Path, version: str, checksums_dir: str, dry_run: DryRun) -> Result:
    formula = formula_path(root)
    if not formula.is_file():
        raise UnreadableError(
            "homebrew",
            "%s is not checked out (git submodule update --init %s), so the formula cannot be "
            "judged" % (formula.relative_to(root), update_homebrew_tap.TAP_SUBMODULE),
        )
    lines: list[str] = []
    proc = dry_run(version)
    output = proc.stderr + proc.stdout
    if proc.returncode != 0 and "unknown revision" in output and "origin/main" in output:
        # The tap's fetch is allowed to fail (`|| true`), so an unreachable GitHub only matters when the tap holds no origin/main at all: the checkout cannot be read, which is not formula drift.
        raise UnreadableError(
            "homebrew",
            "the tap has no origin/main and the fetch did not supply one: %s" % _tail(output),
        )
    if proc.returncode != 0:
        return Result(
            "homebrew",
            DRIFT,
            (
                "update_homebrew_tap --dry-run exited %d: %s"
                % (proc.returncode, _tail(proc.stderr + proc.stdout)),
            ),
        )
    lines.append("update_homebrew_tap --version %s --dry-run: rc 0" % bare(version))
    if checksums_dir:
        checksums = read_checksums(pathlib.Path(checksums_dir))
        lines.append("checksums from %s" % checksums_dir)
    else:
        checksums = synthetic_checksums()
        lines.append(
            "SYNTHETIC checksums (no --checksums-dir): the rewrite and its placement are "
            "exercised, the PR's binaries are not"
        )
    original = formula.read_text(encoding="utf-8")
    rc, rewritten = rewrite_formula(original, version, checksums)
    if rc != 0:
        return Result("homebrew", DRIFT, (*lines, "the formula rewrite exited %d" % rc))
    found = formula_findings(original, rewritten, version, checksums)
    if found:
        return Result("homebrew", DRIFT, (*lines, *("DRIFT formula: " + f for f in found)))
    lines.append("formula rewrite to %s places all %d checksums" % (bare(version), len(checksums)))
    return Result("homebrew", OK, tuple(lines))


# --------------------------------------------------------------------------- promotion ---------------------------------------------------------------------------


def promotion_minutes(objects: int, rate: int = PROMOTION_RATE_PER_MIN) -> float:
    return objects / rate


def check_promotion(state: State) -> Result:
    objects = state.channel_objects(PROMOTION_CHANNEL)
    dirs = "|".join(CHANNEL_DIRS)
    if objects == 0:
        raise UnreadableError(
            "channel_objects/%s" % PROMOTION_CHANNEL,
            "R2 listed ZERO objects under {%s}/%s/; the projection would measure nothing"
            % (dirs, PROMOTION_CHANNEL),
        )
    minutes = promotion_minutes(objects)
    share = minutes / PROMOTION_CAP_MIN
    line = "%d objects under {%s}/%s/ at %d/min -> %.1f min of the %.0f min cap (%.0f%%)" % (
        objects,
        dirs,
        PROMOTION_CHANNEL,
        PROMOTION_RATE_PER_MIN,
        minutes,
        PROMOTION_CAP_MIN,
        share * 100,
    )
    if share >= 1:
        return Result(
            "promotion",
            DRIFT,
            (line, "DRIFT Validate Promotion would exceed its watchdog cap on main"),
        )
    if share >= PROMOTION_WARN_FRACTION:
        return Result(
            "promotion",
            WARN,
            (
                line,
                "Validate Promotion is past %.0f%% of its cap" % (PROMOTION_WARN_FRACTION * 100),
            ),
        )
    return Result("promotion", OK, (line,))


# --------------------------------------------------------------------------- the run ---------------------------------------------------------------------------

StateCheck = Callable[[State, str, str, str], Result]

STATE_CHECKS: dict[str, StateCheck] = {"a": check_a, "b": check_b, "c": check_c, "d": check_d}


def run_checks(
    state: State,
    *,
    version: str,
    phase: str,
    selected: Sequence[str] = CHECK_IDS,
    release_sha: str = "",
    root: pathlib.Path | None = None,
    checksums_dir: str = "",
    dry_run: DryRun | None = None,
) -> list[Result]:
    """Every check in report order. An UnreadableError becomes that check's UNCHECKED, and an unselected check a visible SKIPPED."""
    results: list[Result] = []
    for check in CHECK_IDS:
        if check not in selected:
            results.append(Result(check, SKIPPED, ("not selected by --checks",)))
            continue
        try:
            if check in STATE_CHECKS:
                results.append(STATE_CHECKS[check](state, version, phase, release_sha))
            elif check == "homebrew":
                base = root or paths.repo_root()
                runner = dry_run or homebrew_dry_run(base)
                results.append(check_homebrew(base, version, checksums_dir, runner))
            else:
                results.append(check_promotion(state))
        except UnreadableError as exc:
            results.append(Result(check, UNCHECKED, ("UNCHECKED %s: %s" % (exc.reader, exc.why),)))
    return results


def exit_code(results: Sequence[Result]) -> int:
    return 1 if any(r.status in FAILING for r in results) else 0


def summary(results: Sequence[Result], version: str, phase: str) -> str:
    statuses = (OK, WARN, DRIFT, UNCHECKED, SKIPPED)
    counts = ", ".join("%d %s" % (sum(1 for r in results if r.status == s), s) for s in statuses)
    return "%s (phase %s, %s): %d checks: %s -> %s" % (
        SELF,
        phase,
        tag(version),
        len(results),
        counts,
        "FAIL" if exit_code(results) else "PASS",
    )


def annotation(result: Result) -> str:
    """The text of a result's annotation: its finding lines, never its shape or its passing steps. Measured live 2026-10-08: quoting the last two lines made (b)'s warning read "holds" twice while the drift sat three lines above."""
    found = [ln.strip() for ln in result.lines if ln.lstrip().startswith(("DRIFT", "UNCHECKED"))]
    return "; ".join(found[:3] or [result.lines[-1].strip()])


def render(results: Sequence[Result], version: str, phase: str) -> list[str]:
    out: list[str] = []
    for r in results:
        out.append("[%s] %s: %s" % (r.check, r.status, CHECK_TITLES[r.check]))
        out.extend("    " + line for line in r.lines)
        if r.status in FAILING:
            out.append("::error title=cd-preflight (%s)::%s" % (r.check, annotation(r)))
        elif r.status == WARN:
            out.append("::warning title=cd-preflight (%s)::%s" % (r.check, annotation(r)))
    out.append(summary(results, version, phase))
    return out


def dry_run_plan(phase: str, version: str, selected: Sequence[str], remote: str) -> list[str]:
    bucket = release_state.bucket()
    reads = [
        "aws s3api list-objects-v2 --bucket %s --prefix cli/v (the sentinels)" % bucket,
        "git ls-remote --tags %s" % remote,
        "aws s3 cp s3://%s/cli/versions.json -" % bucket,
        *(
            "aws s3 cp s3://%s/cli/%s/%s -" % (bucket, ch, f)
            for ch in release_state.CHANNELS
            for f in ("latest.json", "manifest.json")
        ),
        *(
            "aws s3 ls s3://%s/%s/%s/ --recursive" % (bucket, d, PROMOTION_CHANNEL)
            for d in CHANNEL_DIRS
        ),
        "read %s" % release_state.FLOOR_FILE_REL,
        "update_homebrew_tap --version %s --dry-run, then the formula rewrite on a scratch copy"
        % bare(version),
    ]
    return [
        "%s DRY-RUN (phase %s, %s, checks %s): these reads would be made:"
        % (SELF, phase, tag(version), ",".join(selected)),
        *("  " + r for r in reads),
        "DRY-RUN: no reader ran and nothing was judged; this is NOT a verdict.",
    ]


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="cd_preflight", description="Predict CD failures.")
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument(
        "--release-version",
        required=True,
        help="the version this merge (pr) or this CD run (cd) releases",
    )
    parser.add_argument("--checks", default=",".join(CHECK_IDS))
    parser.add_argument("--remote", default="origin", help="git remote or URL for ls-remote")
    parser.add_argument("--release-sha", default="", help="phase cd: the release tag's commit")
    parser.add_argument("--checksums-dir", default="", help="binaries or .sha256 sidecars")
    parser.add_argument("--state", default="", help="replay a --json state snapshot")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(list(argv))


def main(
    argv: Sequence[str] | None = None,
    *,
    readers: Readers | None = None,
    dry_run: DryRun | None = None,
) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    match = _VERSION_RE.match(args.release_version)
    if not match:
        print(
            "%s: --release-version must be X.Y.Z (got %r)" % (SELF, args.release_version),
            file=sys.stderr,
        )
        return 2
    version = match.group(1)
    selected = [c.strip() for c in args.checks.split(",") if c.strip()]
    if not selected or any(c not in CHECK_IDS for c in selected):
        print(
            "%s: --checks takes %s (got %r)" % (SELF, ",".join(CHECK_IDS), args.checks),
            file=sys.stderr,
        )
        return 2
    if args.dry_run:
        print("\n".join(dry_run_plan(args.phase, version, selected, args.remote)))
        return 0

    root = paths.repo_root()
    if readers is None:
        if args.state:
            try:
                snapshot = json.loads(pathlib.Path(args.state).read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                print("%s: --state %s unreadable (%s)" % (SELF, args.state, exc), file=sys.stderr)
                return 2
            readers = replay_readers(snapshot.get("state", snapshot))
        else:
            readers = LiveReaders(root, args.remote, dict(os.environ)).readers()
    state = State(readers)
    results = run_checks(
        state,
        version=version,
        phase=args.phase,
        selected=selected,
        release_sha=args.release_sha,
        root=root,
        checksums_dir=args.checksums_dir,
        dry_run=dry_run,
    )
    rc = exit_code(results)
    if args.json:
        payload = {
            "phase": args.phase,
            "release_version": version,
            "rc": rc,
            "results": [dataclasses.asdict(r) for r in results],
            "state": state.snapshot(),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("\n".join(render(results, version, args.phase)))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
