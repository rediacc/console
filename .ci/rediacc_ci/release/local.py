"""Publish an edge release from the local machine (box W2-B of agent/plans/PLAN-local-release.md).

    npm run release:local -- --channel edge [--dry-run] [--workers-only [--regions eu,us]]

npm consumes a `--dry-run` placed before `--`, so the flag goes after it: `npm run release:local -- --channel edge --dry-run`.

EDGE ONLY. Operator ruling ASKED:2026-10-27T09:45Z: "EU/ASIA/US stable should be asked! They're CI/CD only. BUT edge and bench could be released via agent or with CI/CD." `--channel stable` is refused here, with or without `--workers-only`, and names promote-stable.yml; stable is promoted only through CI/CD. cd-v2.yml keeps releasing edge on merge, so this entry is a second edge path, and the two share the release lock: the R2 sentinel `cli/v<V>/.released` and the tag/Release check of `check_existing_release`.

THE LAUNCH FORM. The npm script runs exactly the shape `release_run.entry_refusal` admits (.claude/rediacc_hooks/git/release_run.py, THE ENTRY INVOCATION): `PYTHONPATH="$PWD/.ci" PYTHONPYCACHEPREFIX=/dev/null /usr/bin/python3 -P -s -m rediacc_ci.release.local`. A real run refuses before anything else when this process is not that entry, because the release-run record it writes later would be refused anyway.

ONE DECLARATIVE TABLE. `STEPS` lists every step once: an id, a section, the bws profiles it runs under (none for most), an argv, and whether it can fail. `plan()` expands the per-region rows over the regions and keeps the `workers` rows only under `--workers-only` (plan decision 3). The sections, in order: version, gates, builds (in the release clone, each timed), assist (the local-release-assist dispatch), stage, seal (the sentinel, then the tag at once), publish, deploy (the Worker deploys, each account deploy behind `order.account_refusal` and each with a deploy record), smoke, release (tag-and-release), record.

THE LOCK HOLDS THROUGH THE RUN. The gates judge it once; a concurrent CD edge release can still seal or tag the same version while this run builds. So `lock-check` (the gates' own `local_gates.lock_refusals`, live) runs again before the first stage write and immediately before the seal, and a version taken mid-run stops the run before anything is published.

`can_fail` IS READ AFTER THE SEAL. Every step before the seal may fail and nothing sealed is left behind. After the seal, a failure that leaves `cli/v<V>/.released` with no tag `v<V>` is the CD run 37749637824 case, so the seal and the tag rows carry `can_fail=False`: the tag immediately follows the seal, and every step that can fail after the seal comes after the tag. A `can_fail=False` row is retried with backoff (`RETRY_BACKOFF`) before the run stops, which narrows the window and does not close it: a tag that still fails leaves the version sealed and untagged, and `sealed_untagged` then prints SEALED WITHOUT A TAG with the one recovery command. `test_release_local.py` and the local-release phase of `rediacc_ci.security.ci_workflow_invariants` (`npm run check:ci-workflow-invariants`) pin those invariants.

THE TAG IS THREE ROWS, ONE UNIT. The git-level pre-push hook admits the tag push only by the exact object id the release-run record lists, and an annotated tag's object id does not exist until the tag is made. So `tag-create` makes the local tag in the clone (`rediacc_ci.release.tag --create-only`, whose only stdout line is the oid), `tag-record` re-writes the release-run record (same run id and path, so REDIACC_RELEASE_RUN is unchanged) with `(clone, origin, refs/tags/v<V>, oid)`, and `tag-push` pushes `refs/tags/v<V>` only while it is still that oid (`--push-oid`). The record is first written with no push at all.

THE ASSIST (local-release-assist.yml, THE R2 CONTRACT in its header). As soon as the keyed renet set exists, `assist-stage-in` empties `staging/local-release/v<V>/` in WK_RELEASES_BUCKET (a stale `.complete` of an earlier attempt must never be read as this run's) and uploads `private-bin/` with `checksums.sha256`, every embedded renet checked against it first; then `assist-dispatch` starts the workflow while the other builds run. `assist-fetch` waits for `cli/.complete`, takes its run id only when the marker names this sha exactly and `gh run view` shows that id is this workflow on this sha, stops early when a dispatch of this sha created since the dispatch completed red, fetches the four SEAs into dist/cli (so SHA256SUMS covers them) and checks each against its `.sha256`. `assist-clean` removes the prefix at the end of stage, and `assist-clean-on-stop` (an `on_failure` row armed by `assist-stage-in`) removes it when the run stops anywhere after the stage-in, after `assist-cancel-on-stop` (armed by `assist-dispatch`) has cancelled this attempt's assist if it is still in flight. A marker whose run was created before this attempt's dispatch is an earlier attempt's, and `assist-fetch` waits past it.

PROVENANCE (plan decision 6). Sigstore needs the GitHub OIDC identity, so `provenance` writes `dist/cli/SHA256SUMS` over every Release asset (`create_github_release.release_assets`: `dist/cli/**` and `dist/packages/**`) and its armoured detached signature `dist/cli/SHA256SUMS.asc`, made with the release GPG key of the `release-local` profile in a throwaway GNUPGHOME. Both ride the GitHub Release, whose asset set is `dist/cli/**`.

NO SECRET IN THIS PROCESS. A credentialed step runs as a child `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile <p> -- ...`, so values live only in that child's environment. A step that needs a store name under another spelling (`binds`, the `STORE > LOCAL` grammar of secret-supply.json) or the operator's GitHub token (`gh_env`, read from `gh auth token`) runs its command through the `_bind` verb of this module INSIDE that child. `_bind` reads no store: STORE must be declared by one of the step's profiles, which bound it, and `_bind` only copies it to LOCAL, so `check:ci-secret-supply` knows every vault entry a release reads. That is how the www Worker gets the unsuffixed `AWS_SES_ACCESS_KEY_ID` / `AWS_SES_SECRET_ACCESS_KEY` it reads while the store holds only the regional pairs: the EU pair is bound under the unsuffixed names for that one child, as cd-deploy-worker.yml does. Every push (the tag, the tap, the Release) uses the session's GitHub token through gh: the clone's credential helper is `gh auth git-credential`, and `GITHUB_PAT` / `GH_TOKEN` come from `gh auth token`. No App token.

`--dry-run` resolves the version and runs the gates read-only, then prints every step with its profiles and the key NAMES they bind. It reads no secret value and writes nothing: the gates' fetch becomes `git ls-remote`, the release lock reads the public sentinel URL and `git ls-remote --tags`, the release clone is not made (named as not judged), and no record is written. It exits 1 naming each refusal, else 0.

A REAL RUN, after the gates admit: the release clone's `origin` is pointed at the real remote (it was cloned from this checkout) with gh as its credential helper, the release-run record is written through `release_run.write_release_run` and exported as REDIACC_RELEASE_RUN to every child, then the steps run in order, each timed. On a failure the run stops; the `on_failure` rows of an armed region (the deploy rollback) and the `always` rows (the deploy records, the release record) still run. The release record (every step's id, rc and wall seconds, for L1's timing comparison) is written to R2 once at `release-records/v<V>/edge/run-<id>.json`, and on a full release also at `release-records/v<V>/edge.json`, the key `local_gates` and the stable soak read.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Sequence
from typing import Any

from rediacc_ci import paths
from rediacc_ci import proc as child_proc
from rediacc_ci.core import awscli, bws_env, gh_retry
from rediacc_ci.deploy import deploy_record
from rediacc_ci.release import create_github_release, local_gates, order

SELF = "rediacc_ci.release.local"
CHANNEL = "edge"
CHANNELS = ("edge", "stable")
STABLE_REFUSAL = (
    "--channel stable is promoted through CI/CD only (.github/workflows/promote-stable.yml); "
    "release:local publishes edge (operator ruling ASKED:2026-10-27T09:45Z)"
)
SECTIONS = (
    "version",
    "gates",
    "builds",
    "assist",
    "stage",
    "seal",
    "publish",
    "deploy",
    "smoke",
    "release",
    "record",
)
RETRIES_NO_FAIL = 3
# Seconds slept before the 2nd and 3rd attempt of a `can_fail=False` row: a transient remote or R2 error gets time to clear.
RETRY_BACKOFF = (5.0, 20.0)
RECORD_PREFIX = "release-records/v%s/edge"
ASSIST_WORKFLOW = "local-release-assist.yml"
ASSIST_NAME = "Local Release Assist"
# local-release-assist.yml THE R2 CONTRACT: one prefix in WK_RELEASES_BUCKET, private-bin/ in, cli/ out, cli/.complete last.
ASSIST_PREFIX = "staging/local-release/v%s"
ASSIST_SEAS = ("rdc-mac-arm64", "rdc-mac-x64", "rdc-win-x64.exe", "rdc-win-arm64.exe")
# The file list of ci-build-renet.yml's `renet-binaries-<sha>` artifact, which the assist's SEA builds read.
ASSIST_BIN_GLOBS = (
    "renet-linux-*",
    "renet-darwin-*",
    "renet-windows-*",
    "criu-linux-*",
    "rsync-linux-*",
    "zot-linux-*",
    "k3s-linux-*",
    "csiprovisioner-linux-*",
    "csisnapshotter-linux-*",
    "snapshotcontroller-linux-*",
    "checksums.sha256",
)
# The renet binaries the four SEAs embed; each must be in checksums.sha256 and match it before anything is staged.
ASSIST_RENET = tuple(
    "renet-%s-%s%s" % (goos, arch, ".exe" if goos == "windows" else "")
    for goos in ("linux", "darwin", "windows")
    for arch in ("amd64", "arm64")
)
CLONE_REL = ".ci/cache/release"
WELL_KNOWN_REL = ".ci/config/well-known.env"
REGIONS_REL = "regions.json"
SUMS_NAME = "SHA256SUMS"
# The tools a run needs before its first step (plan risk R4). nfpm is fetched by its own stage step.
PREREQS = {
    "full": ("git", "docker", "gh", "npm", "node", "gpg", "aws"),
    "workers": ("git", "gh", "npm", "aws"),
}
GH_CREDENTIAL = 'git config credential.helper "" && git config --add credential.helper "!gh auth git-credential"'

PY = ("python3", "-m")


@dataclasses.dataclass(frozen=True)
class Step:
    """One row of the release table. `argv` and `env` values are templates over the run context (`{version}`, `{sha}`, `{region}`, ...)."""

    id: str
    section: str
    argv: tuple[str, ...]
    profiles: tuple[str, ...] = ()
    can_fail: bool = True
    env: tuple[tuple[str, str], ...] = ()
    binds: tuple[str, ...] = ()
    gh_env: tuple[str, ...] = ()
    cwd: str = "clone"
    per_region: bool = False
    workers: bool = False
    kind: str = "run"
    capture: str = ""
    rc_as: str = ""
    always: bool = False
    on_failure: bool = False
    arm: str = ""
    readonly: bool = False

    def for_region(self, region: str) -> Step:
        def sub(text: str) -> str:
            return text.replace("{region}", region)

        return dataclasses.replace(
            self,
            id="%s-%s" % (self.id, region),
            argv=tuple(sub(a) for a in self.argv),
            env=tuple((k, sub(v)) for k, v in self.env),
            arm=sub(self.arm),
            per_region=False,
        )


# The store names the edge www Worker secrets read under another spelling (cd-deploy-worker.yml `Set Worker secrets`, target edge).
WWW_BINDS = (
    "AWS_SES_ACCESS_KEY_ID_EU > AWS_SES_ACCESS_KEY_ID",
    "AWS_SES_SECRET_ACCESS_KEY_EU > AWS_SES_SECRET_ACCESS_KEY",
    "AWS_SES_REGION_EU > AWS_SES_REGION",
    "STRIPE_SANDBOX_SECRET_KEY > STRIPE_SECRET_KEY",
    "STRIPE_SANDBOX_WEBHOOK_SECRET > STRIPE_WEBHOOK_SECRET",
)
TURNSTILE = ("TURNSTILE_SITE_KEY > VITE_TURNSTILE_SITE_KEY",)
LOCK_CHECK = (*PY, SELF, "_lock-check", "--version", "{version}")


def _retag(image_flag: str, image: str, src: str, dst: str, *extra: str) -> tuple[str, ...]:
    return (
        "python3",
        ".ci/scripts/docker/retag_image.py",
        image_flag,
        image,
        "--from",
        src,
        "--to",
        dst,
        *extra,
    )


def _table() -> tuple[Step, ...]:
    server = "{registry}/server"
    sea_env = (("CLI_VERSION", "{version}"), ("RELEASE_BUILD", "true"))
    w: dict[str, Any] = {"workers": True}
    return (
        # ---- 1. version (read-only: it runs under --dry-run too)
        Step(
            "bump-type",
            "version",
            (*PY, "rediacc_ci.version.detect_bump_type"),
            env=(("GITHUB_REPOSITORY", "{repo}"),),
            cwd="root",
            capture="bump",
            readonly=True,
        ),
        Step(
            "version",
            "version",
            (*PY, "rediacc_ci.version.resolve_version", "--bump-type", "{bump}"),
            cwd="root",
            capture="version",
            readonly=True,
        ),
        Step(
            "channel-version",
            "version",
            (),
            cwd="root",
            kind="channel-version",
            capture="version",
            readonly=True,
            **w,
        ),
        # ---- 2. gates (W2-A), then the clone's remote and credential, and the release-run record
        Step(
            "gates",
            "gates",
            (*PY, "rediacc_ci.release.local_gates", "--channel", "edge", "--version", "{version}"),
            profiles=("r2-artifacts",),
            cwd="root",
            kind="gates",
            readonly=True,
            **w,
        ),
        Step("clone-origin", "gates", ("git", "remote", "set-url", "origin", "{origin_url}"), **w),
        Step("clone-credential", "gates", ("sh", "-c", GH_CREDENTIAL), **w),
        Step("release-run", "gates", (), cwd="root", kind="release-run", **w),
        # ---- 3. builds, in the release clone
        Step("deps", "builds", ("npm", "ci"), **w),
        Step("natives", "builds", ("npm", "run", "install:natives"), **w),
        Step("packages", "builds", ("npm", "run", "build:packages"), **w),
        Step(
            "account-deps",
            "builds",
            ("sh", "-c", "npm install && npm run install:natives"),
            cwd="clone:private/account",
            **w,
        ),
        Step(
            "inject-env",
            "builds",
            (*PY, "rediacc_ci.version.inject_env", "--version", "{version}", "--strict", "--print"),
        ),
        Step("version-bump", "builds", (*PY, "rediacc_ci.version.bump", "--version", "{version}")),
        Step(
            "renet",
            "builds",
            (
                *PY,
                "rediacc_ci.build.build_renet",
                "--version",
                "{version}",
                "--output",
                "./private/bin",
            ),
            profiles=("release-local",),
        ),
        Step(
            "renet-key-gate",
            "builds",
            # The clone has no DEV public-key cache (it is untracked), so the operator checkout's is named: without a DEV key the gate refuses. The path reaches the shell through the environment, never spliced into its text, so a checkout path holding `"`, `$` or a backtick stays one word (review 0e993d36.1); `sh -c` is only there to expand the renet glob.
            (
                "sh",
                "-c",
                'exec env PYTHONPATH=.ci python3 -m rediacc_ci.release.renet_key_gate --dev-cache "$DEV_CACHE" private/bin/renet-*',
            ),
            profiles=("release-local",),
            env=(("DEV_CACHE", "{dev_cache}"),),
        ),
        # The assist starts as soon as the keyed renet set exists (local-release-assist.yml THE R2 CONTRACT): stage it, then dispatch.
        Step(
            "assist-stage-in",
            "builds",
            (*PY, SELF, "_assist", "stage-in", "--version", "{version}"),
            profiles=("r2-artifacts",),
        ),
        Step(
            "assist-dispatched-at", "builds", (), cwd="root", kind="stamp", capture="dispatched_at"
        ),
        Step(
            "assist-dispatch",
            "builds",
            (
                "gh",
                "workflow",
                "run",
                ASSIST_WORKFLOW,
                "--ref",
                "main",
                "-f",
                "version={version}",
                "-f",
                "sha={sha}",
            ),
        ),
        Step("cli-bundle", "builds", (*PY, "rediacc_ci.build.build_cli")),
        Step(
            "cli-npm",
            "builds",
            (*PY, "rediacc_ci.build.pack_cli_npm"),
            env=(("VERSION", "{version}"),),
        ),
        Step("www-json", "builds", (*PY, "rediacc_ci.build.build_www")),
        Step(
            "sea-linux-x64",
            "builds",
            (
                *PY,
                "rediacc_ci.build.build_cli_executables",
                "--platform",
                "linux",
                "--arch",
                "x64",
                "--output",
                "dist/cli",
            ),
            env=sea_env,
        ),
        Step(
            "sea-musl-x64",
            "builds",
            (*PY, "rediacc_ci.build.build_cli_musl", "--arch", "x64", "--output", "dist/cli"),
            env=sea_env,
        ),
        Step(
            "sea-musl-arm64",
            "builds",
            (*PY, "rediacc_ci.build.build_cli_musl", "--arch", "arm64", "--output", "dist/cli"),
            env=sea_env,
        ),
        Step(
            "sea-linux-arm64",
            "builds",
            (
                "docker",
                "run",
                "--rm",
                "--platform",
                "linux/arm64",
                "-v",
                "{clone}:/w",
                "-w",
                "/w",
                "-e",
                "CLI_VERSION={version}",
                "-e",
                "RELEASE_BUILD=true",
                "-e",
                "PYTHONPATH=.ci",
                "node:24",
                "python3",
                "-m",
                "rediacc_ci.build.build_cli_executables",
                "--platform",
                "linux",
                "--arch",
                "arm64",
                "--output",
                "dist/cli",
            ),
        ),
        Step(
            "renet-binaries",
            "builds",
            ("sh", "-c", "mkdir -p binaries && cp private/bin/renet-linux-* binaries/"),
        ),
        Step(
            "docker-renet-amd64",
            "builds",
            (
                "docker",
                "buildx",
                "build",
                "--file",
                "private/renet/Dockerfile.native",
                "--platform",
                "linux/amd64",
                "--build-arg",
                "TARGETARCH=amd64",
                "--tag",
                "{registry}/renet:{build_tag}-amd64",
                "--push",
                ".",
            ),
        ),
        Step(
            "docker-renet-arm64",
            "builds",
            (
                "docker",
                "buildx",
                "build",
                "--file",
                "private/renet/Dockerfile.native",
                "--platform",
                "linux/arm64",
                "--build-arg",
                "TARGETARCH=arm64",
                "--tag",
                "{registry}/renet:{build_tag}-arm64",
                "--push",
                ".",
            ),
        ),
        Step(
            "docker-renet-manifest",
            "builds",
            (
                "python3",
                ".ci/scripts/docker/create_manifest.py",
                "--image",
                "renet",
                "--tag",
                "{build_tag}",
            ),
        ),
        Step(
            "docker-rdc-amd64",
            "builds",
            (
                "sh",
                "-c",
                'mkdir -p bin && cp dist/cli/rdc-linux-musl-x64 bin/rdc && exec docker buildx build --file packages/cli/Dockerfile.native --platform linux/amd64 --tag "$IMAGE" --push .',
            ),
            env=(("IMAGE", "{registry}/rdc:{build_tag}-amd64"),),
        ),
        Step(
            "docker-rdc-arm64",
            "builds",
            (
                "sh",
                "-c",
                'mkdir -p bin && cp dist/cli/rdc-linux-musl-arm64 bin/rdc && exec docker buildx build --file packages/cli/Dockerfile.native --platform linux/arm64 --tag "$IMAGE" --push .',
            ),
            env=(("IMAGE", "{registry}/rdc:{build_tag}-arm64"),),
        ),
        Step(
            "docker-rdc-manifest",
            "builds",
            (
                "python3",
                ".ci/scripts/docker/create_manifest.py",
                "--image",
                "rdc",
                "--tag",
                "{build_tag}",
            ),
        ),
        Step(
            "docker-server-amd64",
            "builds",
            (*PY, "rediacc_ci.build.buildx_push_web"),
            profiles=("release-local",),
            env=(
                ("PLATFORM", "linux/amd64"),
                ("VARIANT", "onprem"),
                ("IMAGE_PATH", server),
                ("WEB_TAG", "{build_tag}"),
                ("ACCOUNT_ENTRY", "on-premise"),
            ),
        ),
        Step(
            "docker-server-arm64",
            "builds",
            (*PY, "rediacc_ci.build.buildx_push_web"),
            profiles=("release-local",),
            env=(
                ("PLATFORM", "linux/arm64"),
                ("VARIANT", "onprem"),
                ("IMAGE_PATH", server),
                ("WEB_TAG", "{build_tag}"),
                ("ACCOUNT_ENTRY", "on-premise"),
            ),
        ),
        Step(
            "docker-server-manifest",
            "builds",
            (
                "python3",
                ".ci/scripts/docker/create_manifest.py",
                "--image-path",
                server,
                "--tag",
                "{build_tag}",
            ),
        ),
        # ---- 4. the mac and win SEAs and install legs, on CI (plan: Gaps that stay on CI): wait for the marker, fetch the four SEAs into dist/cli
        Step(
            "assist-fetch",
            "assist",
            (
                *PY,
                SELF,
                "_assist",
                "fetch",
                "--version",
                "{version}",
                "--sha",
                "{sha}",
                "--since",
                "{dispatched_at}",
            ),
            profiles=("r2-artifacts",),
            capture="assist_run",
        ),
        # ---- 5. stage (memo A, C1-C9), opened by the live lock check: a CD edge release of v<V> since the gates stops here
        Step("lock-check-stage", "stage", LOCK_CHECK, profiles=("r2-artifacts",)),
        Step("ensure-nfpm", "stage", (*PY, "rediacc_ci.build.ensure_nfpm"), capture="nfpm_dir"),
        Step(
            "linux-packages",
            "stage",
            (*PY, "rediacc_ci.build.build_linux_packages"),
            profiles=("release-local",),
            env=(("NEXT_VERSION", "{version}"), ("PATH", "{nfpm_dir}:{path}")),
        ),
        Step(
            "cli-manifest",
            "stage",
            (
                *PY,
                "rediacc_ci.build.generate_cli_manifest",
                "--version",
                "{version}",
                "--channel",
                "edge",
                "--input",
                "dist/cli/",
                "--output",
                "dist/cli/manifest.json",
            ),
        ),
        Step("pages", "stage", (*PY, "rediacc_ci.build.build_pages", "--output", "dist/pages")),
        Step(
            "pages-manifest",
            "stage",
            ("sh", "-c", "mkdir -p dist/pages/cli && cp dist/cli/manifest.json dist/pages/cli/"),
        ),
        Step(
            "pkg-repo",
            "stage",
            (
                *PY,
                "rediacc_ci.build.build_pkg_repo",
                "--version",
                "{version}",
                "--local-pkgs",
                "dist/packages",
                "--output",
                "dist/repos",
                "--channel",
                "edge",
            ),
            profiles=("release-local",),
            gh_env=("GH_TOKEN",),
        ),
        Step(
            "provenance",
            "stage",
            (*PY, SELF, "_provenance", "--root", "."),
            profiles=("release-local",),
        ),
        Step("retag-renet", "stage", _retag("--image", "renet", "{build_tag}", "edge")),
        Step("retag-rdc", "stage", _retag("--image", "rdc", "{build_tag}", "edge")),
        Step("retag-server", "stage", _retag("--image-path", server, "{build_tag}", "edge")),
        Step(
            "validate-stage",
            "stage",
            (*PY, "rediacc_ci.release.validate_stage_artifacts"),
            env=(
                ("MODE", ""),
                ("EVENT_NAME", "push"),
                ("NEXT_VERSION", "{version}"),
                ("CHANNEL", "edge"),
            ),
        ),
        Step(
            "upload-cli-r2",
            "stage",
            (*PY, "rediacc_ci.deploy.upload_to_r2", "--version", "{version}", "--channel", "edge"),
            profiles=("r2-artifacts",),
            env=(("SNAPSHOT_VERSION", "{version}"),),
        ),
        Step(
            "upload-repos-r2",
            "stage",
            (*PY, "rediacc_ci.deploy.upload_repos_to_r2"),
            profiles=("release-local", "deploy-workers"),
            env=(("CHANNEL", "edge"), ("SNAPSHOT_VERSION", "{version}")),
        ),
        Step(
            "assert-r2-sentinel",
            "stage",
            (*PY, "rediacc_ci.release.assert_r2_sentinel", "edge", "{version}"),
            profiles=("r2-artifacts",),
        ),
        Step(
            "assist-clean",
            "stage",
            (*PY, SELF, "_assist", "clean", "--version", "{version}"),
            profiles=("r2-artifacts",),
        ),
        # A stop after the dispatch first cancels this attempt's assist run while it is still in flight and waits for it to finish, so the clean below is not raced by its upload (review 0e993d36.2). It runs before the clean because on-stop rows run in table order.
        Step(
            "assist-cancel-on-stop",
            "stage",
            (
                *PY,
                SELF,
                "_assist",
                "cancel",
                "--version",
                "{version}",
                "--sha",
                "{sha}",
                "--since",
                "{dispatched_at}",
            ),
            on_failure=True,
            arm="assist-dispatch",
        ),
        # A stop anywhere after the keyed renet set was staged (a failed fetch, stage or seal) still empties the prefix; the rm is idempotent, so a stop after assist-clean repeats it harmlessly.
        Step(
            "assist-clean-on-stop",
            "stage",
            (*PY, SELF, "_assist", "clean", "--version", "{version}"),
            profiles=("r2-artifacts",),
            on_failure=True,
            arm="assist-stage-in",
        ),
        Step("lock-check-seal", "stage", LOCK_CHECK, profiles=("r2-artifacts",)),
        # ---- 6. seal, then the tag at once (risk R2)
        Step(
            "seal",
            "seal",
            (
                *PY,
                "rediacc_ci.deploy.write_release_sentinel",
                "--version",
                "{version}",
                "--channel",
                "edge",
                "--commit-sha",
                "{sha}",
            ),
            profiles=("r2-artifacts",),
            can_fail=False,
        ),
        # The tag in three rows that run as one unit: create it locally (its object id is the only stdout line), add that oid to the release-run record, push exactly that oid. The pre-push hook admits the push by that oid only.
        Step(
            "tag-create",
            "seal",
            (
                "sh",
                "-c",
                'exec env PYTHONPATH=.ci python3 -m rediacc_ci.release.tag --version "$VERSION" --sha "$SHA" --remote origin --create-only --bot-name "$GIT_BOT_NAME" --bot-email "$GIT_BOT_EMAIL"',
            ),
            profiles=("release-local",),
            env=(("VERSION", "{version}"), ("SHA", "{sha}")),
            capture="tag_oid",
            can_fail=False,
        ),
        Step("tag-record", "seal", (), cwd="root", kind="tag-record", can_fail=False),
        Step(
            "tag-push",
            "seal",
            (
                *PY,
                "rediacc_ci.release.tag",
                "--version",
                "{version}",
                "--push-oid",
                "{tag_oid}",
                "--remote",
                "origin",
            ),
            can_fail=False,
        ),
        # ---- 7. publish
        Step(
            "cd-preflight",
            "publish",
            (
                *PY,
                "rediacc_ci.release.cd_preflight",
                "--phase",
                "cd",
                "--release-version",
                "{version}",
                "--release-sha",
                "{sha}",
                "--checks",
                "a,c,d",
            ),
            profiles=("r2-artifacts",),
        ),
        Step(
            "promote-renet",
            "publish",
            _retag("--image", "renet", "edge", "{version}", "--push-latest", "--skip-if-exists"),
        ),
        Step(
            "promote-rdc",
            "publish",
            _retag("--image", "rdc", "edge", "{version}", "--push-latest", "--skip-if-exists"),
        ),
        Step(
            "promote-server",
            "publish",
            _retag(
                "--image-path", server, "edge", "{version}", "--push-latest", "--skip-if-exists"
            ),
        ),
        Step(
            "stripe-sync",
            "publish",
            ("npx", "--no-install", "tsx", "scripts/stripe-sync.ts"),
            profiles=("release-local",),
            cwd="clone:private/account",
        ),
        Step(
            "stripe-webhook",
            "publish",
            (
                "npx",
                "--no-install",
                "tsx",
                "private/account/scripts/verify-webhook.ts",
                "--expected-url",
                "https://{domain}/account/api/v1/webhooks/stripe",
            ),
            profiles=("release-local",),
            per_region=True,
        ),
        Step(
            "cleanup-channel-tags",
            "publish",
            (*PY, "rediacc_ci.release.cleanup_channel_docker_tags"),
            env=(("CHANNEL", "edge"),),
            gh_env=("GH_TOKEN",),
        ),
        Step(
            "executor-stage",
            "publish",
            (
                *PY,
                "rediacc_ci.deploy.executor_artifacts",
                "stage",
                "--version",
                "{version}",
                "--git-sha",
                "{sha}",
                "--bundle-dir",
                "packages/cli/dist",
                "--renet",
                "private/bin/renet-linux-amd64",
                "--node-modules",
                "node_modules",
            ),
            profiles=("deploy-proxy",),
        ),
        # ---- 8. the edge Worker deploys (cd-deploy-worker.yml, cd-deploy-account.yml)
        Step(
            "www-pages",
            "deploy",
            ("npm", "run", "build", "-w", "@rediacc/www"),
            env=(
                ("APP_VERSION", "{version}"),
                ("NODE_OPTIONS", "--max-old-space-size=4096"),
                ("PUBLIC_VIDEO_CDN_BASE_URL", "{media_origin}"),
            ),
            gh_env=("GITHUB_TOKEN",),
            **w,
        ),
        Step(
            "www-assets",
            "deploy",
            (
                "sh",
                "-c",
                "rm -rf workers/www/dist && mkdir -p workers/www/dist && cp -r packages/www/dist/* workers/www/dist/",
            ),
            **w,
        ),
        Step(
            "www-portal",
            "deploy",
            (
                "sh",
                "-c",
                "npm install && npx vite build --outDir ../../../workers/www/dist/account",
            ),
            profiles=("deploy-workers",),
            binds=TURNSTILE,
            env=(("VITE_CI_MODE", "false"),),
            cwd="clone:private/account/web",
            **w,
        ),
        Step("www-worker-deps", "deploy", ("npm", "install"), cwd="clone:workers/www", **w),
        Step(
            "www-deploy",
            "deploy",
            (*PY, "rediacc_ci.deploy.deploy_edge"),
            profiles=("deploy-workers",),
            env=(
                ("DEPLOY_RECORD_OUT", "{out}/www-record.json"),
                ("DEPLOY_RECORD_VERSION", "{version}"),
            ),
            **w,
        ),
        Step(
            "www-secrets",
            "deploy",
            (*PY, "rediacc_ci.deploy.set_www_worker_secrets"),
            profiles=("release-local", "deploy-workers"),
            binds=WWW_BINDS,
            env=(("WORKER_NAME", "edge-rediacc-www"),),
            **w,
        ),
        Step(
            "account-portal",
            "deploy",
            (
                "sh",
                "-c",
                "npm install && npx vite build --outDir ../../../workers/account/dist/account",
            ),
            profiles=("deploy-workers",),
            binds=TURNSTILE,
            env=(("VITE_CI_MODE", "false"),),
            cwd="clone:private/account/web",
            **w,
        ),
        Step("account-worker-deps", "deploy", ("npm", "install"), cwd="clone:workers/account", **w),
        Step("proxy-worker-deps", "deploy", ("npm", "install"), cwd="clone:workers/proxy", **w),
        Step(
            "order",
            "deploy",
            (
                *PY,
                "rediacc_ci.release.order",
                "--channel",
                "edge",
                "--account-pointer",
                "{account_pointer}",
            ),
            profiles=("r2-artifacts",),
            per_region=True,
            **w,
        ),
        Step(
            "record-before",
            "deploy",
            (
                *PY,
                "rediacc_ci.deploy.deploy_record",
                "before",
                "--target",
                "edge",
                "--region",
                "{region}",
                "--version",
                "{version}",
                "--out",
                "{out}/{region}/before.json",
            ),
            profiles=("deploy-proxy",),
            per_region=True,
            **w,
        ),
        Step(
            "account-deploy",
            "deploy",
            (*PY, "rediacc_ci.deploy.deploy_account", "--region", "{region}", "--target", "edge"),
            profiles=("deploy-workers",),
            per_region=True,
            **w,
        ),
        Step(
            "account-secrets",
            "deploy",
            (
                *PY,
                "rediacc_ci.deploy.account_secrets_local",
                "--region",
                "{region}",
                "--target",
                "edge",
            ),
            per_region=True,
            **w,
        ),
        Step(
            "proxy-deploy",
            "deploy",
            (
                *PY,
                "rediacc_ci.deploy.deploy_proxy",
                "--target",
                "edge",
                "--region",
                "{region}",
                "--version",
                "{version}",
                "--record",
                "{out}/{region}/proxy.json",
            ),
            profiles=("deploy-proxy",),
            per_region=True,
            **w,
        ),
        Step(
            "proxy-smoke",
            "deploy",
            (
                *PY,
                "rediacc_ci.deploy.deploy_proxy",
                "--target",
                "edge",
                "--region",
                "{region}",
                "--smoke-only",
                "--record",
                "{out}/{region}/proxy.json",
            ),
            profiles=("deploy-proxy",),
            per_region=True,
            **w,
        ),
        Step(
            "executor-enable",
            "deploy",
            (
                *PY,
                "rediacc_ci.deploy.console_executor",
                "--enable",
                "--target",
                "edge",
                "--region",
                "{region}",
            ),
            profiles=("deploy-proxy",),
            per_region=True,
            **w,
        ),
        Step(
            "rollback",
            "deploy",
            (
                *PY,
                "rediacc_ci.deploy.deploy_record",
                "rollback",
                "--before",
                "{out}/{region}/before.json",
            ),
            profiles=("deploy-proxy",),
            per_region=True,
            on_failure=True,
            arm="record-before-{region}",
            **w,
        ),
        # ---- 9. smoke, then the deploy records with its rc
        Step(
            "verify-endpoints",
            "smoke",
            (*PY, "rediacc_ci.deploy.verify_edge_endpoints"),
            env=(("VERSION", "{version}"), ("WORKERS_ONLY", "{workers_only}")),
            rc_as="smoke_rc",
            **w,
        ),
        Step(
            "install-quick",
            "smoke",
            (
                *PY,
                "rediacc_ci.testrun.install_methods",
                "--method",
                "quick",
                "--version",
                "{version}",
            ),
        ),
        Step(
            "record-www",
            "smoke",
            (
                *PY,
                "rediacc_ci.deploy.deploy_record",
                "www-after",
                "--record",
                "{out}/www-record.json",
                "--smoke-rc",
                "{smoke_rc}",
                "--sink",
                "r2",
                "--channel",
                "edge",
            ),
            profiles=("deploy-proxy",),
            always=True,
            arm="www-deploy",
            **w,
        ),
        Step(
            "record-after",
            "smoke",
            (
                *PY,
                "rediacc_ci.deploy.deploy_record",
                "after",
                "--before",
                "{out}/{region}/before.json",
                "--proxy-record",
                "{out}/{region}/proxy.json",
                "--manifest",
                "workers/proxy/stage/manifest.json",
                "--enable-outcome",
                "{outcome:executor-enable-{region}}",
                "--rollback-outcome",
                "{outcome:rollback-{region}}",
                "--account-smoke-rc",
                "{smoke_rc}",
                "--out",
                "{out}/{region}/deploy-record-edge-{region}.json",
                "--sink",
                "r2",
                "--channel",
                "edge",
            ),
            profiles=("deploy-proxy",),
            per_region=True,
            always=True,
            arm="record-before-{region}",
            **w,
        ),
        # ---- 10. tag-and-release (cd-v2.yml tag-and-release); the version tag itself is the seal's twin above
        Step(
            "tag-submodules",
            "release",
            (*PY, "rediacc_ci.release.tag_submodules"),
            env=(("VERSION", "{version}"),),
            gh_env=("GITHUB_PAT",),
        ),
        Step(
            "homebrew",
            "release",
            (
                *PY,
                "rediacc_ci.release.update_homebrew_tap",
                "--version",
                "{version}",
                "--local-checksums",
                "dist/cli",
                "--push",
            ),
            profiles=("release-local",),
            gh_env=("GITHUB_PAT",),
        ),
        Step(
            "contract-floor",
            "release",
            (*PY, "rediacc_ci.release.advance_contract_floor"),
            profiles=("release-local",),
            # This checkout, not the release clone: the floor file it writes rides the session's next PR, and the clone is rebuilt on every run.
            cwd="root",
        ),
        Step(
            "github-release",
            "release",
            (*PY, "rediacc_ci.release.create_github_release"),
            env=(("VERSION", "{version}"), ("GITHUB_REPOSITORY", "{repo}")),
            gh_env=("GH_TOKEN",),
        ),
        # ---- 11. the release record
        Step(
            "release-record",
            "record",
            (),
            profiles=("deploy-proxy",),
            cwd="root",
            kind="release-record",
            always=True,
            **w,
        ),
    )


STEPS: tuple[Step, ...] = _table()


def plan(
    regions: Sequence[str], *, workers_only: bool = False, steps: Sequence[Step] = STEPS
) -> list[Step]:
    """The rows one run executes, in table order, per-region rows expanded over `regions`.

    A release takes every row except the workers-only version row; `--workers-only` takes the `workers` rows only, so it reads the live edge version instead of cutting one, and builds, seals, tags and publishes nothing.
    """
    out: list[Step] = []
    for step in steps:
        if workers_only and not step.workers:
            continue
        if not workers_only and step.kind == "channel-version":
            continue
        if step.per_region:
            out.extend(step.for_region(r) for r in regions)
        else:
            out.append(step)
    return out


# --------------------------------------------------------------------------- context


def read_regions(root: pathlib.Path) -> dict[str, dict[str, Any]]:
    doc = json.loads((root / REGIONS_REL).read_text(encoding="utf-8"))
    return {r["id"]: r for r in doc["regions"]}


def well_known(root: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (root / WELL_KNOWN_REL).read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.startswith("WK_"):
            out[key] = value.strip()
    return out


def _git(root: pathlib.Path, *args: str, timeout: int = 120) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return proc.returncode, proc.stdout.strip()


class Context(dict):
    """The template values of a run. A missing key renders as `<key?>` so a dry run can print a row whose value is not known yet."""

    def __missing__(self, key: str) -> str:
        return "<%s?>" % key


_OUTCOME = re.compile(r"\{outcome:([^{}]+)\}")


def render(template: str, ctx: Context) -> str:
    def outcome(m: re.Match[str]) -> str:
        return str(ctx.get("outcomes", {}).get(m.group(1), "skipped"))

    text = _OUTCOME.sub(outcome, template)
    return re.sub(r"\{([a-z_]+)\}", lambda m: str(ctx[m.group(1)]), text)


def base_context(root: pathlib.Path, regions: Sequence[str], workers_only: bool) -> Context:
    wk = well_known(root)
    _rc, head = _git(root, "rev-parse", "HEAD")
    _rc, tree = _git(root, "rev-parse", "HEAD^{tree}")
    _rc, origin = _git(root, "remote", "get-url", "origin")
    # The account commit HEAD's tree points at: the clone is HEAD, so its private/account is this gitlink.
    _rc, account = _git(root, "rev-parse", "HEAD:private/account")
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", origin)
    return Context(
        channel=CHANNEL,
        sha=head,
        tree=tree,
        build_tag="local-%s" % head[:12],
        registry=wk.get("WK_IMAGE_REGISTRY", ""),
        media_origin=wk.get("WK_MEDIA_ORIGIN", ""),
        releases_origin=wk.get("WK_RELEASES_ORIGIN", ""),
        origin_url=origin,
        account_pointer=account,
        repo=m.group(1) if m else "",
        clone=str(root / CLONE_REL / tree),
        dev_cache=str(root / "private" / "account" / ".cache" / "public-keys.env"),
        workers_only="true" if workers_only else "",
        smoke_rc="-1",
        path=os.environ.get("PATH", ""),
        outcomes={},
        regions=list(regions),
    )


# --------------------------------------------------------------------------- children


def child_argv(step: Step, ctx: Context) -> list[str]:
    """The full argv of a row: its command, wrapped in `_bind` when it binds aliases or the GitHub token, wrapped in `bws_env exec` when it runs under profiles."""
    cmd = [render(a, ctx) for a in step.argv]
    if step.binds or step.gh_env:
        bind = ["python3", "-m", SELF, "_bind"]
        for spec in step.binds:
            bind += ["--spec", spec]
        for name in step.gh_env:
            bind += ["--gh-token", name]
        cmd = [*bind, "--", *cmd]
    if step.profiles:
        wrap = ["python3", "-m", "rediacc_ci.core.bws_env", "exec"]
        for p in step.profiles:
            wrap += ["--profile", p]
        cmd = [*wrap, "--", *cmd]
    return cmd


def child_cwd(step: Step, ctx: Context, root: pathlib.Path) -> pathlib.Path:
    if step.cwd == "root":
        return root
    base = pathlib.Path(ctx["clone"])
    _kind, _sep, sub = step.cwd.partition(":")
    return base / sub if sub else base


def child_env(step: Step, ctx: Context, root: pathlib.Path) -> dict[str, str]:
    """The environment of a row's child. Non-secret values only: the profiles bind the rest inside the child."""
    tree_root = root if step.cwd == "root" else pathlib.Path(ctx["clone"])
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPYCACHEPREFIX"}
    env["PYTHONPATH"] = str(tree_root / ".ci")
    env["BWS_ENV_ROOT"] = str(root)
    out = ctx.get("out")
    if out:
        env["GITHUB_OUTPUT"] = str(pathlib.Path(out) / ("github-output-%s" % step.id))
        env["GITHUB_STEP_SUMMARY"] = str(pathlib.Path(out) / ("summary-%s.md" % step.id))
    if ctx.get("repo"):
        env.setdefault("GITHUB_REPOSITORY", ctx["repo"])
    if ctx.get("release_run"):
        env["REDIACC_RELEASE_RUN"] = ctx["release_run"]
    for key, value in step.env:
        env[key] = render(value, ctx)
    return env


