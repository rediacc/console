#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/deploy-www.sh`.

Deploys the www marketing Worker to Cloudflare. Two lanes, chosen by whether `--name` was passed:

  * PRODUCTION (no `--name`): one `npx wrangler deploy` against
    `workers/www/wrangler.toml` as it stands. No D1 is involved; the account API
    on www.rediacc.com is served by the regional `account-<region>` workers.
    Before it, `www_sitekey_refusal` refuses a `workers/www/dist` whose pages do
    not carry the bound `TURNSTILE_SITE_KEY` (2026-11-12, every www form refused
    every visitor). The twin had no such refusal; its goldens cover only keyed runs.
  * PREVIEW (`--name pr-379`): mint a per-PR D1 database `account-pr-379`,
    DELETING any existing one first for a clean slate, write a generated
    `wrangler.preview.toml` naming that database, apply the account migrations
    to it, deploy, and remove the generated config.

NOTHING HERE REACHES CLOUDFLARE IN A TEST. `npx` (and `npm` on the install branch), `jq` and `sed` are the external tools, so the differential (`.ci/rediacc_ci/tests/test_deploy_deploy_www.py`) puts a RECORDING FAKE for `npx`/`npm` on a scratch PATH and points both sides at a fixture repo root through `$REDIACC_CI_ROOT`. the ledger (deleted in commit:936280cd35) records this path as blocked
only for the "one real run" clause and says in as many words that the mocked parity ledger is a separate, achievable piece of work. This is that piece.

THE CALL LOG IS THE PRIMARY EVIDENCE, as it was for the promote ports. Almost
everything printed is `log_step`/`log_info`, which is chatter by any classifier;
the observable effect of a run is WHICH `npx wrangler` subcommands were invoked, in what order, with what arguments, plus the exact bytes of the generated `wrangler.preview.toml`.

-----------------------------------------------------------------------------
THE EM DASH IN THE GENERATED TOML IS WRITTEN AS `\\u2014`, ON PURPOSE
-----------------------------------------------------------------------------
The twin's heredoc carries one U+2014 in a comment inside the emitted file (twin :123). The house rule bans em dashes in authored text and `check:ci-em-dash-surfaces` scans `.ci/rediacc_ci/**/*.py` for the literal character, so spelling it out here would be a NEW finding in a shrink-only baseline. The escape produces the identical byte sequence in the emitted TOML and leaves no em
dash in this file's own text. The differential asserts the generated file is byte-identical between the two sides, which is what makes the escape safe rather than a quiet edit.

-----------------------------------------------------------------------------
`jq` AND `sed` ARE CALLED, NOT REIMPLEMENTED
-----------------------------------------------------------------------------
`get_d1_uuid` (twin :41-58) is `npx wrangler d1 info --json`, then
`sed -n '/^[[:space:]]*[{[]/,$p'`, then `jq -r '.uuid // empty'`. All three
stages are shelled out:

  * `sed` because the address is a POSIX BRE with a bracket class and a range to
    `$`, and because "print from the first line that starts with optional
    whitespace then `{` or `[`" is not the same as "find the first JSON value".
    A banner line containing a brace LATER in the line does not match; a line
    that is only `[` does.
  * `jq` because `.uuid // empty` is jq's alternative operator, which treats
    `false` and `null` alike, and because jq accepts a STREAM of concatenated
    JSON values and prints one line per value. A `json.loads` port would refuse
    input jq happily reads, and would print one answer where jq prints two.

`require_cmd jq` is in the twin for this reason and is reproduced.

-----------------------------------------------------------------------------
THREE FACTS ABOUT THE TWIN THAT LOOK LIKE MISTAKES. ALL THREE ARE REPRODUCED
-----------------------------------------------------------------------------
  1. THE PRODUCTION-DATABASE GUARD CANNOT FIRE. Twin :69-72 refuses when
     `DB_NAME` is `account-db` or `edge-account-db`, but `DB_NAME` is built two
     lines above as `account-db-pr-${PR_NUM}`, which carries the literal
     `-pr-` infix for EVERY value of `ARG_NAME`, including the empty string
     (`--name=` yields `account-db-pr-`). No input reaches the refusal. It is
     kept because a future edit to the name template is exactly when it would
     start earning its place. `PRODUCTION_GUARD_IS_UNREACHABLE` names it.
  2. `--name` WITH NO VALUE DEPLOYS A PREVIEW WORKER LITERALLY CALLED `true`.
     `common.sh`'s `parse_args` stores the string `true` for a flag with no
     following value, and nothing here validates the shape, so
     `deploy-www.sh --name` mints `account-db-pr-true` and deploys a worker
     named `true`. Driven against the twin 2026-09-13 under the fake `npx`.
     `A_VALUELESS_NAME_DEPLOYS_A_WORKER_CALLED_TRUE` names it.
  3. A NAME THAT IS NOT `pr-N` STILL WORKS, because `${ARG_NAME#pr-}` removes
     the prefix ONLY when it is there. `--name staging` mints
     `account-db-pr-staging` and deploys a worker named `staging`. There is no
     validation; the `pr-` stripping is a convenience, not a contract.

