"""Release order: may this account pointer reach a channel, given the CLI that channel has published?

`.ci/config/release-requires.json` declares, per entry, an account commit (`since`) from which the account Worker relies on CLI behaviour, and the console commits (`cli_commits`) that carry that behaviour. An entry is ACTIVE once `since` is an ancestor of the account pointer about to be deployed. An active entry admits the deploy only when the channel's published CLI contains every `cli_commits` sha.

THE PUBLISHED CLI IS READ, NEVER ASSUMED. Its version V is the `version` of the R2 `cli/<channel>/manifest.json`, read at the URL `check_edge_manifest` and `check_stable_manifest` read (`RELEASES_ORIGIN + /cli/<channel>/manifest.json`, through `curl`, where only a 404 means no manifest) and parsed by `check_stable_manifest.manifest_version`. V counts only when it is committed in the `release_state_validator` sense: the sentinel `cli/v<V>/.released` exists AND the tag `v<V>` exists. A manifest naming an unsealed or untagged version is a release that never finished, and it admits nothing.

A PROBE THAT COULD NOT ANSWER REFUSES. An unreachable bucket, an unknown commit object or an unparseable manifest answers `unknown: ...`, never a pass: the caller is about to deploy, and an unanswered question is not a yes.

The readers are injected, so the tests run offline; `main` wires the live ones. Usage:

    python3 -m rediacc_ci.release.order --channel edge --account-pointer <sha>

The sentinel probe needs the R2 trio, so a live run goes through
`PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile r2-artifacts -- ...`.
Exit 0 admitted, 1 refused (the reason on stdout), 2 usage or config error.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
from collections.abc import Callable

from rediacc_ci import paths
from rediacc_ci.core import awscli
from rediacc_ci.core import release_state_validator as rsv
from rediacc_ci.release import check_stable_manifest
from rediacc_ci.well_known import RELEASES_ORIGIN

SELF = "rediacc_ci.release.order"
CONFIG_REL = ".ci/config/release-requires.json"
CONFIG_VERSION = 1
CHANNELS = ("edge", "stable")
SHORT = 9

ManifestReader = Callable[[str], "str | None"]
SentinelProbe = Callable[[str], "bool | None"]
TagResolver = Callable[[str], "str | None"]
AncestorProbe = Callable[[pathlib.Path, str, str], "bool | None"]


class ConfigError(Exception):
    """The declaration file is missing, malformed, or of an unknown version."""


def load_entries(root: pathlib.Path | None = None) -> list[dict]:
    """The validated entries of release-requires.json."""
    path = (root or paths.repo_root()) / CONFIG_REL
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError("%s: cannot read %s: %s" % (SELF, CONFIG_REL, exc)) from exc
    if not isinstance(data, dict):
        raise ConfigError("%s: %s is not a JSON object" % (SELF, CONFIG_REL))
    if data.get("version") != CONFIG_VERSION:
        raise ConfigError(
            "%s: %s has version %r, expected %d"
            % (SELF, CONFIG_REL, data.get("version"), CONFIG_VERSION)
        )
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ConfigError("%s: %s has no entries list" % (SELF, CONFIG_REL))
    for entry in entries:
        if not isinstance(entry, dict):
            raise ConfigError("%s: malformed entry in %s: %r" % (SELF, CONFIG_REL, entry))
        since = entry.get("since")
        commits = entry.get("cli_commits")
        if not (
            isinstance(since, dict)
            and isinstance(entry.get("id"), str)
            and isinstance(entry.get("component"), str)
            and isinstance(since.get("repo"), str)
            and isinstance(since.get("commit"), str)
            and isinstance(commits, list)
            and commits
            and all(isinstance(c, str) and c for c in commits)
        ):
            raise ConfigError(
                "%s: malformed entry in %s: %r" % (SELF, CONFIG_REL, entry.get("id", entry))
            )
    return entries


def _short(commits: list[str]) -> str:
    return ", ".join(c[:SHORT] for c in commits)


def git_is_ancestor(repo: pathlib.Path, ancestor: str, descendant: str) -> bool | None:
    """`git -C <repo> merge-base --is-ancestor`: True, False, or None when git could not answer (an unknown object)."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    return None


