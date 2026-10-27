"""Publish an edge release from the local machine (box W2-B of agent/plans/PLAN-local-release.md).

    npm run release:local -- --channel edge [--dry-run] [--workers-only [--regions eu,us]]

npm consumes a `--dry-run` placed before `--`, so the flag goes after it: `npm run release:local -- --channel edge --dry-run`.

EDGE ONLY. Operator ruling ASKED:2026-10-27T09:45Z: "EU/ASIA/US stable should be asked! They're CI/CD only. BUT edge and bench could be released via agent or with CI/CD." `--channel stable` is refused here, with or without `--workers-only`, and names promote-stable.yml; stable is promoted only through CI/CD. cd-v2.yml keeps releasing edge on merge, so this entry is a second edge path, and the two share the release lock: the R2 sentinel `cli/v<V>/.released` and the tag/Release check of `check_existing_release`.

THE LAUNCH FORM. The npm script runs exactly the shape `release_run.entry_refusal` admits (.claude/rediacc_hooks/git/release_run.py, THE ENTRY INVOCATION): `PYTHONPATH="$PWD/.ci" PYTHONPYCACHEPREFIX=/dev/null /usr/bin/python3 -P -s -m rediacc_ci.release.local`. A real run refuses before anything else when this process is not that entry, because the release-run record it writes later would be refused anyway.

ONE DECLARATIVE TABLE. `STEPS` lists every step once: an id, a section, the bws profiles it runs under (none for most), an argv, and whether it can fail. `plan()` expands the per-region rows over the regions and keeps the `workers` rows only under `--workers-only` (plan decision 3). The sections, in order: version, gates, builds (in the release clone, each timed), assist (the local-release-assist dispatch), stage, seal (the sentinel, then the tag at once), publish, deploy (the Worker deploys, each account deploy behind `order.account_refusal` and each with a deploy record), smoke, release (tag-and-release), record.

THE LOCK HOLDS THROUGH THE RUN. The gates judge it once; a concurrent CD edge release can still seal or tag the same version while this run builds. So `lock-check` (the gates' own `local_gates.lock_refusals`, live) runs again before the first stage write and immediately before the seal, and a version taken mid-run stops the run before anything is published.

`can_fail` IS READ AFTER THE SEAL. Every step before the seal may fail and nothing sealed is left behind. After the seal, a failure that leaves `cli/v<V>/.released` with no tag `v<V>` is the CD run 37749637824 case, so the seal and the tag carry `can_fail=False`: the tag immediately follows the seal, and every step that can fail after the seal comes after the tag. A `can_fail=False` step is retried before the run stops. `test_release_local.py` pins those invariants.

PROVENANCE (plan decision 6). Sigstore needs the GitHub OIDC identity, so `provenance` writes `dist/cli/SHA256SUMS` over every Release asset (`create_github_release.release_assets`: `dist/cli/**` and `dist/packages/**`) and its armoured detached signature `dist/cli/SHA256SUMS.asc`, made with the release GPG key of the `release-local` profile in a throwaway GNUPGHOME. Both ride the GitHub Release, whose asset set is `dist/cli/**`.

NO SECRET IN THIS PROCESS. A credentialed step runs as a child `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile <p> -- ...`, so values live only in that child's environment. A step that needs a store name under another spelling (`binds`, the `STORE > LOCAL` grammar of secret-supply.json) or the operator's GitHub token (`gh_env`, read from `gh auth token`) runs its command through the `_bind` verb of this module INSIDE that child. That is how the www Worker gets the unsuffixed `AWS_SES_ACCESS_KEY_ID` / `AWS_SES_SECRET_ACCESS_KEY` it reads while the store holds only the regional pairs: the EU pair is bound under the unsuffixed names for that one child, as cd-deploy-worker.yml does. Every push (the tag, the tap, the Release) uses the session's GitHub token through gh: the clone's credential helper is `gh auth git-credential`, and `GITHUB_PAT` / `GH_TOKEN` come from `gh auth token`. No App token.

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
from rediacc_ci.core import awscli, bws_env
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
RECORD_PREFIX = "release-records/v%s/edge"
ASSIST_WORKFLOW = "local-release-assist.yml"
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
            ("sh", "-c", "exec python3 -m rediacc_ci.release.renet_key_gate private/bin/renet-*"),
            profiles=("release-local",),
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
        # ---- 4. the mac and win SEAs and install legs, on CI (plan: Gaps that stay on CI)
        Step(
            "assist-dispatch",
            "assist",
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
        Step("assist-await", "assist", (), kind="assist-await"),
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
        Step(
            "tag",
            "seal",
            (
                "sh",
                "-c",
                'exec python3 -m rediacc_ci.release.tag --version "$VERSION" --sha "$SHA" --remote origin --bot-name "$GIT_BOT_NAME" --bot-email "$GIT_BOT_EMAIL"',
            ),
            profiles=("release-local",),
            env=(("VERSION", "{version}"), ("SHA", "{sha}")),
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
            ("npx", "tsx", "scripts/stripe-sync.ts"),
            profiles=("release-local",),
            cwd="clone:private/account",
        ),
        Step(
            "stripe-webhook",
            "publish",
            (
                "npx",
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

    def run_step(self, step: Step) -> int:
        started, t0 = _now(), time.monotonic()
        attempts = 1 if step.can_fail else RETRIES_NO_FAIL
        rc, tries = 1, 0
        while tries < attempts:
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


def pushes_for(run: Run) -> list[dict[str, str]]:
    """The pushes this run makes that the git-level pre-push hook judges: the version tag from the release clone."""
    if run.ctx.get("workers_only"):
        return []
    return [
        {
            "toplevel": run.ctx["clone"],
            "remote": "origin",
            "remote_ref": "refs/tags/v%s" % run.ctx["version"],
            "oid": run.ctx["sha"],
        }
    ]


def internal_release_run(step: Step, run: Run) -> int:
    del step
    module = _release_run_module(run.root)
    try:
        path = module.write_release_run(
            run.root,
            run.ctx["run_id"],
            tree=run.ctx["tree"],
            version=run.ctx["version"],
            channel=CHANNEL,
            pushes=pushes_for(run),
        )
    except module.RecordError as exc:
        print("%s: release-run: %s" % (SELF, exc), file=sys.stderr)
        return 1
    run.ctx["release_run"] = str(path)
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
    refusals = filter_workers(
        [ln for ln in lines if ln.startswith("local-gates:") and "admitted" not in ln],
        bool(run.ctx.get("workers_only")),
    )
    if proc.returncode not in (0, 1) or refusals:
        return 1
    return 0


def internal_assist_await(step: Step, run: Run) -> int:
    """Wait for the local-release-assist run dispatched for this version, and take its verdict."""
    del step
    deadline = time.monotonic() + 600
    run_id = ""
    while time.monotonic() < deadline and not run_id:
        proc = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "--workflow",
                ASSIST_WORKFLOW,
                "--limit",
                "20",
                "--json",
                "databaseId,displayTitle,event",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            for row in json.loads(proc.stdout or "[]"):
                if row.get("event") == "workflow_dispatch" and run.ctx["version"] in str(
                    row.get("displayTitle", "")
                ):
                    run_id = str(row["databaseId"])
                    break
        if not run_id:
            time.sleep(15)
    if not run_id:
        print(
            "%s: assist-await: no %s run for v%s appeared"
            % (SELF, ASSIST_WORKFLOW, run.ctx["version"]),
            file=sys.stderr,
        )
        return 1
    run.ctx["assist_run"] = run_id
    return subprocess.run(["gh", "run", "watch", run_id, "--exit-status"], check=False).returncode


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
    "assist-await": internal_assist_await,
    "release-record": internal_release_record,
}


# --------------------------------------------------------------------------- child verbs


def bind_main(argv: list[str]) -> int:
    """`_bind --spec 'STORE > LOCAL' ... --gh-token NAME ... -- CMD`: run inside a `bws_env exec` child, resolve the specs through `bws_env.load` (and NAME from `gh auth token`), exec CMD with them. Prints names only."""
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
    if specs:
        try:
            resolved, missing, _rc = bws_env.load(specs)
        except bws_env.RefusalError as refusal:
            for line in refusal.lines:
                print(line, file=sys.stderr)
            return 1
        if missing:
            return 1
        env.update(resolved)
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
    return rc


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
    "_launch-probe": launch_probe_main,
}


def entry(argv: list[str]) -> int:
    if argv and argv[0] in VERBS:
        return VERBS[argv[0]](argv[1:])
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(entry(sys.argv[1:]))