def profile_keys(profiles: Sequence[str]) -> list[str]:
    """The LOCAL names the profiles bind, read from secret-supply.json. No value is read."""
    if not profiles:
        return []
    required, optional = bws_env.profile_specs(bws_env.profiles(), list(profiles))
    return [local for _store, local in required] + ["%s?" % local for _store, local in optional]


# --------------------------------------------------------------------------- the gates


@dataclasses.dataclass
class GateResult:
    refusals: list[str]
    notes: list[str]


def _ls_remote_main(root: pathlib.Path) -> tuple[str | None, str]:
    """origin/main read with `git ls-remote`, which writes no ref (the dry-run replacement of `local_gates.live_fetch`)."""
    rc, out = _git(root, "ls-remote", "--exit-code", "origin", "refs/heads/main")
    if rc != 0 or not out:
        return None, "git ls-remote origin refs/heads/main exited %d" % rc
    return out.split()[0], ""


def public_sentinel(releases_origin: str) -> Callable[[str], bool | None]:
    """`cli/v<V>/.released` read over the public releases origin, with no credential (the dry-run sentinel probe)."""

    def probe(version: str) -> bool | None:
        url = "%s/cli/v%s/.released" % (releases_origin, version)
        try:
            proc = subprocess.run(
                ["curl", "-sf", "-o", "/dev/null", url],
                capture_output=True,
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode == 0:
            return True
        return False if proc.returncode == 22 else None

    return probe


def readonly_existing(root: pathlib.Path, version: str) -> tuple[bool, str]:
    """The tag half of `check_existing_release`, read with `git ls-remote --tags` (no local tag is fetched)."""
    rc, _out = _git(root, "ls-remote", "--exit-code", "--tags", "origin", "refs/tags/v%s" % version)
    if rc == 2:
        return True, ""
    if rc == 0:
        return False, "the tag v%s exists on origin" % version
    return False, "git ls-remote --tags origin exited %d, so whether v%s exists is unknown" % (
        rc,
        version,
    )


def dry_gates(root: pathlib.Path, version: str | None, ctx: Context) -> GateResult:
    """`local_gates.check` with every writing or credentialed reader replaced by a read-only one."""
    notes = [
        "local-gates: clone: not judged under --dry-run (it writes the release clone %s)"
        % paths_rel(root, pathlib.Path(ctx["clone"]))
    ]
    refusals = local_gates.check(
        root,
        "edge",
        fetch=_ls_remote_main,
        sentinel=public_sentinel(ctx["releases_origin"]),
        existing=readonly_existing,
        version=version,
        clone=lambda _r, _t, _h: None,
    )
    return GateResult([r.line() for r in refusals], notes)


def paths_rel(root: pathlib.Path, path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def filter_workers(lines: list[str], workers_only: bool) -> list[str]:
    """A workers-only run cuts no version, so the release lock (`v<V>` taken) is its premise, not a refusal."""
    if not workers_only:
        return lines
    return [line for line in lines if not line.startswith("local-gates: lock:")]


# --------------------------------------------------------------------------- prerequisites


def prereq_refusals(workers_only: bool) -> list[str]:
    found: list[str] = []
    for tool in PREREQS["workers" if workers_only else "full"]:
        if tool == "aws":
            try:
                ok = awscli.resolve() is not None
            except awscli.AwsCliMissingError:
                ok = False
            if not ok:
                found.append(
                    "prereq: aws: no aws CLI resolves; `%s` installs the pin" % awscli.INSTALL_HINT
                )
        elif shutil.which(tool) is None:
            found.append("prereq: %s: not on PATH" % tool)
    return found


# --------------------------------------------------------------------------- the dry run


def describe(steps: Sequence[Step], ctx: Context) -> list[str]:
    """One block per row: section, id, profiles, the key names bound, the can-fail flag, then the command."""
    lines = []
    for step in steps:
        binds = [spec.split(">", 1)[1].strip() for spec in step.binds] + list(step.gh_env)
        head = "  [%s] %s  profile=%s  can_fail=%s" % (
            step.section,
            step.id,
            ",".join(step.profiles) or "-",
            "yes" if step.can_fail else "no",
        )
        flags = [f for f, on in (("always", step.always), ("on-failure", step.on_failure)) if on]
        if flags:
            head += "  (%s)" % ", ".join(flags)
        lines.append(head)
        if binds:
            lines.append("      binds: %s" % " ".join(binds))
        if step.kind != "run":
            lines.append("      (%s, run by the entry)" % step.kind)
        else:
            lines.append(
                "      %s$ %s"
                % (_cwd_label(step), " ".join(shlex.quote(a) for a in child_argv(step, ctx)))
            )
    return lines


def _cwd_label(step: Step) -> str:
    if step.cwd == "root":
        return "<console>"
    _k, _s, sub = step.cwd.partition(":")
    return "<clone>/%s" % sub if sub else "<clone>"


# --------------------------------------------------------------------------- the executor


@dataclasses.dataclass
class StepResult:
    id: str
    section: str
    rc: int
    seconds: float
    started_at: str
    attempts: int = 1

    @property
    def outcome(self) -> str:
        return "success" if self.rc == 0 else "failure"


Runner = Callable[[list[str], pathlib.Path, dict[str, str], bool], "tuple[int, str]"]


def default_runner(
    argv: list[str], cwd: pathlib.Path, env: dict[str, str], capture: bool
) -> tuple[int, str]:
    """Run a child with its stderr inherited; stdout too unless the row captures it."""
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            env=env,
            check=False,
            stdout=subprocess.PIPE if capture else None,
            text=True,
        )
    except OSError as exc:
        print("%s: cannot run %s: %s" % (SELF, argv[0], exc.strerror), file=sys.stderr)
        return 127, ""
    return proc.returncode, (proc.stdout or "").strip() if capture else ""


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclasses.dataclass
class Run:
    root: pathlib.Path
    ctx: Context
    runner: Runner = default_runner
    internal: dict[str, Callable[[Step, Run], int]] = dataclasses.field(default_factory=dict)
    results: list[StepResult] = dataclasses.field(default_factory=list)
    failed: str = ""
    backoff: tuple[float, ...] = RETRY_BACKOFF

    def run_step(self, step: Step) -> int:
        started, t0 = _now(), time.monotonic()
        attempts = 1 if step.can_fail else RETRIES_NO_FAIL
        rc, tries = 1, 0
        while tries < attempts:
            if tries:
                time.sleep(self.backoff[min(tries, len(self.backoff)) - 1] if self.backoff else 0)
            tries += 1
            if step.kind != "run":
                handler = self.internal.get(step.kind)
                rc = handler(step, self) if handler else 2
            else:
                out = self.ctx.get("out")
                if out:
                    pathlib.Path(out).mkdir(parents=True, exist_ok=True)
                rc, captured = self.runner(
                    child_argv(step, self.ctx),
                    child_cwd(step, self.ctx, self.root),
                    child_env(step, self.ctx, self.root),
                    bool(step.capture),
                )
                if rc == 0 and step.capture:
                    self.ctx[step.capture] = captured.splitlines()[-1].strip() if captured else ""
            if rc == 0:
                break
        result = StepResult(
            step.id, step.section, rc, round(time.monotonic() - t0, 3), started, tries
        )
        self.results.append(result)
        self.ctx["outcomes"][step.id] = result.outcome
        if step.rc_as:
            self.ctx[step.rc_as] = str(rc)
        print(
            "%s: [%s] %s rc=%d %.1fs" % (SELF, step.section, step.id, rc, result.seconds),
            file=sys.stderr,
        )
        return rc

    def execute(self, steps: Sequence[Step]) -> int:
        ran: set[str] = set()
        for step in steps:
            if self.failed:
                break
            if step.on_failure or step.always:
                continue
            ran.add(step.id)
            if self.run_step(step) != 0:
                self.failed = step.id
        for step in steps:
            armed = step.arm in ran and self.ctx["outcomes"].get(step.arm) == "success"
            if step.on_failure and self.failed and armed:
                self.run_step(step)
        for step in steps:
            if step.always and (not step.arm or step.arm in ran):
                self.run_step(step)
        return 1 if self.failed or any(r.rc for r in self.results) else 0


# --------------------------------------------------------------------------- internal rows


def _release_run_module(root: pathlib.Path) -> Any:
    """`.claude/rediacc_hooks/git/release_run.py`, loaded by file as `githooks.py` loads it."""
    path = root / ".claude" / "rediacc_hooks" / "git" / "release_run.py"
    spec = importlib.util.spec_from_file_location("release_run", path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tag_push(run: Run) -> dict[str, str]:
    """The version tag's push from the release clone, the one push the git-level pre-push hook judges by its exact oid: the tag OBJECT `tag-create` made, never the commit."""
    return {
        "toplevel": run.ctx["clone"],
        "remote": "origin",
        "remote_ref": "refs/tags/v%s" % run.ctx["version"],
        "oid": run.ctx["tag_oid"],
    }


def _write_record(run: Run, pushes: list[dict[str, str]]) -> int:
    module = _release_run_module(run.root)
    try:
        path = module.write_release_run(
            run.root,
            run.ctx["run_id"],
            tree=run.ctx["tree"],
            version=run.ctx["version"],
            channel=CHANNEL,
            pushes=pushes,
        )
    except module.RecordError as exc:
        print("%s: release-run: %s" % (SELF, exc), file=sys.stderr)
        return 1
    run.ctx["release_run"] = str(path)
    run.ctx["pushes"] = list(pushes)
    return 0


def internal_release_run(step: Step, run: Run) -> int:
    """Write the release-run record with no push yet: the tag's object id does not exist until `tag-create`, and `tag-record` re-writes the record with it."""
    del step
    return _write_record(run, [])


_OID = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")


def internal_tag_record(step: Step, run: Run) -> int:
    """Re-write the release-run record (same run id, same path, so REDIACC_RELEASE_RUN is unchanged) with the version tag's push at the oid `tag-create` printed."""
    oid = str(run.ctx.get("tag_oid", ""))
    if not _OID.match(oid):
        print(
            "%s: %s: tag-create printed %r, not an object id; the push cannot be recorded"
            % (SELF, step.id, oid),
            file=sys.stderr,
        )
        return 1
    push = tag_push(run)
    pushes = [p for p in run.ctx.get("pushes", []) if p.get("remote_ref") != push["remote_ref"]]
    return _write_record(run, [*pushes, push])


def internal_stamp(step: Step, run: Run) -> int:
    """The current UTC instant into `step.capture` (the assist's dispatch time, so `_assist fetch` judges only runs created after it)."""
    run.ctx[step.capture] = _now()
    return 0


def internal_channel_version(step: Step, run: Run) -> int:
    """The live edge version, from `cli/edge/manifest.json` (a workers-only run deploys what edge already serves)."""
    version = order.live_manifest_version(CHANNEL)
    if not version or version == "null":
        print(
            "%s: %s: cli/edge/manifest.json names no version (%r)" % (SELF, step.id, version),
            file=sys.stderr,
        )
        return 1
    run.ctx[step.capture] = version
    return 0


def internal_gates(step: Step, run: Run) -> int:
    """The gates as a child under the r2-artifacts profile, so the lock's sentinel read has its credential and this process none."""
    env = child_env(step, run.ctx, run.root)
    try:
        proc = subprocess.run(
            child_argv(step, run.ctx),
            cwd=str(run.root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        print("%s: gates: %s" % (SELF, exc), file=sys.stderr)
        return 1
    sys.stderr.write(proc.stderr)
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    for line in lines:
        print(line)
    return gates_verdict(proc.returncode, lines, bool(run.ctx.get("workers_only")))


def gates_verdict(rc: int, lines: list[str], workers_only: bool) -> int:
    """0 only when the gates child admitted: rc 0 with no refusal line, or (workers-only) rc 1 whose every refusal is the release lock, which a workers-only run takes as its premise. Any other nonzero exit refuses, a crash or a bws refusal with no `local-gates:` line included: unjudged is never admitted (review finding 7c25d047.1)."""
    raw = [ln for ln in lines if ln.startswith("local-gates:") and "admitted" not in ln]
    kept = filter_workers(raw, workers_only)
    if rc == 0 and not raw:
        return 0
    if rc == 1 and workers_only and raw and not kept:
        return 0
    if not raw:
        print(
            "%s: gates: the gates child exited %d and printed no refusal line; a gate that did not judge refuses"
            % (SELF, rc),
            file=sys.stderr,
        )
    return 1


def release_record(run: Run) -> dict[str, Any]:
    ctx = run.ctx
    return {
        "schema": 1,
        "kind": "release-local",
        "version": ctx["version"],
        "channel": CHANNEL,
        "sha": ctx["sha"],
        "tree": ctx["tree"],
        "run_id": ctx["run_id"],
        "workers_only": bool(ctx.get("workers_only")),
        "regions": ctx["regions"],
        "assist_run": ctx.get("assist_run"),
        "recorded_at": _now(),
        "smoke_rc": int(ctx["smoke_rc"]),
        "failed_step": run.failed or None,
        "total_seconds": round(sum(r.seconds for r in run.results), 3),
        "steps": [dataclasses.asdict(r) for r in run.results],
    }


def internal_release_record(step: Step, run: Run) -> int:
    """Write the release record to R2 through a `_write-record` child under the profile, once per key."""
    record = release_record(run)
    out = pathlib.Path(run.ctx["out"])
    out.mkdir(parents=True, exist_ok=True)
    body = out / "release-record.json"
    body.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    prefix = RECORD_PREFIX % record["version"]
    keys = ["%s/run-%s.json" % (prefix, run.ctx["run_id"])]
    if not run.failed and not record["workers_only"]:
        keys.append(prefix + ".json")
    rc = 0
    for key in keys:
        writer = dataclasses.replace(
            step, argv=(*PY, SELF, "_write-record", "--key", key, "--file", str(body)), kind="run"
        )
        rc |= subprocess.run(
            child_argv(writer, run.ctx),
            cwd=str(run.root),
            env=child_env(step, run.ctx, run.root),
            check=False,
        ).returncode
    return rc


INTERNAL = {
    "release-run": internal_release_run,
    "channel-version": internal_channel_version,
    "gates": internal_gates,
    "tag-record": internal_tag_record,
    "stamp": internal_stamp,
    "release-record": internal_release_record,
}


# --------------------------------------------------------------------------- child verbs


def bind_main(argv: list[str]) -> int:
    """`_bind --spec 'STORE > LOCAL' ... --gh-token NAME ... -- CMD`: run inside a `bws_env exec` child, copy each STORE value the enclosing profile bound to LOCAL (and NAME from `gh auth token`), exec CMD. Prints names only.

    THROUGH THE PROFILE, NEVER AROUND IT. No store is read here: STORE must be a name one of the carried profiles (`REDIACC_BWS_PROFILES`) declares in .ci/config/secret-supply.json, so `check:ci-secret-supply` knows every vault entry this entry fetches, and the value is the one `bws_env exec` already bound.
    """
    if "--" not in argv:
        print("%s _bind: want --spec/--gh-token ... -- CMD" % SELF, file=sys.stderr)
        return 2
    cut = argv.index("--")
    opts, cmd = argv[:cut], argv[cut + 1 :]
    specs = [opts[i + 1] for i, a in enumerate(opts) if a == "--spec" and i + 1 < len(opts)]
    tokens = [opts[i + 1] for i, a in enumerate(opts) if a == "--gh-token" and i + 1 < len(opts)]
    if not cmd:
        print("%s _bind: no command after --" % SELF, file=sys.stderr)
        return 2
    env = dict(os.environ)
    why = bind_refusals(specs, env)
    if why:
        for line in why:
            print("%s _bind: %s" % (SELF, line), file=sys.stderr)
        return 1
    for store, local_name in bws_env.parse_specs(specs):
        env[local_name] = env[store]
    for name in tokens:
        if env.get(name):
            continue
        proc = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
        token = proc.stdout.strip()
        if proc.returncode != 0 or not token:
            print("%s _bind: `gh auth token` gave no token for %s" % (SELF, name), file=sys.stderr)
            return 1
        env[name] = token
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        child_proc.exec_replace(cmd, env=env)
    except OSError as exc:
        print("%s _bind: cannot run %s: %s" % (SELF, cmd[0], exc.strerror), file=sys.stderr)
        return 127
    return 0  # pragma: no cover


def bind_refusals(specs: Sequence[str], env: dict[str, str]) -> list[str]:
    """Why the specs cannot be bound from `env`: a STORE no carried profile declares, or one the profile left empty. Names only.

    No spec, nothing to refuse: a row that only takes the GitHub token (`gh_env` with no profile: cleanup-channel-tags, www-pages, tag-submodules, github-release) reads no store, so it needs no carried profile.
    """
    if not specs:
        return []
    carried = [p for p in env.get(bws_env.PROFILES_ENV, "").split(",") if p]
    if not carried:
        return [
            "no profile is carried (%s is empty); run under bws_env exec" % bws_env.PROFILES_ENV
        ]
    try:
        required, optional = bws_env.profile_specs(bws_env.profiles(env), carried)
    except bws_env.RefusalError as refusal:
        return list(refusal.lines)
    declared = {local_name for _store, local_name in required + optional}
    out = []
    for store, local_name in bws_env.parse_specs(list(specs)):
        if store not in declared:
            out.append(
                "%s (for %s) is not declared by profile(s) %s in .ci/config/secret-supply.json"
                % (store, local_name, ",".join(carried))
            )
        elif not env.get(store):
            out.append(
                "%s (for %s) is empty after profile(s) %s" % (store, local_name, ",".join(carried))
            )
    return out


def write_record_main(argv: list[str]) -> int:
    """`_write-record --key K --file F`: put F at K once (deploy_record.write_record_once), inside a profile child."""
    parser = argparse.ArgumentParser(prog="%s _write-record" % SELF)
    parser.add_argument("--key", required=True)
    parser.add_argument("--file", required=True)
    args = parser.parse_args(argv)
    record = json.loads(pathlib.Path(args.file).read_text(encoding="utf-8"))
    try:
        deploy_record.write_record_once(record, args.key)
    except deploy_record.RecordError as exc:
        print("%s _write-record: %s" % (SELF, exc), file=sys.stderr)
        return 1
    return 0


def lock_check_main(argv: list[str]) -> int:
    """`_lock-check --version V`: the gates' release lock, judged live now (`local_gates.lock_refusals`), inside an r2-artifacts child."""
    parser = argparse.ArgumentParser(prog="%s _lock-check" % SELF)
    parser.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    refusals = local_gates.lock_refusals(
        paths.repo_root(), args.version, order.live_sentinel_exists, local_gates.live_existing
    )
    for refusal in refusals:
        print(refusal.line())
    if refusals:
        print("%s: v%s was taken during this run; nothing more is published" % (SELF, args.version))
        return 1
    return 0


def sha256_manifest(root: pathlib.Path) -> str:
    """`<sha256>  <path>` for every Release asset (`create_github_release.release_assets`), the manifest and its signature excluded."""
    lines = []
    for rel in create_github_release.release_assets(str(root)):
        if pathlib.PurePosixPath(rel).name.startswith(SUMS_NAME):
            continue
        digest = hashlib.sha256()
        with open(root / rel, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        lines.append("%s  %s\n" % (digest.hexdigest(), rel))
    return "".join(lines)


def provenance_main(argv: list[str]) -> int:
    """`_provenance --root DIR`: write `dist/cli/SHA256SUMS` and its armoured detached signature with the release GPG key, in a throwaway GNUPGHOME. Inside a release-local child; no value is printed."""
    parser = argparse.ArgumentParser(prog="%s _provenance" % SELF)
    parser.add_argument("--root", required=True)
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    manifest = sha256_manifest(root)
    if not manifest:
        print(
            "%s _provenance: no Release asset under dist/cli or dist/packages" % SELF,
            file=sys.stderr,
        )
        return 1
    key = os.environ.get("RELEASE_GPG_PRIVATE_KEY", "")
    if not key:
        print("%s _provenance: RELEASE_GPG_PRIVATE_KEY is not bound" % SELF, file=sys.stderr)
        return 1
    sums = root / "dist" / "cli" / SUMS_NAME
    sums.parent.mkdir(parents=True, exist_ok=True)
    sums.write_text(manifest, encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="gnupg-") as home:
        env = dict(os.environ, GNUPGHOME=home)
        base = ["gpg", "--batch", "--yes", "--pinentry-mode", "loopback"]
        imported = subprocess.run(
            [*base, "--import"],
            input=(key + "\n").encode(),
            env=env,
            capture_output=True,
            check=False,
        )
        if imported.returncode != 0:
            print(
                "%s _provenance: gpg --import exited %d" % (SELF, imported.returncode),
                file=sys.stderr,
            )
            return 1
        signed = subprocess.run(
            [
                *base,
                "--passphrase-fd",
                "0",
                "--armor",
                "--detach-sign",
                "--output",
                str(sums) + ".asc",
                str(sums),
            ],
            input=os.environ.get("RELEASE_GPG_PASSPHRASE", "").encode(),
            env=env,
            capture_output=True,
            check=False,
        )
        if signed.returncode != 0:
            print(
                "%s _provenance: gpg --detach-sign exited %d" % (SELF, signed.returncode),
                file=sys.stderr,
            )
            return 1
        verified = subprocess.run(
            [*base, "--verify", str(sums) + ".asc", str(sums)],
            env=env,
            capture_output=True,
            check=False,
        )
        if verified.returncode != 0:
            print(
                "%s _provenance: the signature does not verify (gpg exited %d)"
                % (SELF, verified.returncode),
                file=sys.stderr,
            )
            return 1
    print(
        "%s _provenance: %d asset(s) in %s, signed"
        % (SELF, manifest.count("\n"), paths_rel(root, sums))
    )
    return 0


class AssistError(Exception):
    """The assist exchange cannot go on; the message says why."""


def _assist_r2(root: pathlib.Path) -> tuple[str, str, dict[str, str]]:
    """(bucket, endpoint, aws env) from well-known.env and the r2-artifacts trio this child carries."""
    bucket = well_known(root).get("WK_RELEASES_BUCKET", "")
    access = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID", "")
    secret = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "")
    endpoint = os.environ.get("CLOUDFLARE_R2_ENDPOINT", "")
    if not bucket:
        raise AssistError("%s names no WK_RELEASES_BUCKET" % WELL_KNOWN_REL)
    if not (access and secret and endpoint):
        raise AssistError("the R2 trio is not bound; run under bws_env exec --profile r2-artifacts")
    try:
        awscli.require()
    except awscli.AwsCliMissingError as exc:
        raise AssistError(str(exc)) from exc
    env = dict(
        os.environ,
        AWS_ACCESS_KEY_ID=access,
        AWS_SECRET_ACCESS_KEY=secret,
        AWS_DEFAULT_REGION="auto",
    )
    return bucket, endpoint, env


def _aws(args: list[str], endpoint: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return awscli.run(
        ["aws", *args, "--endpoint-url", endpoint], env=env, capture_output=True, text=True
    )


def _digest(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def checksum_refusals(folder: pathlib.Path, sums: pathlib.Path, need: Sequence[str]) -> list[str]:
    """Why `sums` (`<sha256>  <name>` lines) does not prove the files of `need` in `folder`: a name unlisted, a file missing, a digest that differs."""
    if not sums.is_file() or not sums.stat().st_size:
        return ["%s is missing or empty" % sums]
    listed: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2:
            listed[parts[1].lstrip("*")] = parts[0].lower()
    out = []
    for name in need:
        path = folder / name
        if name not in listed:
            out.append("%s is not listed in %s" % (name, sums.name))
        elif not path.is_file() or not path.stat().st_size:
            out.append("%s is missing or empty" % path)
        elif _digest(path) != listed[name]:
            out.append("%s does not match its digest in %s" % (path, sums.name))
    return out


def assist_stage_in(version: str, clone: pathlib.Path) -> str:
    """Empty the version's staging prefix (a stale `.complete` of an earlier attempt must never be read as this run's), then upload the keyed renet set with its checksums to private-bin/."""
    bucket, endpoint, env = _assist_r2(clone)
    folder = clone / "private" / "bin"
    why = checksum_refusals(folder, folder / "checksums.sha256", ASSIST_RENET)
    if why:
        raise AssistError("the renet set is not provably whole: " + "; ".join(why))
    files = sorted({p for g in ASSIST_BIN_GLOBS for p in folder.glob(g) if p.is_file()})
    prefix = "s3://%s/%s" % (bucket, ASSIST_PREFIX % version)
    gone = _aws(["s3", "rm", "--recursive", "--only-show-errors", prefix + "/"], endpoint, env)
    if gone.returncode != 0:
        raise AssistError("aws s3 rm %s/ exited %d" % (prefix, gone.returncode))
    for path in files:
        put = _aws(
            [
                "s3",
                "cp",
                "--only-show-errors",
                str(path),
                "%s/private-bin/%s" % (prefix, path.name),
            ],
            endpoint,
            env,
        )
        if put.returncode != 0:
            raise AssistError("aws s3 cp %s exited %d" % (path.name, put.returncode))
    return "%d file(s) staged at %s/private-bin/" % (len(files), prefix)


def _gh_json(args: list[str]) -> Any:
    try:
        result = gh_retry.gh(args, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout_raw or "null")
    except ValueError:
        return None


def assist_failed_run(sha: str, since: str) -> str:
    """The id of a local-release-assist dispatch on `sha`, created at or after `since`, that completed without success; "" when there is none or gh cannot say (the marker and the timeout still decide)."""
    rows = _gh_json(
        [
            "run",
            "list",
            "--workflow",
            ASSIST_WORKFLOW,
            "--event",
            "workflow_dispatch",
            "--limit",
            "20",
            "--json",
            "databaseId,headSha,status,conclusion,createdAt",
        ]
    )
    for row in rows if isinstance(rows, list) else []:
        if (
            row.get("headSha") == sha
            and str(row.get("createdAt", "")) >= since
            and row.get("status") == "completed"
            and row.get("conclusion") != "success"
        ):
            return str(row.get("databaseId", ""))
    return ""


def parse_marker(text: str, sha: str) -> str:
    """The run id of a `cli/.complete` marker (`<sha> <run id>`) written for `sha`; AssistError otherwise. Exact fields, never a substring (review finding 7c25d047.2)."""
    parts = text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        raise AssistError("cli/.complete reads %r, not `<sha> <run id>`" % text.strip())
    if parts[0] != sha:
        raise AssistError("cli/.complete names sha %s, this release is %s" % (parts[0], sha))
    return parts[1]


def _marker_run(run_id: str, sha: str) -> dict[str, Any]:
    """`gh run view` of the marker's run, proven to be this workflow on `sha` and to carry its creation instant; AssistError otherwise."""
    view = _gh_json(["run", "view", run_id, "--json", "workflowName,headSha,createdAt"])
    if not isinstance(view, dict):
        raise AssistError("gh run view %s gave no answer, so the marker's run is unproven" % run_id)
    if view.get("workflowName") != ASSIST_NAME or view.get("headSha") != sha:
        raise AssistError(
            "the marker names run %s, which is %r on %s, not %s on %s"
            % (run_id, view.get("workflowName"), view.get("headSha"), ASSIST_NAME, sha)
        )
    if not view.get("createdAt"):
        raise AssistError(
            "gh run view %s names no createdAt, so whether the marker is this dispatch's is unproven"
            % run_id
        )
    return view


def assist_fetch(
    version: str,
    sha: str,
    since: str,
    clone: pathlib.Path,
    *,
    timeout: float = 3600.0,
    poll: float = 20.0,
) -> str:
    """Wait for `cli/.complete`, prove it names this sha and a run of this workflow on this sha, fetch the four SEAs into dist/cli and check each against its `.sha256`. Returns the run id."""
    bucket, endpoint, env = _assist_r2(clone)
    prefix = "s3://%s/%s/cli" % (bucket, ASSIST_PREFIX % version)
    deadline = time.monotonic() + timeout
    unknown = 0
    stale = ""
    while True:
        got = _aws(["s3", "cp", "--only-show-errors", prefix + "/.complete", "-"], endpoint, env)
        if got.returncode == 0:
            run_id = parse_marker(got.stdout, sha)
            view = _marker_run(run_id, sha)
            if str(view["createdAt"]) >= since:
                break
            unknown = 0
            # An earlier attempt's assist of the same sha, still in flight when that attempt stopped and queued ahead of this dispatch by the workflow's concurrency group, wrote this marker after the stage-in emptied the prefix. It is not this run's; this run overwrites it (review 0e993d36.2).
            if stale != run_id:
                stale = run_id
                print(
                    "%s: cli/.complete names run %s, created %s before this dispatch at %s: an earlier attempt's, waiting for this run's"
                    % (SELF, run_id, view["createdAt"], since),
                    file=sys.stderr,
                )
        elif re.search(r"Not Found|NoSuchKey|\b404\b|does not exist", got.stderr or ""):
            unknown = 0
        else:
            unknown += 1
            if unknown >= 3:
                raise AssistError(
                    "reading %s/.complete failed 3 times running (aws exited %d); whether the assist finished is unknown"
                    % (prefix, got.returncode)
                )
        failed = assist_failed_run(sha, since)
        if failed:
            raise AssistError(
                "%s run %s on %s failed; no SEA to stage" % (ASSIST_WORKFLOW, failed, sha)
            )
        if time.monotonic() >= deadline:
            raise AssistError("no %s/.complete after %ds" % (prefix, int(timeout)))
        time.sleep(poll)
    dist = clone / "dist" / "cli"
    dist.mkdir(parents=True, exist_ok=True)
    got = _aws(
        [
            "s3",
            "cp",
            "--recursive",
            "--only-show-errors",
            "--exclude",
            ".complete",
            prefix + "/",
            str(dist) + "/",
        ],
        endpoint,
        env,
    )
    if got.returncode != 0:
        raise AssistError("aws s3 cp --recursive %s/ exited %d" % (prefix, got.returncode))
    why = [
        line
        for name in ASSIST_SEAS
        for line in checksum_refusals(dist, dist / ("%s.sha256" % name), (name,))
    ]
    if why:
        raise AssistError("the fetched SEAs are not provably whole: " + "; ".join(why))
    return run_id


def _assist_runs(sha: str, since: str) -> list[dict[str, Any]] | None:
    """This attempt's local-release-assist dispatches on `sha` (created at or after `since`), or None when gh cannot say."""
    rows = _gh_json(
        [
            "run",
            "list",
            "--workflow",
            ASSIST_WORKFLOW,
            "--event",
            "workflow_dispatch",
            "--limit",
            "20",
            "--json",
            "databaseId,headSha,status,createdAt",
        ]
    )
    if not isinstance(rows, list):
        return None
    return [
        r
        for r in rows
        if isinstance(r, dict) and r.get("headSha") == sha and str(r.get("createdAt", "")) >= since
    ]


def assist_cancel(
    sha: str, since: str, *, grace: float = 30.0, wait: float = 180.0, poll: float = 5.0
) -> str:
    """Cancel this attempt's assist run while it is in flight and wait until it has finished, so the on-stop clean is not raced by its upload (review 0e993d36.2). A dispatch can take a few seconds to be listed, so an empty list is re-read for `grace` seconds. AssistError when gh cannot say, a cancel is refused, or the run is still going after `wait`: the clean still runs, and the next stage-in empties the prefix again; `assist_fetch` never reads an earlier attempt's marker as its own."""
    deadline = time.monotonic() + grace
    while True:
        runs = _assist_runs(sha, since)
        if runs is None:
            raise AssistError("gh run list gave no answer; an in-flight assist may still write")
        if runs or time.monotonic() >= deadline:
            break
        time.sleep(poll)
    live = [str(r.get("databaseId", "")) for r in runs if r.get("status") != "completed"]
    if not live:
        return "no assist run of %s since %s is in flight (%d finished)" % (sha, since, len(runs))
    for run_id in live:
        try:
            proc = subprocess.run(
                ["gh", "run", "cancel", run_id],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AssistError("gh run cancel %s failed: %s" % (run_id, exc)) from exc
        if proc.returncode != 0:
            raise AssistError(
                "gh run cancel %s exited %d: %s"
                % (run_id, proc.returncode, (proc.stderr or "").strip()[-300:])
            )
    deadline = time.monotonic() + wait
    while True:
        runs = _assist_runs(sha, since)
        if runs is None:
            raise AssistError(
                "gh run list failed while waiting for the cancelled assist run(s) %s"
                % ", ".join(live)
            )
        going = [str(r.get("databaseId", "")) for r in runs if r.get("status") != "completed"]
        if not going:
            return "cancelled assist run(s) %s" % ", ".join(live)
        if time.monotonic() >= deadline:
            raise AssistError(
                "assist run(s) %s still in flight %ds after the cancel"
                % (", ".join(going), int(wait))
            )
        time.sleep(poll)


def assist_clean(version: str, clone: pathlib.Path) -> str:
    bucket, endpoint, env = _assist_r2(clone)
    prefix = "s3://%s/%s/" % (bucket, ASSIST_PREFIX % version)
    gone = _aws(["s3", "rm", "--recursive", "--only-show-errors", prefix], endpoint, env)
    if gone.returncode != 0:
        raise AssistError("aws s3 rm %s exited %d" % (prefix, gone.returncode))
    return "removed %s" % prefix


def assist_main(argv: list[str]) -> int:
    """`_assist stage-in|fetch|cancel|clean --version V [--sha S --since ISO]`: the local half of local-release-assist.yml's R2 contract, run in the release clone (`stage-in`, `fetch` and `clean` inside an r2-artifacts child). `fetch` prints the assist run id as its last stdout line; `cancel` stops this attempt's in-flight assist on a stop."""
    parser = argparse.ArgumentParser(prog="%s _assist" % SELF)
    parser.add_argument("verb", choices=("stage-in", "fetch", "cancel", "clean"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--sha", default="")
    parser.add_argument("--since", default="")
    parser.add_argument("--timeout", type=float, default=3600.0)
    args = parser.parse_args(argv)
    clone = pathlib.Path.cwd()
    try:
        if args.verb == "stage-in":
            print(assist_stage_in(args.version, clone), file=sys.stderr)
        elif args.verb == "clean":
            print(assist_clean(args.version, clone), file=sys.stderr)
        else:
            if not re.fullmatch(r"[0-9a-f]{40}", args.sha) or not args.since:
                parser.error("%s needs --sha <40 hex> and --since <ISO instant>" % args.verb)
            if args.verb == "cancel":
                print(assist_cancel(args.sha, args.since), file=sys.stderr)
                return 0
            print(assist_fetch(args.version, args.sha, args.since, clone, timeout=args.timeout))
    except AssistError as exc:
        print("%s _assist %s: %s" % (SELF, args.verb, exc), file=sys.stderr)
        return 1
    return 0


def launch_probe_main(argv: list[str]) -> int:
    """`_launch-probe`: does THIS process carry the launch form `release_run.entry_refusal` admits? Interpreter and invocation only; the package check needs a committed tree."""
    del argv
    root = paths.repo_root()
    module = _release_run_module(root)
    pid = os.getpid()
    cmdline, environ, exe = module.proc_cmdline(pid), module.proc_environ(pid), module.proc_exe(pid)
    if cmdline is None or environ is None or exe is None:
        print("unreadable")
        return 1
    why = module.interpreter_refusal(
        cmdline[0] if cmdline else "", exe
    ) or module.invocation_refusal(root, cmdline, environ)
    print(why or "ok")
    return 1 if why else 0


# --------------------------------------------------------------------------- the entry


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="npm run release:local --", description=(__doc__ or "").splitlines()[0]
    )
    parser.add_argument("--channel", required=True, choices=CHANNELS)
    parser.add_argument(
        "--dry-run", action="store_true", help="print every step, read no secret, write nothing"
    )
    parser.add_argument(
        "--workers-only",
        action="store_true",
        help="deploy the edge Workers of the live version only (plan decision 3)",
    )
    parser.add_argument(
        "--regions",
        default="",
        help="comma-separated region ids (default: every region in regions.json)",
    )
    args = parser.parse_args(argv)
    if args.regions and not args.workers_only:
        parser.error("--regions applies to --workers-only")
    return args


def resolve_regions(root: pathlib.Path, raw: str) -> list[str]:
    known = list(read_regions(root))
    if not raw:
        return known
    picked = [r.strip() for r in raw.split(",") if r.strip()]
    unknown = [r for r in picked if r not in known]
    if unknown:
        raise SystemExit(
            "%s: unknown region(s) %s; regions.json has %s"
            % (SELF, ", ".join(unknown), ", ".join(known))
        )
    return picked


def main(
    argv: list[str],
    *,
    root: pathlib.Path | None = None,
    runner: Runner = default_runner,
    gates: Callable[..., GateResult] | None = None,
    internal: dict[str, Callable[[Step, Run], int]] | None = None,
) -> int:
    args = parse(argv)
    if args.channel != CHANNEL:
        print("%s: refused: %s" % (SELF, STABLE_REFUSAL), file=sys.stderr)
        return 2
    root = root or paths.repo_root()
    regions = resolve_regions(root, args.regions)
    ctx = base_context(root, regions, args.workers_only)
    # The webhook check reads each region's production domain, as cd-v2.yml's per-region loop does.
    domains = {r: d.get("domain") or "" for r, d in read_regions(root).items()}
    steps = [_with_domain(s, domains) for s in plan(regions, workers_only=args.workers_only)]

    if args.dry_run:
        return dry_run(root, args, steps, ctx, runner, gates or dry_gates)

    module = _release_run_module(root)
    why = module.entry_refusal(root, os.getpid())
    if why:
        print(
            "%s: refused: this process is not the release entry: %s" % (SELF, why), file=sys.stderr
        )
        print("%s: launch it as `npm run release:local -- --channel edge`" % SELF, file=sys.stderr)
        return 2
    refused = prereq_refusals(args.workers_only)
    if refused:
        for line in refused:
            print("%s: %s" % (SELF, line))
        return 1
    ctx["run_id"] = "%s-%s" % (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()), uuid.uuid4().hex[:8])
    ctx["out"] = str(root / CLONE_REL / ("out-%s" % ctx["run_id"]))
    run = Run(root, ctx, runner=runner, internal={**INTERNAL, **(internal or {})})
    rc = run.execute(steps)
    if run.failed:
        print(
            "%s: stopped at %s; the release record names every step's rc and wall time"
            % (SELF, run.failed),
            file=sys.stderr,
        )
    for line in sealed_untagged(run):
        print("%s: %s" % (SELF, line), file=sys.stderr)
    return rc


def sealed_untagged(run: Run) -> list[str]:
    """The recovery lines when the seal succeeded and the tag push did not (review finding 7c25d047.3).

    `can_fail=False` buys retries with backoff, not certainty: a tag that still fails leaves `cli/v<V>/.released` with no `v<V>`, the bijection break Check Release State reddens main on. No row in the table can recover it, since the push needs the same remote that just failed, so the run says so loudly and names the one command that does, run from the operator's terminal (agent Bash is refused a v* tag push by block_unasked_release).
    """
    outcomes = run.ctx.get("outcomes", {})
    if outcomes.get("seal") != "success" or outcomes.get("tag-push") == "success":
        return []
    version, sha = run.ctx.get("version", "<V>"), run.ctx.get("sha", "<sha>")
    return [
        "SEALED WITHOUT A TAG: cli/v%s/.released exists and v%s was not pushed; Check Release State reddens main until it is."
        % (version, version),
        "  recover from the operator's terminal, in %s:" % run.ctx.get("clone", "<clone>"),
        "  PYTHONPATH=.ci python3 -m rediacc_ci.release.tag --version %s --sha %s --remote origin"
        % (version, sha),
    ]


def _with_domain(step: Step, domains: dict[str, str]) -> Step:
    if "{domain}" not in " ".join(step.argv):
        return step
    region = next((r for r in domains if step.id.endswith("-" + r)), "")
    return dataclasses.replace(
        step, argv=tuple(a.replace("{domain}", domains.get(region, "")) for a in step.argv)
    )


def dry_run(
    root: pathlib.Path,
    args: argparse.Namespace,
    steps: list[Step],
    ctx: Context,
    runner: Runner,
    gates: Callable[..., GateResult],
) -> int:
    print(
        "release:local --channel edge%s (dry run): no secret value is read and nothing is written"
        % (" --workers-only" if args.workers_only else "")
    )
    run = Run(root, ctx, runner=runner, internal={"channel-version": internal_channel_version})
    for step in steps:
        if step.section == "version" and step.readonly and run.run_step(step) != 0:
            break
    version = ctx.get("version")
    print(
        "version: %s%s"
        % (version or "unresolved", " (bump %s)" % ctx["bump"] if "bump" in ctx else "")
    )
    refusals = list(prereq_refusals(args.workers_only))
    result = gates(root, version, ctx)
    refusals += filter_workers(result.refusals, args.workers_only)
    print("gates:")
    for line in [*refusals, *result.notes] or ["local-gates: admitted"]:
        print("  %s" % line)
    print("profiles (key names only):")
    for p in sorted({p for s in steps for p in s.profiles}):
        print("  %s: %s" % (p, " ".join(profile_keys([p]))))
    print("steps (%d):" % len(steps))
    for line in describe(steps, ctx):
        print(line)
    if refusals:
        print("refused: %d refusal(s): %s" % (len(refusals), ", ".join(_codes(refusals))))
        return 1
    print(
        "admitted: every gate passes; the run above is what `npm run release:local -- --channel edge` executes"
    )
    return 0


def _codes(lines: list[str]) -> list[str]:
    """The refusal codes, in order, once each: `ci-quick` from `local-gates: ci-quick: ...`, `prereq:aws` from `prereq: aws: ...`."""
    out: list[str] = []
    for line in lines:
        parts = [p.strip() for p in line.split(":")]
        code = parts[1] if parts[0] == "local-gates" and len(parts) > 1 else ":".join(parts[:2])
        if code not in out:
            out.append(code)
    return out


VERBS = {
    "_bind": bind_main,
    "_write-record": write_record_main,
    "_lock-check": lock_check_main,
    "_provenance": provenance_main,
    "_assist": assist_main,
    "_launch-probe": launch_probe_main,
}


def entry(argv: list[str]) -> int:
    if argv and argv[0] in VERBS:
        return VERBS[argv[0]](argv[1:])
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(entry(sys.argv[1:]))