def account_refusal(
    channel: str,
    account_pointer: str,
    *,
    manifest_reader: ManifestReader,
    sentinel_exists: SentinelProbe,
    tag_commit: TagResolver,
    is_ancestor: AncestorProbe = git_is_ancestor,
    entries: list[dict] | None = None,
    root: pathlib.Path | None = None,
) -> str | None:
    """None when `account_pointer` may reach `channel`, else the first refusal.

    `manifest_reader(channel)` answers the manifest's version ("" for no manifest, "null" for one without a version, None when it could not be read). `sentinel_exists(version)` answers whether `cli/v<version>/.released` exists (None: unknown). `tag_commit(tag)` answers the commit a tag points at, or None when the tag does not exist. `is_ancestor(repo, a, d)` answers git ancestry (None: unknown).
    """
    root = root or paths.repo_root()
    if entries is None:
        entries = load_entries(root)

    active: list[dict] = []
    for entry in entries:
        if entry["component"] != "account":
            continue
        since = entry["since"]
        verdict = is_ancestor(root / since["repo"], since["commit"], account_pointer)
        if verdict is None:
            return (
                "unknown: %s cannot tell whether %s %s is an ancestor of the account pointer %s"
                % (
                    entry["id"],
                    since["repo"],
                    since["commit"][:SHORT],
                    account_pointer[:SHORT],
                )
            )
        if verdict:
            active.append(entry)
    if not active:
        return None

    version = manifest_reader(channel)
    published: str | None = None
    lacking_reason = ""
    if version is None:
        return "unknown: cannot read the published CLI manifest cli/%s/manifest.json" % channel
    if version in ("", "null"):
        lacking_reason = "no CLI version is published on %s" % channel
    else:
        sealed = sentinel_exists(version)
        if sealed is None:
            return "unknown: cannot tell whether cli/v%s/.released exists" % version
        tag_sha = tag_commit("v%s" % version)
        if not sealed:
            lacking_reason = "published v%s is not sealed (cli/v%s/.released is absent)" % (
                version,
                version,
            )
        elif tag_sha is None:
            lacking_reason = "published v%s has no tag v%s" % (version, version)
        else:
            published = tag_sha

    for entry in active:
        commits = entry["cli_commits"]
        head = "cli-behind: %s needs %s in a released CLI on %s" % (
            entry["id"],
            _short(commits),
            channel,
        )
        if published is None:
            return "%s; %s" % (head, lacking_reason)
        missing: list[str] = []
        for commit in commits:
            verdict = is_ancestor(root, commit, published)
            if verdict is None:
                return "unknown: %s cannot tell whether %s is in v%s" % (
                    entry["id"],
                    commit[:SHORT],
                    version,
                )
            if not verdict:
                missing.append(commit)
        if missing:
            return "%s; published v%s lacks them" % (head, version)
    return None


# --------------------------------------------------------------------------- live readers ---------------------------------------------------------------------------


def live_manifest_version(channel: str) -> str | None:
    """The `version` of the live `cli/<channel>/manifest.json`, read the way `check_edge_manifest` reads it."""
    url = RELEASES_ORIGIN + "/cli/%s/manifest.json" % channel
    # The status is read, not `-f`'s exit 22: curl exits 22 on every status of 400 or more, and only a 404 is "no manifest". A 403 or a 5xx is an outage, which could not answer.
    proc = subprocess.run(
        ["curl", "-s", "-w", "\n%{http_code}", url], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        return None
    body, _, status = proc.stdout.rpartition("\n")
    if status == "404":
        return ""
    if status != "200":
        return None
    try:
        return check_stable_manifest.manifest_version(body)
    except json.JSONDecodeError:
        return None


def live_sentinel_exists(version: str) -> bool | None:
    """`release_state_validator.sentinel_exists('cli', 'v<version>')`, with the R2 trio exported the way `reprobe_r2_sentinel` exports it."""
    access = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID")
    secret = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY")
    if not (access and secret and os.environ.get("CLOUDFLARE_R2_ENDPOINT")):
        print(
            "%s: the R2 trio is not set; run under `python3 -m rediacc_ci.core.bws_env exec --profile r2-artifacts --`"
            % SELF,
            file=sys.stderr,
        )
        return None
    # The aws binary is checked first: `sentinel_exists` greps stderr for `not found`, so a missing binary's
    # `aws: command not found` reads as a genuine 404 (NO) rather than UNKNOWN.
    try:
        binary = awscli.resolve()
    except awscli.AwsCliMissingError as exc:
        print("%s: %s" % (SELF, exc), file=sys.stderr)
        return None
    if binary is None:
        print(
            "%s: no aws CLI found; `%s` installs the pin" % (SELF, awscli.INSTALL_HINT),
            file=sys.stderr,
        )
        return None
    os.environ["AWS_ACCESS_KEY_ID"] = access
    os.environ["AWS_SECRET_ACCESS_KEY"] = secret
    os.environ["AWS_DEFAULT_REGION"] = "auto"
    probe = rsv.sentinel_exists("cli", "v%s" % version)
    if probe is rsv.Probe.YES:
        return True
    if probe is rsv.Probe.NO:
        return False
    return None


def live_tag_commit(tag: str, root: pathlib.Path | None = None) -> str | None:
    """`git rev-parse --verify -q <tag>^{commit}` in the console checkout, or None when the tag does not exist."""
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(root or paths.repo_root()),
            "rev-parse",
            "--verify",
            "-q",
            "refs/tags/%s^{commit}" % tag,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    sha = proc.stdout.strip()
    return sha if proc.returncode == 0 and sha else None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m " + SELF, description=__doc__.split("\n", 1)[0]
    )
    parser.add_argument("--channel", required=True, choices=CHANNELS)
    parser.add_argument(
        "--account-pointer", required=True, help="the private/account commit about to be deployed"
    )
    args = parser.parse_args(argv)
    try:
        refusal = account_refusal(
            args.channel,
            args.account_pointer,
            manifest_reader=live_manifest_version,
            sentinel_exists=live_sentinel_exists,
            tag_commit=live_tag_commit,
        )
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if refusal:
        print(refusal)
        return 1
    print("ok: account %s may reach %s" % (args.account_pointer[:SHORT], args.channel))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
