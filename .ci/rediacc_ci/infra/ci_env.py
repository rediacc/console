#!/usr/bin/env python3
"""Port of `.ci/scripts/infra/ci-env.sh`, as a LIBRARY, because the twin is
sourced and never executed.

-----------------------------------------------------------------------------
WHY THERE IS NO CLI TWIN HERE, AND WHY THAT IS NOT A GAP
-----------------------------------------------------------------------------
`.ci/scripts/infra/ci-env.sh` is on the language-policy allowlist with this
reason, and it is still true:

    BLOCKER: sourced only, by ci-start-account.sh and ci-start-elite.sh, to
    export variables into the CALLER's shell -- same contract as the already-
    exempted inject-env.sh and .ci/docker/service/env.sh, a child process
    cannot mutate its parent's environment in any language

Checked again for this port rather than taken from the allowlist: the only two
`source`/`.` call sites in the tree are `ci-start-account.sh:31` and
`ci-start-elite.sh:29`, and the two ports of THOSE scripts
(`infra/ci_start_account.py`, `infra/ci_start_elite.py:123-158`) run the real
bash file through `bash -c '. "$1"; env -0'` and read the exported set back.
Nothing runs it as a program.

So this module follows what the tree already does with a sourced-only twin:
`.ci/scripts/test/proxies/proxy-lib.sh` is ported as the `core.proxyx` library,
and `.ci/scripts/lib/common.sh` as `core.common` plus `core.review_budget` --
pure functions plus a small verb CLI whose only job is to give the shadow
differential a surface to drive. `configure()` is the whole contract; `apply()`
performs the two writes and the printing; the verbs below exist so a differential
can compare the RESULT of sourcing the twin against the result of calling this.

THE CUTOVER THIS ENABLES, stated so nobody mistakes the shape for a dead end:
`ci_start_elite.py` and `ci_start_account.py` currently shell out to bash to get
this environment. When the cutover box lands they can call `configure()` and
drop the `bash -c` hop; that is not this box's call.

-----------------------------------------------------------------------------
WHAT "EQUIVALENT" MEANS FOR A SOURCED SCRIPT: FOUR OBSERVABLES, NOT ONE
-----------------------------------------------------------------------------
  1. the EXPORTED SET the caller is left holding (names AND values, and which
     names are absent -- see the export-without-assignment quirk below);
  2. `$CI_DOCKER_DIR/.env`, byte for byte, which docker compose reads;
  3. what is APPENDED to `$GITHUB_ENV`, which every later workflow step reads;
  4. stdout: up to eight `::add-mask::` directives and the three summary lines,
     in order.

All four are compared by `test_infra_ci_env.py`. Comparing only the exit code
would compare nothing at all: this script has no verdict.

-----------------------------------------------------------------------------
`node`, `openssl` AND `jq` ARE SPAWNED, NOT REIMPLEMENTED
-----------------------------------------------------------------------------
The same argument this wave keeps making, and here it has teeth. The Ed25519
and X25519 keys are DER (`pkcs8`/`spki`) base64 produced by node's own crypto,
and the account server verifies signatures made with them. A Python
reimplementation would have to re-derive the exact encoding, and the first byte
it got wrong would produce a key that looks perfectly well-formed and does not
verify. `KEYGEN_PROGRAM` below is the twin's node program character for
character (asserted against the twin's source by
`test_the_node_programs_are_the_twins_own_text`), the two are handed to the same
`node`, and the two fields come back out through the same `jq -r`.

`openssl rand` likewise: `-base64 48` and `-hex 32` are the twin's, and the
`tr -d '/+=' | cut -c1-64` half is the only piece done in Python -- it is pure
text, and `strip_and_cut` is driven against the real bash pipeline in the tests
rather than trusted.

-----------------------------------------------------------------------------
THREE THINGS THE TWIN DOES THAT LOOK LIKE BUGS. ONE IS.
-----------------------------------------------------------------------------
(a) `export A B` WITH B NEVER ASSIGNED. When `ACCOUNT_ED25519_PRIVATE_KEY` is
    supplied by the caller, the generation block is skipped and
    `ACCOUNT_ED25519_PUBLIC_KEY` is never assigned; `export A B` then MARKS it
    for export without putting it in the environment. So the caller is left
    with a private key and NO public key in `env`, while the `.env` file gets
    `ACCOUNT_ED25519_PUBLIC_KEY=` (empty), because `${VAR}` under `set -e`
    without `set -u` is the empty string. Both halves are reproduced --
    `exported` omits the name, `persisted_block` writes it empty. Pinned by
    `test_a_private_key_without_its_public_leaves_the_public_unexported`.

(b) A FAILING `openssl` IS SILENT, AND THIS IS THE ONE THAT IS A DEFECT.
    Driven against the live twin on 2026-09-13 with an `openssl` that exits 1:

        $ ACCOUNT_SERVER_API_KEY= ... bash -c '. ci-env.sh; echo "[$ACCOUNT_SERVER_API_KEY]"'
        [] ; exit 0

    Three secrets are affected and the script exits 0 with all of them empty or
    stub: `ACCOUNT_SERVER_API_KEY=`, `ACCOUNT_JWT_SECRET=`, and
    `STRIPE_WEBHOOK_SECRET=whsec_test_`. Those values are then written into the
    `.env` file AND appended to `$GITHUB_ENV`, so every later step of the
    workflow runs with an empty API key and an empty JWT secret rather than
    stopping. TWO INDEPENDENT REASONS `set -e` does not catch it, and both have
    to be true at once:
      * there is no `set -o pipefail` here, so `openssl ... | tr | cut` reports
        `cut`'s status, which is 0 on empty input;
      * the assignments are `export VAR=...`, and the exit status of `export` is
        `export`'s own, not the substitution's -- the SC2155 shape. That alone
        would swallow the bare `$(openssl rand -hex 32)` in the Stripe secret,
        which has no pipeline to blame.
    NOT REPAIRED HERE. The fix is a one-line `set -o pipefail` plus splitting
    the three `export VAR=$(...)` into assign-then-export, and it changes what a
    live CI job does when openssl hiccups: today it proceeds with junk, after
    the fix it stops. That is the cutover box's call, not this one's. Reproduced
    faithfully and pinned by `test_a_failing_openssl_yields_empty_secrets`.

(c) `node` OR `jq` FAILING IS **NOT** SILENT, and the asymmetry with (b) is
    worth naming: `KEYS=$(node -e ...)` and `PRIV=$(echo "$KEYS" | jq -r ...)`
    are PLAIN assignments, whose status IS the substitution's, so `set -e` ends
    the sourcing shell with node's or jq's own exit code. Reproduced: `configure`
    raises `ToolFailedError`, and `main` returns that code.

-----------------------------------------------------------------------------
TWO SMALLER FAITHFULNESS NOTES
-----------------------------------------------------------------------------
`set -e` LEAKS INTO THE CALLER. The twin's line 15 runs in the sourcing shell
and stays set after it returns. `ci_start_elite.py` already documents that; a
Python caller of `configure()` has no such side effect, which is a difference in
the port's favour and is listed here rather than hidden.

THE `.env` HEADER LINE IS COPIED WITH ITS PUNCTUATION AS FOUND. It reads
`# Auto-generated by ci-env.sh - do not edit` in the twin with an em dash where
the hyphen is here; the byte sequence is reproduced verbatim in `ENV_HEADER`
because docker compose reads that file and a differential compares it. It is
quoted, not authored.

K=5 LEDGER: `.ci/shadow/w7p6-ci-env.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

# The twin's `node -e "..."` argument, character for character, with the curve
# name as the only substitution. Both occurrences differ in that one word alone.
KEYGEN_PROGRAM = """
        const crypto = require('crypto');
        const { privateKey, publicKey } = crypto.generateKeyPairSync('%s');
        console.log(JSON.stringify({
            private: privateKey.export({type:'pkcs8',format:'der'}).toString('base64'),
            public: publicKey.export({type:'spki',format:'der'}).toString('base64')
        }));
    """

# `openssl rand -base64 48 | tr -d '/+=' | cut -c1-64`.
RAND_BASE64_ARGV = ["openssl", "rand", "-base64", "48"]
STRIP_CHARS = "/+="
CUT_COLUMNS = 64

# `whsec_test_$(openssl rand -hex 32)`.
RAND_HEX_ARGV = ["openssl", "rand", "-hex", "32"]
STRIPE_PREFIX = "whsec_test_"

DEFAULT_REGISTRY = "ghcr.io/rediacc"
DEFAULT_ACTOR = "github-actions"
DEFAULT_TAG = "latest"
DEFAULT_ACCOUNT_URL = "http://account-server:3000"
DEFAULT_CI_MODE = "true"

# `export SYSTEM_X="${SYSTEM_X:-<default>}"`, in the twin's order (:106-114).
SYSTEM_DEFAULTS = (
    ("SYSTEM_DOMAIN", "localhost"),
    ("SYSTEM_ADMIN_EMAIL", "admin@rediacc.io"),
    ("SYSTEM_ADMIN_PASSWORD", "admin"),
    ("SYSTEM_ORGANIZATION_NAME", "Default Organization"),
    ("SYSTEM_DEFAULT_BRIDGE_NAME", "Global Bridges"),
    ("SYSTEM_DEFAULT_REGION_NAME", "Default Region"),
    ("SYSTEM_DEFAULT_TEAM_NAME", "Private Team"),
    ("SYSTEM_PLAN_CODE", "COMMUNITY"),
)

# The seven names masked as a block (:94-100). SYSTEM_ADMIN_PASSWORD is masked
# separately, later, on its own line (:109), and the order matters because
# stdout is one of the four observables.
MASKED = (
    "ACCOUNT_ED25519_PRIVATE_KEY",
    "ACCOUNT_ED25519_PUBLIC_KEY",
    "ACCOUNT_X25519_PRIVATE_KEY",
    "ACCOUNT_X25519_PUBLIC_KEY",
    "ACCOUNT_SERVER_API_KEY",
    "ACCOUNT_JWT_SECRET",
    "STRIPE_WEBHOOK_SECRET",
)

# The `<<ENVBLOCK` heredoc (:136-158). `(name, expansion)` where the expansion
# is the name itself for a plain `${NAME}` and a `(name, default)` pair for the
# two that carry one. THE ORDER IS THE FILE'S CONTENT and is asserted against
# the twin's own heredoc by the tests, because `check-compose-env.sh` parses
# this same block out of the twin to decide whether a compose variable is
# persisted -- a name dropped here is a variable that silently arrives empty in
# a later workflow step.
PERSISTED: tuple[tuple[str, str | None], ...] = (
    ("DOCKER_REGISTRY", None),
    ("TAG", None),
    ("WEB_TAG", None),
    ("SYSTEM_DOMAIN", None),
    ("ENABLE_HTTPS", "false"),
    ("SYSTEM_ADMIN_EMAIL", None),
    ("SYSTEM_ADMIN_PASSWORD", None),
    ("SYSTEM_ORGANIZATION_NAME", None),
    ("SYSTEM_ORGANIZATION_VAULT_DEFAULTS", ""),
    ("SYSTEM_DEFAULT_BRIDGE_NAME", None),
    ("SYSTEM_DEFAULT_REGION_NAME", None),
    ("SYSTEM_DEFAULT_TEAM_NAME", None),
    ("CI_MODE", None),
    ("ACCOUNT_SERVER_URL", None),
    ("ACCOUNT_SERVER_API_KEY", None),
    ("ACCOUNT_ED25519_PRIVATE_KEY", None),
    ("ACCOUNT_ED25519_PUBLIC_KEY", None),
    ("ACCOUNT_X25519_PRIVATE_KEY", None),
    ("ACCOUNT_X25519_PUBLIC_KEY", None),
    ("STRIPE_WEBHOOK_SECRET", None),
    ("ACCOUNT_JWT_SECRET", None),
)

# QUOTED, NOT AUTHORED: the twin's own first line of the .env file, em dash and
# all. See the module docstring.
ENV_HEADER = "# Auto-generated by ci-env.sh -- do not edit"

SUMMARY = (
    "CI environment configured:",
    "  Docker Registry: %s",
    "  Web Tag: %s",
    "  Account Server: %s",
)


class ToolFailedError(Exception):
    """`node` or `jq` exited non-zero inside a PLAIN assignment.

    The twin's `set -e` ends the sourcing shell with that exact status, so the
    status travels with the exception rather than being flattened to 1.
    """

    def __init__(self, code: int, what: str) -> None:
        super().__init__("%s exited %d" % (what, code))
        self.code = code
        self.what = what


class Config:
    """What sourcing the twin leaves behind: the four observables.

    `masks` and `summary` are kept APART rather than as one stdout list because
    they straddle the two writes: the twin prints the mask directives at :94-109
    and the summary at :172-175, with the `.env` write between them. A run whose
    `.env` write fails has therefore already printed the masks and never prints
    the summary, and a port holding one flat list could not reproduce that.
    """

    __slots__ = ("env_file", "env_file_path", "exported", "github_env", "masks", "summary")

    def __init__(
        self,
        exported: dict[str, str],
        masks: list[str],
        summary: list[str],
        env_file: str,
        env_file_path: pathlib.Path,
        github_env: str,
    ) -> None:
        self.exported = exported
        self.masks = masks
        self.summary = summary
        self.env_file = env_file
        self.env_file_path = env_file_path
        self.github_env = github_env

    @property
    def stdout(self) -> list[str]:
        """Every line the twin prints, in order."""
        return [*self.masks, *self.summary]


def console_root() -> pathlib.Path:
    """The twin's `SCRIPT_DIR/../../..` from `.ci/scripts/infra/`.

    This module sits one directory deeper (`.ci/rediacc_ci/infra/`), so the same
    root is `parents[3]` here where the twin's is `parents[2]` of its own
    directory. `rediacc_ci.paths.repo_root()` is deliberately NOT used, for the
    reason `ci_start_elite.py:110-119` already records: it honours
    `$REDIACC_CI_ROOT` and the twin has no such override, so a fixture pointing
    one at a tree and not the other would diverge silently.
    """
    return pathlib.Path(__file__).resolve().parents[3]


def _capture(argv: list[str], what: str) -> str:
    """Run `argv`, return stdout with trailing newlines stripped.

    `$( )` strips trailing newlines and stderr is INHERITED, so node's and jq's
    own diagnostics reach fd 2 exactly as they do in the twin. A non-zero exit
    raises, because both call sites are plain assignments. A missing binary is
    127, which is bash's status for command-not-found.
    """
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, check=False)
    except OSError:
        raise ToolFailedError(127, argv[0]) from None
    if proc.returncode != 0:
        raise ToolFailedError(proc.returncode, what)
    return (proc.stdout or b"").decode("utf-8", "surrogateescape").rstrip("\n")


def _capture_soft(argv: list[str]) -> str:
    """`$(openssl ... )` inside an `export VAR=` -- FAILURE IS SILENT.

    Hazard (b) in the module docstring. A non-zero exit, and a binary that is
    not there at all, both yield the empty string and let the run continue,
    because `export`'s own status is what `set -e` sees.
    """
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, check=False)
    except OSError:
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or b"").decode("utf-8", "surrogateescape").rstrip("\n")


def strip_and_cut(text: str) -> str:
    """`tr -d '/+=' | cut -c1-64`, on one line of openssl output.

    `tr` deletes the three characters anywhere; `cut -c1-64` then takes the
    first 64 CHARACTERS OF EACH LINE. `openssl rand -base64 48` emits exactly
    one 64-character line, so the result is at most 64 characters and usually
    fewer -- the twin's name for this value is a 64-character key and it is
    not one, which is cosmetic and preserved.

    Driven against the real pipeline in `test_strip_and_cut_agrees_with_the_
    bash_pipeline` rather than trusted.
    """
    return "\n".join(
        line.translate({ord(c): None for c in STRIP_CHARS})[:CUT_COLUMNS]
        for line in text.split("\n")
    )


def keypair(curve: str) -> tuple[str, str]:
    """`node -e "<KEYGEN_PROGRAM>"` then `jq -r .private` / `jq -r .public`.

    Two `jq` invocations over one node run, exactly as the twin: the JSON is
    produced once and indexed twice.
    """
    keys = _capture(["node", "-e", KEYGEN_PROGRAM % curve], "node")
    private = _jq(".private", keys)
    public = _jq(".public", keys)
    return private, public


def _jq(program: str, stdin_text: str) -> str:
    """`echo "$KEYS" | jq -r '<program>'`. `echo` appends the newline."""
    try:
        proc = subprocess.run(
            ["jq", "-r", program],
            input=(stdin_text + "\n").encode("utf-8", "surrogateescape"),
            stdout=subprocess.PIPE,
            check=False,
        )
    except OSError:
        raise ToolFailedError(127, "jq") from None
    if proc.returncode != 0:
        raise ToolFailedError(proc.returncode, "jq")
    return (proc.stdout or b"").decode("utf-8", "surrogateescape").rstrip("\n")


def persisted_block(view: dict[str, str]) -> str:
    """The `<<ENVBLOCK` heredoc, expanded. No trailing newline, like `$( )`.

    `view` is the caller's environment WITH this script's exports applied. An
    absent name expands to the empty string: the twin runs `set -e` and never
    `set -u`, so `${ACCOUNT_ED25519_PUBLIC_KEY}` on the export-without-
    assignment path is empty rather than an error. See hazard (a).
    """
    lines = []
    for name, default in PERSISTED:
        # `${NAME}` for a plain name; `${NAME:-<default>}` for the two that
        # carry one, where the default applies to unset AND empty.
        value = view.get(name, "") if default is None else (view.get(name, "") or default)
        lines.append("%s=%s" % (name, value))
    return "\n".join(lines)


def configure(env: dict[str, str] | None = None, root: pathlib.Path | None = None) -> Config:
    """Everything sourcing the twin does, minus the two writes and the printing.

    Returns the four observables. `exported` holds ONLY the names the twin
    leaves in the environment, so a name it marks for export without assigning
    is absent here too (hazard (a)).
    """
    src = dict(os.environ) if env is None else dict(env)
    console = console_root() if root is None else pathlib.Path(root)
    out: dict[str, str] = {}
    masks: list[str] = []

    def view(name: str) -> str:
        """`${NAME:-}` against the exports first, then the caller's env."""
        return out.get(name, src.get(name, ""))

    # :25-27. Plain shell variables, never exported.
    workflow_tag = src.get("TAG", "")
    workflow_ci_mode = src.get("CI_MODE", "")
    workflow_web_tag = src.get("WEB_TAG", "")

    out["DOCKER_REGISTRY"] = src.get("DOCKER_REGISTRY", "") or DEFAULT_REGISTRY
    if src.get("GITHUB_TOKEN", ""):
        out["DOCKER_REGISTRY_USERNAME"] = src.get("GITHUB_ACTOR", "") or DEFAULT_ACTOR
        out["DOCKER_REGISTRY_PASSWORD"] = src["GITHUB_TOKEN"]

    out["TAG"] = workflow_tag or DEFAULT_TAG
    out["WEB_TAG"] = workflow_web_tag or out["TAG"]

    # :51-63 and :68-80. The public key is generated ONLY when the PRIVATE one
    # was absent, which is hazard (a).
    if not src.get("ACCOUNT_ED25519_PRIVATE_KEY", ""):
        private, public = keypair("ed25519")
        out["ACCOUNT_ED25519_PRIVATE_KEY"] = private
        out["ACCOUNT_ED25519_PUBLIC_KEY"] = public
    if not src.get("ACCOUNT_X25519_PRIVATE_KEY", ""):
        private, public = keypair("x25519")
        out["ACCOUNT_X25519_PRIVATE_KEY"] = private
        out["ACCOUNT_X25519_PUBLIC_KEY"] = public

    # :83-90. All three are `export VAR=...`, so a failing openssl is silent.
    out["ACCOUNT_SERVER_API_KEY"] = src.get("ACCOUNT_SERVER_API_KEY", "") or strip_and_cut(
        _capture_soft(RAND_BASE64_ARGV)
    )
    out["ACCOUNT_SERVER_URL"] = src.get("ACCOUNT_SERVER_URL", "") or DEFAULT_ACCOUNT_URL
    out["ACCOUNT_JWT_SECRET"] = src.get("ACCOUNT_JWT_SECRET", "") or strip_and_cut(
        _capture_soft(RAND_BASE64_ARGV)
    )
    out["STRIPE_WEBHOOK_SECRET"] = src.get("STRIPE_WEBHOOK_SECRET", "") or (
        STRIPE_PREFIX + _capture_soft(RAND_HEX_ARGV)
    )

    if src.get("GITHUB_ACTIONS", ""):
        # `echo "::add-mask::$VAR"` with VAR unset prints the bare directive,
        # which is what hazard (a) produces for a missing public key.
        masks.extend("::add-mask::%s" % view(name) for name in MASKED)

    for name, default in SYSTEM_DEFAULTS:
        out[name] = src.get(name, "") or default
        if name == "SYSTEM_ADMIN_PASSWORD" and src.get("GITHUB_ACTIONS", ""):
            # :109, on its own line and AFTER the block above.
            masks.append("::add-mask::%s" % out[name])

    out["CI_MODE"] = workflow_ci_mode or DEFAULT_CI_MODE

    ci_docker_dir = console / ".ci" / "docker" / "ci"
    out["CI_DOCKER_DIR"] = str(ci_docker_dir)
    out["CI_COMPOSE_FILE"] = str(ci_docker_dir / "docker-compose.yml")

    merged = dict(src)
    merged.update(out)
    block = persisted_block(merged)

    summary = [
        SUMMARY[0],
        SUMMARY[1] % out["DOCKER_REGISTRY"],
        SUMMARY[2] % out["WEB_TAG"],
        SUMMARY[3] % out["ACCOUNT_SERVER_URL"],
    ]

    return Config(
        exported=out,
        masks=masks,
        summary=summary,
        env_file="%s\n%s\n" % (ENV_HEADER, block),
        env_file_path=ci_docker_dir / ".env",
        github_env=block + "\n",
    )