None is repaired here. This wave's acceptance rule is agreement with the live twin; changing what a deploy creates is a cutover-box decision.

-----------------------------------------------------------------------------
A WORD-NAMED PREVIEW KEEPS ITS PR-NUMBERED DATABASE (PLAN-preview-signer D5)
-----------------------------------------------------------------------------
`--name pv-<w>-<w>-<w>` (the name `rediacc_ci.deploy.preview_name` derives) deploys that Worker, and its D1 is still `account-pr-<PR_NUMBER>`: the database is internal, and the seed, the PR-close cleanup and the housekeeping sweep find it by number. A word name without a digits-only `PR_NUMBER` is refused before any call, and so is a `-signer` name. No twin counterpart; every other name keeps the twin's behaviour above.

A word-named preview also gets its own signer and its build identity (PLAN-preview-signer D1, D6, D12), and the generated config differs from the twin's in exactly those lines (`word_preview_toml`):

  * `LICENSE_SIGNER` binds `<name>-signer` (entrypoint `LicenseSigner`, props `{tier = "shared", region = "eu"}`: the preview Worker is that signer's one shared caller), and `SIGNERLESS_PREVIEW` is gone. The signer is deployed by `rediacc_ci.deploy.preview_signer` after the D1 is (re)created and migrated, because it binds that database, and before this Worker's deploy, because wrangler refuses a service binding to a missing Worker.
  * `PREVIEW_BUILD` is a JSON var `{name, version, sha256: {<platform>: <hex>}, formatChange}`: the version and one sha256 per platform from the staged channel manifest (`--manifest <path>`, the `cli/<channel>/manifest.json` the run staged), and `formatChange` from the committed marker `.ci/config/preview-format-change.json` (`{"formats": [...], "reason": "..."}`) or null. A manifest with no binary, a sha256 that is not 64 hex characters, or a malformed marker refuses the run.
  * THE FORMAT BACKSTOP (D12 Option C). `--renet-diff <path>` is the unified diff of `private/renet` between the PR base and head. A changed line that sets a known on-disk format constant (`FORMAT_CONSTANTS`) with no marker file refuses the run before any call, so a forgotten marker never reaches a customer.

All three are refused before any call when missing; nothing falls back to the signerless config.

-----------------------------------------------------------------------------
THE UUID IS LOOKED UP TWICE AND THE SECOND LOOKUP IS THE LOAD-BEARING ONE
-----------------------------------------------------------------------------
The first `get_d1_uuid` only decides whether to delete. After `d1 create` the lookup runs again and an empty answer is fatal, which is the ONE place this script refuses on its own account rather than on a child's exit status. Every other failure path is a bare `set -e` on an unguarded `npx`.

-----------------------------------------------------------------------------
ONE DIVERGENCE, IN TEXT NOBODY PARSES
-----------------------------------------------------------------------------
An argument whose flag is not a valid shell identifier (`--foo.bar=x`) is
`printf -v`'s own failure inside `common.sh:341`, exit 2, and bash names common.sh's path and line. This port prints `rediacc_ci.deploy.deploy_www: printf: ...` with the same status, on the same stream, following `deploy/deploy_account.py` and `autopilot/sweep_collect.py`.

K=5 LEDGER: the ledger (deleted in commit:936280cd35).
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import re
import secrets
import subprocess
import sys
import typing

from rediacc_ci import log
from rediacc_ci.core import common, wrangler
from rediacc_ci.deploy import deploy_record, deploy_signer, preview_name, preview_signer
from rediacc_ci.well_known import APEX_DOMAIN, INFRA_DOMAIN

# This module's own dotted name, the prefix of every diagnostic it prints (the same name `python3 -m` runs it by). A literal, because `__name__` is `__main__` under `-m`.
SELF = "rediacc_ci.deploy.deploy_www"

# `WORKER_DIR="$REPO_ROOT/workers/www"` (twin :17), relative to the repo root
# `common.sh`'s own location resolves to. NOT cwd: the twin can be invoked from anywhere and `.ci/legacy/run-legacy.sh:245` does exactly that.
WORKER_SUBDIR = ("workers", "www")

# `wrangler.toml` (twin :19) and the generated `wrangler.preview.toml` (twin :90, :137, :140, :141). The second is written into the worker directory and removed on the success path only.
PRODUCTION_CONFIG = "wrangler.toml"
PREVIEW_CONFIG = "wrangler.preview.toml"

# `PR_NUM="${ARG_NAME#pr-}"` and `DB_NAME="account-db-pr-${PR_NUM}"`
# (twin :64-65; the port names it `account-pr-<n>` since 2026-11-08). The prefix strip is a `#` expansion, so it removes `pr-` only when the name actually starts with it (fact 3 in the module docstring).
NAME_PREFIX = "pr-"
DB_NAME_TEMPLATE = "account-pr-%s"

# `--location eeur` (twin :82). Hard-coded in the twin; every preview database lands in the same region.
D1_LOCATION = "eeur"

# The two names twin :69 refuses to delete. Unreachable, which is fact 1.
# The `-j` names are the databases created under a jurisdiction (PLAN-d1-eu-jurisdiction Design 1): protected before they exist, so the guard never lags the repoint.
PROTECTED_DATABASES = (
    "account-eu",
    "account-us",
    "account-asia",
    "account-bench",
    "account-eu-j",
    "account-bench-j",
)

# The `sed` address at twin :52 and the `jq` program at twin :57, verbatim.
JSON_START_SED = "/^[[:space:]]*[{[]/,$p"
UUID_JQ = ".uuid // empty"

# The three facts in the module docstring, as constants so a test can assert each by name instead of restating the sentence.
PRODUCTION_GUARD_IS_UNREACHABLE = True
A_VALUELESS_NAME_DEPLOYS_A_WORKER_CALLED_TRUE = True
A_NON_PR_NAME_IS_ACCEPTED_VERBATIM = True

# The generated preview config (twin :90-133), byte for byte after expansion, with ONE Rule-T change: the `[observability]` tables. The twin enabled logs and traces, which Cloudflare persists by default; PLAN-telemetry-export T15 turns them off with persist = false, and the golden records carry that change as `intentional`.
#
# THE U+2014 ON THE `trailingSlash` COMMENT IS THE TWIN'S, written as an escape rather than as the character itself, for the reason in the module docstring. THE BACKTICKS on the `trailingSlash` line are `\`` in the twin's UNQUOTED heredoc, which bash renders as bare backticks; there is no command substitution in the emitted bytes.
#
# `%s` three times, in the twin's order: the worker name, then the database name and its UUID at the bottom.
PREVIEW_TOML = (
    """name = "%s"
main = "src/index.ts"
compatibility_date = "2026-01-20"
compatibility_flags = ["nodejs_compat"]
upload_source_maps = true

[vars]
ALLOWED_EMAIL_DOMAINS = \""""
    + APEX_DOMAIN
    + ""","""
    + INFRA_DOMAIN
    + """\"
# Must be set explicitly. envSchema defaults ENVIRONMENT to "production", so an
# unset value here made every preview worker report environment "production" and
# hand out updateChannel "stable" -- while the install.sh this same worker serves
# bakes in channel pr-N. A CLI installed from a preview would then self-update
# off the wrong channel. See private/account/src/types/env.ts.
ENVIRONMENT = "preview"
# A preview binds no licence signer (PLAN-preview-signer, Context 11): PR-written code must never
# reach a signer holding the production key. This flag, admitted under ENVIRONMENT = "preview"
# alone, lets the account Worker serve without LICENSE_SIGNER; every signing route answers
# 503 SIGNER_NOT_CONFIGURED (private/account src/types/env.ts SIGNERLESS_PREVIEW).
SIGNERLESS_PREVIEW = "true"

# A preview has no OTLP destination, and Cloudflare must store nothing from it
# (persist = false), so logs and traces are off. Mirrors wrangler.toml.
[observability]
enabled = false

[observability.logs]
enabled = false
invocation_logs = false
persist = false

[observability.traces]
enabled = false
persist = false

[assets]
directory = "./dist"
binding = "ASSETS"
not_found_handling = "404-page"
# Match Astro's `trailingSlash: 'never'` so ASSETS does not 307 `/foo`
# to `/foo/`. Without this, the Worker's normalizePath strips the
# trailing slash with a 301 and ASSETS re-adds it \u2014 infinite loop.
# Mirrors the setting in wrangler.{,edge.}toml.
html_handling = "drop-trailing-slash"
run_worker_first = ["/*"]

[[d1_databases]]
binding = "DB"
database_name = "%s"
database_id = "%s"
migrations_dir = "../../private/account/drizzle"

# The www Worker's contact and newsletter routes post through this binding, and the preview binds the bench account Worker so a preview form never reaches production data.
[[services]]
binding = "ACCOUNT"
service = "account-bench"

# The enterprise company lookup. No id: wrangler provisions an empty namespace for this preview on
# deploy, so a preview never reads or writes the production lookup records. Without the binding,
# the pepper and the Turnstile secret, /api/enterprise-lookup answers 503 unavailable.
[[kv_namespaces]]
binding = "ENTERPRISE_LOOKUP"
"""
)


def strip_newlines(token: str) -> str:
    """`printf '%s' "$CLOUDFLARE_API_TOKEN" | tr -d '\\r\\n'` (twin :32).

    NOT shelled out. `tr -d` deletes BYTES, and in UTF-8 neither 0x0D nor 0x0A can appear inside a multi-byte sequence, so deleting the two characters and deleting the two bytes agree for every input. Same ruling and same wording as `deploy/deploy_account.py`, which carries the identical line.

    ONLY THE TOKEN IS CLEANED. `CLOUDFLARE_ACCOUNT_ID` with a stray carriage
    return is passed to children untouched, exactly as in the twin.
    """
    return token.replace("\r", "").replace("\n", "")


def db_name_for(worker_name: str) -> str:
    """`PR_NUM="${ARG_NAME#pr-}"; DB_NAME="account-pr-${PR_NUM}"` (twin :64-65, renamed from `account-db-pr-`).

    `removeprefix` IS the `#` expansion: it strips only when the prefix is present and leaves everything else alone. That is fact 3 in the module docstring, and it is why `--name staging` is accepted.
    """
    return DB_NAME_TEMPLATE % worker_name.removeprefix(NAME_PREFIX)


def preview_db_name(worker_name: str, pr_number: str) -> tuple[str | None, str]:
    """The D1 name for a preview Worker, or (None, refusal).

    A word-named preview (`pv-<w>-<w>-<w>`) keeps the PR-numbered database `account-pr-<PR_NUMBER>`; any other name goes through `db_name_for`, as in the twin.
    """
    if not preview_name.is_preview_worker(worker_name):
        return db_name_for(worker_name), ""
    if worker_name.endswith("-signer"):
        return None, "the www preview is never deployed under a -signer name"
    if not pr_number.isascii() or not pr_number.isdigit():
        return None, "a word-named preview needs PR_NUMBER (digits) for its account-pr-<n> database"
    return DB_NAME_TEMPLATE % pr_number, ""


# ---- a word-named preview's signer and build identity (PLAN-preview-signer D1, D6, D12) ----

# The twin's signerless lines, and what a word-named preview carries in their place.
SIGNERLESS_BLOCK = (
    "# A preview binds no licence signer (PLAN-preview-signer, Context 11): PR-written code must never\n"
    '# reach a signer holding the production key. This flag, admitted under ENVIRONMENT = "preview"\n'
    "# alone, lets the account Worker serve without LICENSE_SIGNER; every signing route answers\n"
    "# 503 SIGNER_NOT_CONFIGURED (private/account src/types/env.ts SIGNERLESS_PREVIEW).\n"
    'SIGNERLESS_PREVIEW = "true"\n'
)
SIGNER_SERVICE = (
    "\n# The preview's own signer (rediacc_ci.deploy.preview_signer): a fresh delegated key per deploy,\n"
    "# certified by signer-bench-eu for this preview's pv- subscriptions only. Never the production key.\n"
    "[[services]]\n"
    'binding = "LICENSE_SIGNER"\n'
    'service = "%s"\n'
    'entrypoint = "LicenseSigner"\n'
    'props = { tier = "shared", region = "eu" }\n'
)
FORMAT_MARKER = (".ci", "config", "preview-format-change.json")
# The on-disk format constants of private/renet (Context 20): a PR that changes one may leave data the pre-preview renet refuses after `rdc preview leave`, so it must carry the marker.
FORMAT_CONSTANTS = {
    "pkg/functions/vault/schema.go": ("VaultSchemaID", "VaultVersion"),
    "pkg/chunkstore/manifest.go": ("ManifestVersion",),
    "pkg/chunkstore/journal.go": ("JournalVersion",),
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PreviewBuildError(Exception):
    """A word-named preview cannot be deployed: the manifest, the marker or the format backstop refused it."""


def preview_build(name: str, manifest_text: str, marker_text: str | None) -> dict:
    """`PREVIEW_BUILD` from the staged channel manifest and the optional marker file."""
    try:
        manifest = json.loads(manifest_text)
    except ValueError as exc:
        raise PreviewBuildError("the channel manifest is not JSON (%s)" % exc) from None
    version = manifest.get("version") if isinstance(manifest, dict) else None
    binaries = manifest.get("binaries") if isinstance(manifest, dict) else None
    if not isinstance(version, str) or not version:
        raise PreviewBuildError("the channel manifest names no version")
    if not isinstance(binaries, dict) or not binaries:
        raise PreviewBuildError("the channel manifest lists no binary")
    sha256: dict[str, str] = {}
    for platform, entry in sorted(binaries.items()):
        digest = entry.get("sha256") if isinstance(entry, dict) else None
        if not isinstance(digest, str) or not SHA256_RE.match(digest):
            raise PreviewBuildError(
                "the channel manifest's %s entry has no valid sha256" % platform
            )
        sha256[platform] = digest
    return {
        "name": name,
        "version": version,
        "sha256": sha256,
        "formatChange": format_change(marker_text),
    }


def format_change(marker_text: str | None) -> dict | None:
    """The marker file's `{formats, reason}`, or None when there is no marker."""
    if marker_text is None:
        return None
    try:
        marker = json.loads(marker_text)
    except ValueError as exc:
        raise PreviewBuildError("%s is not JSON (%s)" % ("/".join(FORMAT_MARKER), exc)) from None
    formats = marker.get("formats") if isinstance(marker, dict) else None
    reason = marker.get("reason") if isinstance(marker, dict) else None
    if (
        not isinstance(formats, list)
        or not formats
        or not all(isinstance(f, str) and f for f in formats)
        or not isinstance(reason, str)
        or not reason.strip()
    ):
        raise PreviewBuildError(
            '%s must be {"formats": ["<format>", ...], "reason": "<one line>"}'
            % "/".join(FORMAT_MARKER)
        )
    return {"formats": formats, "reason": reason.strip()}


def format_constant_changes(diff_text: str) -> list[str]:
    """`<file>: <constant>` for every changed line of a unified diff that sets a known format constant."""
    found: list[str] = []
    current = ""
    for line in diff_text.splitlines():
        if line.startswith(("+++ ", "--- ")):
            path = line[4:].strip()
            if path != "/dev/null":
                current = path.split("/", 1)[1] if path[:2] in ("a/", "b/") else path
            continue
        if not line.startswith(("+", "-")):
            continue
        for suffix, names in FORMAT_CONSTANTS.items():
            if not current.endswith(suffix):
                continue
            for constant in names:
                if re.search(r"\b%s\b\s*=" % constant, line[1:]):
                    hit = "%s: %s" % (suffix, constant)
                    if hit not in found:
                        found.append(hit)
    return found


def word_preview_toml(worker_name: str, db_name: str, db_uuid: str, build: dict) -> str:
    """The twin's preview config with the signerless lines replaced by `PREVIEW_BUILD`, and the preview's own `LICENSE_SIGNER` appended."""
    body = preview_toml(worker_name, db_name, db_uuid)
    if body.count(SIGNERLESS_BLOCK) != 1:
        raise PreviewBuildError("the preview config template lost its signerless block")
    build_line = (
        "# The build this preview serves (PLAN-preview-signer D6), returned by server-info as previewBuild.\nPREVIEW_BUILD = %s\n"
        % json.dumps(json.dumps(build, sort_keys=True, separators=(",", ":")))
    )
    body = body.replace(SIGNERLESS_BLOCK, build_line)
    return body + SIGNER_SERVICE % preview_signer.signer_name(worker_name)


def word_preview_inputs(worker_name: str, args: dict, root: pathlib.Path) -> dict:
    """Read and check `--manifest`, `--renet-diff` and the marker for a word-named preview; the `PREVIEW_BUILD` value."""
    manifest_path = args.get("ARG_MANIFEST", "")
    diff_path = args.get("ARG_RENET_DIFF", "")
    if not manifest_path or manifest_path == "true":
        raise PreviewBuildError(
            "a word-named preview needs --manifest <staged cli/<channel>/manifest.json>"
        )
    if not diff_path or diff_path == "true":
        raise PreviewBuildError(
            "a word-named preview needs --renet-diff <private/renet diff, base..head>"
        )
    try:
        manifest_text = pathlib.Path(manifest_path).read_text(encoding="utf-8")
        diff_text = pathlib.Path(diff_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise PreviewBuildError("could not read %s (%s)" % (exc.filename, exc.strerror)) from None
    marker = root.joinpath(*FORMAT_MARKER)
    marker_text = marker.read_text(encoding="utf-8") if marker.is_file() else None
    changes = format_constant_changes(diff_text)
    if changes and marker_text is None:
        raise PreviewBuildError(
            "this PR changes an on-disk format constant (%s) and carries no %s; add the marker so `rdc preview use` warns before a switch"
            % (", ".join(changes), "/".join(FORMAT_MARKER))
        )
    return preview_build(worker_name, manifest_text, marker_text)


def is_protected(db_name: str) -> bool:
    """`[[ "$DB_NAME" == "account-db" || "$DB_NAME" == "edge-account-db" ]]` (twin :69), over the shared databases that replaced those two names.

    Exact string comparison against the literals. Unreachable from `db_name_for`, which is fact 1; exported so the differential can assert both halves rather than assert the sentence.
    """
    return db_name in PROTECTED_DATABASES


def info_argv(db_name: str) -> list[str]:
    """`npx wrangler d1 info "$db_name" --json` (twin :44)."""
    return [*wrangler.ARGV, "d1", "info", db_name, "--json"]


def delete_argv(db_name: str) -> list[str]:
    """`npx wrangler d1 delete "$DB_NAME" --skip-confirmation` (twin :77)."""
    return [*wrangler.ARGV, "d1", "delete", db_name, "--skip-confirmation"]


def create_argv(db_name: str) -> list[str]:
    """`npx wrangler d1 create "$DB_NAME" --location eeur` (twin :82)."""
    return [*wrangler.ARGV, "d1", "create", db_name, "--location", D1_LOCATION]


def migrations_argv(db_name: str) -> list[str]:
    """`npx wrangler d1 migrations apply "$DB_NAME" --remote --config ...` (twin :137)."""
    return [
        *wrangler.ARGV,
        "d1",
        "migrations",
        "apply",
        db_name,
        "--remote",
        "--config",
        PREVIEW_CONFIG,
    ]


def preview_deploy_argv() -> list[str]:
    """`npx wrangler deploy --config wrangler.preview.toml` (twin :140)."""
    return [*wrangler.ARGV, "deploy", "--config", PREVIEW_CONFIG]


def production_deploy_argv() -> list[str]:
    """`npx wrangler deploy` (twin :146). No config flag at all."""
    return [*wrangler.ARGV, "deploy"]


def preview_toml(worker_name: str, db_name: str, db_uuid: str) -> str:
    """The heredoc at twin :90-133, expanded.

    THE TRAILING NEWLINE IS THE HEREDOC'S. A `cat > f <<TOML` writes each line
    with its newline, so the file ends with exactly one.
    """
    return PREVIEW_TOML % (worker_name, db_name, db_uuid)


def get_d1_uuid(db_name: str) -> str:
    """`get_d1_uuid` (twin :41-58), as the same three programs.

    THREE EARLY RETURNS, all producing the empty string:

      1. `npx wrangler d1 info ... 2>/dev/null || true` produced nothing. Its
         STDERR IS DISCARDED and its exit status is thrown away, so an
         unauthenticated wrangler and a database that does not exist are the
         same answer here.
      2. The `sed` range matched no line, so there was output but no JSON.
      3. `jq` printed nothing, either because `.uuid` was absent or because jq
         itself failed (`2>/dev/null || true` again).

    Command substitution strips ALL trailing newlines from each stage, so the caller's `[[ -n "$DB_UUID" ]]` sees the empty string in all three cases and a bare UUID otherwise.

    `echo "$output" | sed ...` APPENDS A NEWLINE that `output` may not have had. That is reproduced, because a final line without one would otherwise not be a line to `sed`.
    """
    info = subprocess.run(
        info_argv(db_name),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    output = info.stdout.decode("utf-8", "surrogateescape").rstrip("\n")
    if not output:
        return ""

    sed = subprocess.run(
        ["sed", "-n", JSON_START_SED],
        input=(output + "\n").encode("utf-8", "surrogateescape"),
        stdout=subprocess.PIPE,
        check=False,
    )
    json_start = sed.stdout.decode("utf-8", "surrogateescape").rstrip("\n")
    if not json_start:
        return ""

    jq = subprocess.run(
        ["jq", "-r", UUID_JQ],
        input=(json_start + "\n").encode("utf-8", "surrogateescape"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return jq.stdout.decode("utf-8", "surrogateescape").rstrip("\n")


PEPPER_ENV = "ENTERPRISE_LOOKUP_PEPPER"
TURNSTILE_ENV = "CLOUDFLARE_TURNSTILE_SECRET_KEY"

# Cloudflare's published Turnstile dummy value that siteverify answers success for on every token. A preview holds it instead of the production value, so the lookup route works on a preview and no production value leaves its Worker.
TURNSTILE_ALWAYS_PASSES = "1x0000000000000000000000000000000AA"

# The www pages' client bundles, relative to the worker directory: Astro writes them to `dist/assets` (packages/www astro.config build.assets) and the deploy copies `packages/www/dist` into `workers/www/dist`. The portal's own bundles sit under `dist/account/assets`, which a non-recursive glob here does not read.
WWW_ASSETS = ("dist", "assets")
SITEKEY_SHAPE = re.compile(r"^0x[0-9A-Za-z_-]{16,}$")
WWW_REBUILD_HINT = (
    'rebuild with PUBLIC_TURNSTILE_SITE_KEY="$TURNSTILE_SITE_KEY" npm run build -w @rediacc/www'
    " and copy packages/www/dist into workers/www/dist"
)


def www_sitekey_refusal(worker_dir: pathlib.Path, env: typing.Mapping[str, str]) -> str | None:
    """None when the built www pages under `dist/assets` carry the Turnstile site key the environment binds, else the refusal line.

    Seven www forms (contact, newsletter, lead magnet, partner application, ROI calculator, region lookup) read `PUBLIC_TURNSTILE_SITE_KEY` at build time, and the servers behind them verify every token, so a keyless build refuses every visitor (production 2026-11-12). Only the production lane calls this: a PR preview's pages come from the keyless `build-www` artifact on purpose.
    """
    key = (env.get("TURNSTILE_SITE_KEY") or "").strip()
    if not key:
        return (
            "TURNSTILE_SITE_KEY is not bound, so the www pages cannot be checked for the captcha"
            " widget; run under the deploy-workers profile"
        )
    if not SITEKEY_SHAPE.match(key):
        return "TURNSTILE_SITE_KEY does not look like a Turnstile sitekey (0x...)"
    assets = worker_dir.joinpath(*WWW_ASSETS)
    bundles = sorted(assets.glob("*.js")) if assets.is_dir() else []
    if not bundles:
        return "no built www pages at %s; %s" % (assets, WWW_REBUILD_HINT)
    for bundle in bundles:
        if key in bundle.read_text(encoding="utf-8", errors="replace"):
            return None
    return (
        "the built www pages at %s (%d bundles) carry no Turnstile site key, so every www form"
        " would refuse every visitor; %s" % (assets, len(bundles), WWW_REBUILD_HINT)
    )


def pepper_put_argv() -> list[str]:
    """`npx wrangler secret put ENTERPRISE_LOOKUP_PEPPER`: the value arrives on stdin, never on argv."""
    return [*wrangler.ARGV, "secret", "put", PEPPER_ENV]


def secret_put_argv(name: str) -> list[str]:
    """`npx wrangler secret put <name> --config wrangler.preview.toml`: the value arrives on stdin, never on argv."""
    return [*wrangler.ARGV, "secret", "put", name, "--config", PREVIEW_CONFIG]


def _push_preview_secrets() -> int:
    """The two secrets /api/enterprise-lookup needs on a preview, pushed to the preview Worker after its deploy: a pepper and the Turnstile dummy value.

    The pepper is a fresh random value per deploy, never the production `ENTERPRISE_LOOKUP_PEPPER` the run may carry: a preview serves PR-branch code at a public URL, so it must hold no production secret. The preview binds its own empty `ENTERPRISE_LOOKUP` namespace (`preview_toml`) that nothing seeds (`rediacc_ci.ops.enterprise_lookup` writes the production namespace with the production pepper), so any pepper answers its lookups correctly, as misses.
    """
    pushes = [
        (PEPPER_ENV, secrets.token_hex(32)),
        (TURNSTILE_ENV, TURNSTILE_ALWAYS_PASSES),
    ]
    for name, value in pushes:
        log.step("Pushing the %s preview Worker secret" % name)
        sys.stdout.flush()
        sys.stderr.flush()
        status = subprocess.run(
            secret_put_argv(name), input=value.encode("utf-8"), check=False
        ).returncode
        if status != 0:
            return status
    return 0


def _push_pepper() -> int:
    """Push the enterprise-lookup HMAC pepper as a Worker secret, when the run carries one.

    The www Worker's enterprise-lookup route keys its KV records with this pepper (`workers/www/src/enterprise-lookup.ts`), and `rediacc_ci.ops.enterprise_lookup` holds the same value, so a Worker without it answers every lookup as unconfigured. The `deploy-workers` profile in `.ci/config/secret-supply.json` lists the name as required, so a release run that reaches this point always has it; a run without it (the twin's differential, a hand deploy) skips the push and says nothing, which keeps the twin's streams unchanged.
    """
    pepper = os.environ.get("ENTERPRISE_LOOKUP_PEPPER", "")
    if not pepper:
        return 0
    log.step("Pushing the %s Worker secret" % PEPPER_ENV)
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.run(pepper_put_argv(), input=pepper.encode("utf-8"), check=False).returncode


def _deploy_production() -> int:
    status = _run(production_deploy_argv())
    if status != 0:
        return status
    return _push_pepper()


def _run(argv: list[str]) -> int:
    """One child with BOTH streams inherited, as the twin leaves them.

    wrangler's own output is the entire visible result of a good run; capturing it would move it out of the workflow log. Python's buffers are flushed first so the `log_step` line that precedes a call cannot land after the call's output.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.run(argv, check=False).returncode


def _preview(worker_name: str, worker_dir: pathlib.Path, args: dict | None = None) -> int:
    """The `if [[ -n "${ARG_NAME:-}" ]]` arm (twin :60-141), plus a word-named preview's signer and build identity."""
    log.step("Deploying preview worker: %s" % worker_name)

    pr_number = os.environ.get("PR_NUMBER", "")
    db_name, refusal = preview_db_name(worker_name, pr_number)
    if db_name is None:
        log.error(refusal)
        return 1
    word = preview_name.is_preview_worker(worker_name)
    build: dict | None = None
    if word:
        try:
            build = word_preview_inputs(worker_name, args or {}, common.repo_root())
        except PreviewBuildError as exc:
            log.error(str(exc))
            return 1
    if is_protected(db_name):
        # UNREACHABLE (fact 1). Reproduced rather than dropped.
        log.error("CRITICAL: refusing to delete production/edge database: %s" % db_name)
        return 1

    if get_d1_uuid(db_name):
        log.step("Deleting existing D1 database: %s (clean slate)" % db_name)
        status = _run(delete_argv(db_name))
        if status != 0:
            return status  # `set -e`
        log.info("Deleted %s" % db_name)

    log.step("Creating D1 database: %s" % db_name)
    status = _run(create_argv(db_name))
    if status != 0:
        return status  # `set -e`

    db_uuid = get_d1_uuid(db_name)
    if not db_uuid:
        log.error("Failed to retrieve UUID for newly created D1 database: %s" % db_name)
        return 1
    log.info("Created D1 database %s (UUID: %s)" % (db_name, db_uuid))

    # `cat >wrangler.preview.toml <<TOML` (twin :90). RELATIVE to the worker directory, because the twin has already `cd`-ed there.
    config = worker_dir / PREVIEW_CONFIG
    if build is not None:
        config.write_text(word_preview_toml(worker_name, db_name, db_uuid, build), encoding="utf-8")
    else:
        config.write_text(preview_toml(worker_name, db_name, db_uuid), encoding="utf-8")

    log.step("Applying migrations to %s..." % db_name)
    status = _run(migrations_argv(db_name))
    if status != 0:
        return status  # `set -e`, and the generated config is LEFT BEHIND
    log.info("Migrations applied to %s" % db_name)

    if word:
        # The signer binds the database just migrated, and wrangler refuses this Worker's LICENSE_SIGNER binding while the signer is missing.
        log.step("Deploying the preview's own signer")
        sys.stdout.flush()
        try:
            preview_signer.deploy(
                common.repo_root(),
                name=worker_name,
                pr=pr_number,
                db_id=db_uuid,
                env=os.environ,
                run=deploy_signer.run_process,
            )
        except deploy_signer.RefusedError as exc:
            for line in exc.lines:
                log.error(line)
            return 1
        except wrangler.WranglerNotInstalledError as exc:
            log.error("%s: %s" % (SELF, exc))
            return 1

    status = _run(preview_deploy_argv())
    if status != 0:
        return status  # `set -e`, config left behind again

    status = _push_preview_secrets()
    if status != 0:
        return status  # config left behind, as for a failed deploy

    # `rm -f wrangler.preview.toml` (twin :141). Only on the success path, which is why a failed deploy leaves a generated config in the worker directory.
    with contextlib.suppress(FileNotFoundError):  # `-f`
        config.unlink()
    return 0


# Every `ARG_*` key `main` reads; any other flag is refused before a side effect.
ACCEPTED_ARGS = frozenset({"ARG_NAME", "ARG_MANIFEST", "ARG_RENET_DIFF"})


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv, allowed=ACCEPTED_ARGS)
    except common.RefusalError as exc:
        # THE DIVERGENCE: bash names common.sh's path and line here.
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    worker_dir = common.repo_root().joinpath(*WORKER_SUBDIR)

    if not (worker_dir / PRODUCTION_CONFIG).is_file():
        log.error("www worker not found at %s" % worker_dir)
        return 1

    # `cd "$WORKER_DIR"` (twin :24). Every later relative path is the worker directory's, and `npx` resolves its local `node_modules/.bin` from cwd.
    os.chdir(worker_dir)

    # `require_var CLOUDFLARE_API_TOKEN` then `require_var CLOUDFLARE_ACCOUNT_ID` (twin :26-27), IN THAT ORDER: a run missing both names the token.
    #
    # THE TWO NAMES ARE ALSO READ HERE WITH LITERAL KEYS, and the redundancy is deliberate. `check:ci-python-env-registry` derives a module's declared inputs by walking the AST for `os.environ[...]` / `os.environ.get(...)`, and it cannot see a read that happens inside `core.common.require_var`. Without these two reads `CLOUDFLARE_ACCOUNT_ID` is an input nobody declared. The REFUSAL
    # still goes through `require_var`, because its message and exit status are the twin's and restating them here would let the two drift.
    credentials = {
        "CLOUDFLARE_API_TOKEN": os.environ.get("CLOUDFLARE_API_TOKEN", ""),
        "CLOUDFLARE_ACCOUNT_ID": os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
    }
    for name in credentials:
        try:
            common.require_var(name)
        except common.RefusalError as exc:
            exc.report()
            return exc.code

    try:
        common.require_cmd("jq")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    # `export CLOUDFLARE_API_TOKEN` after the strip: children see the clean one.
    os.environ["CLOUDFLARE_API_TOKEN"] = strip_newlines(os.environ["CLOUDFLARE_API_TOKEN"])

    # `if [[ ! -d "node_modules" ]]` (twin :36). RELATIVE, so the worker directory's, and unlike `deploy-account.sh` there is no `command -v wrangler` half: a machine with a global wrangler still runs `npm install` here when the worker directory has no `node_modules`.
    if not (worker_dir / "node_modules").is_dir():
        status = _run(["npm", "install"])
        if status != 0:
            return status  # `set -e`

    worker_name = args.get("ARG_NAME", "")
    if worker_name:
        return _preview(worker_name, worker_dir, args)

    # Before the production deploy, never after: a keyless www dist refuses every form submission.
    refusal = www_sitekey_refusal(
        worker_dir, {"TURNSTILE_SITE_KEY": os.environ.get("TURNSTILE_SITE_KEY", "")}
    )
    if refusal:
        log.error(refusal)
        return 1

    log.step("Deploying www production worker...")
    return deploy_record.record_www_deploy(
        worker_dir, PRODUCTION_CONFIG, "www-stable", _deploy_production
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