def apply(env: dict[str, str] | None = None, root: pathlib.Path | None = None) -> Config:
    """`configure`, then the two writes and the printing, in the twin's order.

    The `.env` write comes FIRST, then `$GITHUB_ENV`, then the summary -- and
    the `::add-mask::` directives were already emitted before either, which is
    what makes them effective for the values the summary then prints.
    """
    src = dict(os.environ) if env is None else dict(env)
    config = configure(src, root)
    # PRINTED BEFORE THE WRITES, because the twin prints them at :94-109 and
    # writes at :165. A failed write must leave the masks already emitted.
    for line in config.masks:
        print(line)
    sys.stdout.flush()
    try:
        config.env_file_path.write_text(config.env_file, encoding="utf-8")
    except OSError as exc:
        # `{ ... } >"$CI_DOCKER_DIR/.env"` failing is a REDIRECTION failure:
        # bash prints `<script>: line 165: <path>: No such file or directory`
        # and `set -e` ends the run with 1. The path and the status are the
        # same here; the wording is this port's own, because inventing bash's
        # line number would be worse than saying which file could not be
        # written.
        raise ToolFailedError(1, "%s: %s" % (config.env_file_path, exc.strerror)) from None
    github_env = src.get("GITHUB_ENV", "")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as handle:
            handle.write(config.github_env)
    for line in config.summary:
        print(line)
    sys.stdout.flush()
    return config


# ---------------------------------------------------------------------------
# CLI -- the surface the shadow differential drives. See the module docstring
# for why this is not a cutover target.
# ---------------------------------------------------------------------------

USAGE = """ci_env -- .ci/scripts/infra/ci-env.sh, which is SOURCED, as a library.

  apply         configure, write the .env file and $GITHUB_ENV, print the summary
  env           apply, then print the resulting environment as NAME=value, sorted
  persisted     print the ENVBLOCK heredoc for the CURRENT environment (no writes)

A child process cannot export into its parent, so there is no verb that
reproduces the twin's actual contract. `env` exists so a differential can
compare `. ci-env.sh; env` against this.
"""

# THE SHELL-PRIVATE NAMES ARE NOT FILTERED HERE, ON PURPOSE. `_`, `SHLVL`, `PWD`
# and `OLDPWD` describe the SHELL rather than the configuration
# (`ci_start_elite.py:107` carries the same set), and comparing them would
# compare bash against python3. But a filter inside the port is a filter the
# twin has no equivalent of, which is exactly the shape that lets a port drop a
# name and still look equal. So `env` prints everything and BOTH SIDES of the
# differential are filtered identically, in the harness.
SHELL_PRIVATE = frozenset({"_", "SHLVL", "PWD", "OLDPWD"})


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE, file=sys.stderr)
        return 2
    verb = argv[0]
    try:
        if verb == "persisted":
            print(persisted_block(dict(os.environ)))
            return 0
        if verb == "apply":
            apply()
            return 0
        if verb == "env":
            config = apply()
            merged = dict(os.environ)
            merged.update(config.exported)
            for name in sorted(merged):
                print("%s=%s" % (name, merged[name]))
            return 0
    except ToolFailedError as failed:
        print("ci_env: %s" % failed, file=sys.stderr, flush=True)
        return failed.code
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
