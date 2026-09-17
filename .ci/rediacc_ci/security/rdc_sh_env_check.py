#!/usr/bin/env python3
"""Port of `.ci/scripts/test/test-rdc-sh-env.sh` (gate `check:ci-rdc-sh-env`).

Leak test for `rdc.sh`'s dev path. Two layers:

  Layer 1 (static): `rdc.sh` must never `source` (or `set -a` + source)
    `private/account/.env`, and the only variables it exports must be the
    allowlist {PATH, REDIACC_CONFIG, NODE_COMPILE_CACHE}. This is the
    structural guarantee that the private ED25519/X25519/JWT/API secrets in
    that env file cannot reach the CLI process.

  Layer 2 (functional): run the real dev path against a fixture ROOT_DIR whose
    `private/account/.env` carries the two public values PLUS sentinel secret
    lines. `node` and `curl` are PATH-shimmed. The dumped CLI environment must
    carry `REDIACC_CONFIG=dev` and none of the sentinels, and the seeded
    `dev.json` must have the fixture's accountServer.

REGISTERED CI GATE: `check:ci-rdc-sh-env`, step "rdc.sh env tests" in
`.github/workflows/ci-quality.yml`, job `quality-static`.

WHAT MOVES AND WHAT DOES NOT. The HARNESS moves to Python: the greps, the
fixture tree, the two shims, the tally and the exit code. The SUBJECT stays
bash and is still driven as bash -- layer 2 runs the real `rdc.sh` under
`bash`, because a Python reimplementation of the wrapper would be a second
instrument certifying itself.

PORT NOTES, each one driven before it was written down.

THE OUTPUT IS BYTE-IDENTICAL, ANSI escapes and U+2713/U+2717 glyphs included.
This is a registered gate whose stdout a human reads in a CI log, so the
`\\033[0;32m` / `\\033[0;31m` pairs are emitted literally rather than through
any formatting helper, and every message is copied verbatim from the twin.

THE "node not found" BRANCH OF THE TWIN IS DEAD CODE, and this port reproduces
the death rather than the branch. `test-rdc-sh-env.sh:93` reads
`REAL_NODE="$(command -v node)"` under `set -euo pipefail`; an assignment whose
value is a command substitution takes that substitution's exit status, so when
`node` is absent bash exits 1 right there and the `if [[ -z "$REAL_NODE" ]]`
guard on :94-97 never runs. Driven:
`bash -c 'set -euo pipefail; X="$(command -v nope)"; echo REACHED'` prints
nothing and exits 1. So `_real_node()` below raises `SilentExitError`, which
`main` turns into a bare rc=1 with NOTHING on either stream -- exactly what the
twin does, and deliberately NOT the friendlier message the twin's own author
intended. (The house rule is that a missing tool should fail loudly with the
fix in the message; that fix belongs in the twin, which is not this file's to
edit, and forging the message here would make the port disagree with its twin.)

`grep -q ... && pass ...` DOES NOT ABORT WHEN THE GREP FAILS, even under
`set -e`, because a command that is not the last in an `&&` list is exempt and
the list's own failure does not trip the option. Driven:
`bash -c 'set -euo pipefail; if true; then false && echo x; fi; echo AFTER'`
prints `AFTER`. So :156's second `REDIACC_CONFIG=dev` check simply prints no
PASS line when it fails; it is not a silent early exit. Ported as a plain `if`.

THE 1d PASS LINE IS UNCONDITIONAL, and that is the twin's behaviour, not a bug
this port tidied. `test-rdc-sh-env.sh:78-84` runs the dead-surface loop, each
iteration able to call `fail`, and then calls `pass` on :84 regardless. A run
that finds `RDC_BENCH` still referenced therefore prints BOTH the failure and
"no removed token/mode surface". Reproduced.

THE EXPORT SET IS SORTED IN BYTE ORDER. The twin pipes through `sort -u`, whose
collation follows the locale; this repo runs under `LANG=C.UTF-8` where that is
byte order, and all three allowlisted names are pure ASCII with the underscore
never adjacent to a decision. `sorted()` is therefore exact here, and
`test_security_rdc_sh_env_check.py` pins it by running the real `sort -u`
against the real `rdc.sh` rather than asserting the equivalence from the
manual.

THE ONE THING THIS PORT CANNOT KEEP is the shell's own `mktemp -d` name: both
sides make their own fixture directory. Nothing in the twin's output quotes one
on the green path, which is why the differential can compare bytes; the single
red path that can (`cat "$FIX/run.err"`) is normalized in the differential and
masked by the shadow-gate ledger's own `<tmp>` rule.

Exit: 0 when no check failed, 1 otherwise.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# The three names `rdc.sh` is allowed to export, in the twin's own spelling and order (`test-rdc-sh-env.sh:73`) -- which is `sort -u` order, not the order the comment on :68 lists them in.
ALLOWLIST = "NODE_COMPILE_CACHE PATH REDIACC_CONFIG"

# The removed token/mode surface. Fixed strings (`grep -qF`), not patterns.
DEAD_SURFACE = (
    "REDIACC_SUBSCRIPTION_TOKEN_FILE",
    "REDIACC_ENVIRONMENT",
    "RDC_BENCH",
    ".rdc-dev",
    ".rdc-bench",
)

# The four private names that must never appear as a variable in the CLI's env.
SECRET_NAMES = (
    "ACCOUNT_ED25519_PRIVATE_KEY",
    "ACCOUNT_X25519_PRIVATE_KEY",
    "ACCOUNT_JWT_SECRET",
    "ACCOUNT_SERVER_API_KEY",
)

# POSIX `[[:space:]]` inside a single line. `\n` is excluded on purpose: these patterns are applied line by line, exactly as `grep -E` applies them.
_SP = r"[ \t\v\f\r]"

# `^[[:space:]]*set[[:space:]]+-a([[:space:]]|$)` (test-rdc-sh-env.sh:53)
SET_A_RE = re.compile(r"^%s*set%s+-a(%s|$)" % (_SP, _SP, _SP))

# `(^[[:space:]]*(source|\.)[[:space:]]).*(account_env|private/account/\.env)` (test-rdc-sh-env.sh:60)
SOURCE_ENV_RE = re.compile(r"(^%s*(source|\.)%s).*(account_env|private/account/\.env)" % (_SP, _SP))

# `^[[:space:]]*export[[:space:]]+[A-Za-z_][A-Za-z0-9_]*` (test-rdc-sh-env.sh:70)
EXPORT_RE = re.compile(r"^%s*export%s+([A-Za-z_][A-Za-z0-9_]*)" % (_SP, _SP))

FIXTURE_ENV = """REDIACC_ACCOUNT_SERVER=http://127.0.0.1:9
ACCOUNT_X25519_PUBLIC_KEY=stubpublickey
ACCOUNT_ED25519_PRIVATE_KEY=LEAKSENTINEL_ED25519
ACCOUNT_X25519_PRIVATE_KEY=LEAKSENTINEL_X25519
ACCOUNT_JWT_SECRET=LEAKSENTINEL_JWT
ACCOUNT_SERVER_API_KEY=LEAKSENTINEL_API
"""

FIXTURE_CONSTANTS = "NODE_VERSION_MIN=18\n"

FIXTURE_LOCAL_COMMON = """log_info() { echo "INFO: $*" >&2; }
log_warn() { echo "WARN: $*" >&2; }
log_error() { echo "ERROR: $*" >&2; }
log_step() { echo "STEP: $*" >&2; }
check_node_version() { :; }
ensure_deps() { :; }
ensure_packages_built() { :; }
ensure_cli_built() { :; }
ensure_renet_built() { :; }
"""

# The twin's heredoc is UNQUOTED, so `$REAL_NODE` and `$DUMP` are expanded when
# the shim is written and `\$@` / `\${1:-}` survive into the shim.
NODE_SHIM = """#!/usr/bin/env bash
if [[ "${1:-}" == "-e" ]]; then
    exec "%(node)s" "$@"
fi
env >"%(dump)s"
exit 0
"""

CURL_SHIM = """#!/usr/bin/env bash
exit 0
"""


class SilentExitError(Exception):
    """`set -e` killing the twin mid-script: rc=1, nothing on either stream."""


class Tally:
    """The twin's PASS/FAIL counters and its two output helpers."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def fail(self, message: str) -> None:
        self.failed += 1
        print("  %s\u2717%s %s" % (RED, NC, message), file=sys.stderr, flush=True)

    def ok(self, message: str) -> None:
        self.passed += 1
        print("  %s\u2713%s %s" % (GREEN, NC, message), flush=True)


# --------------------------------------------------------------------------- Pure helpers. Exported so the differential can drive them without a fixture. ---------------------------------------------------------------------------


def has_set_a(text: str) -> bool:
    """`grep -nE '^[[:space:]]*set[[:space:]]+-a([[:space:]]|$)'`, per line."""
    return any(SET_A_RE.search(line) for line in text.split("\n"))


def sources_account_env(text: str) -> bool:
    """`grep -nE '(^[[:space:]]*(source|\\.)[[:space:]]).*(account_env|...)'`."""
    return any(SOURCE_ENV_RE.search(line) for line in text.split("\n"))


def exported_names(text: str) -> str:
    """`grep -oE ... | awk '{print $2}' | sort -u | tr '\\n' ' ' | sed 's/ $//'`.

    The awk step takes field 2 of the MATCHED TEXT, which is always the variable
    name whether or not the line was indented, because `grep -o` prints only the
    match and the leading whitespace is not a field.
    """
    names = {m.group(1) for line in text.split("\n") if (m := EXPORT_RE.search(line))}
    return " ".join(sorted(names))


def grep_lines(text: str, pattern: re.Pattern[str]) -> list[str]:
    """Every line matching, as `grep` would print them (no trailing newline)."""
    return [line for line in text.split("\n") if pattern.search(line)]


# --------------------------------------------------------------------------- Layer 1 ---------------------------------------------------------------------------


def layer_one(tally: Tally, rdc_sh_text: str) -> None:
    print("Layer 1 (static): rdc.sh export allowlist + no-source tombstone", flush=True)

    if has_set_a(rdc_sh_text):
        tally.fail("rdc.sh contains a 'set -a' statement (env-export leak vector)")
    else:
        tally.ok("no 'set -a' statement")

    if sources_account_env(rdc_sh_text):
        tally.fail("rdc.sh sources the account env file (secret leak vector)")
    else:
        tally.ok("does not source private/account/.env")

    exported = exported_names(rdc_sh_text)
    if exported == ALLOWLIST:
        tally.ok("exports exactly the allowlist: %s" % exported)
    else:
        tally.fail("export set is [%s]; expected [%s]" % (exported, ALLOWLIST))

    if "export REDIACC_CONFIG=dev" not in rdc_sh_text:
        tally.fail("dev path must export REDIACC_CONFIG=dev")
    for dead in DEAD_SURFACE:
        if dead in rdc_sh_text:
            tally.fail("rdc.sh still references removed token/mode surface: %s" % dead)
    # UNCONDITIONAL in the twin (:84), even when the loop above just failed.
    tally.ok(
        "no removed token/mode surface (REDIACC_SUBSCRIPTION_TOKEN_FILE / "
        "REDIACC_ENVIRONMENT / RDC_BENCH / .rdc-{dev,bench})"
    )


# --------------------------------------------------------------------------- Layer 2 ---------------------------------------------------------------------------


def _real_node() -> str:
    """`REAL_NODE="$(command -v node)"` under `set -e`. See the module docstring."""
    found = shutil.which("node")
    if found is None:
        raise SilentExitError
    return found


def build_fixture(fix: pathlib.Path, rdc_sh: pathlib.Path, real_node: str) -> pathlib.Path:
    """Everything between `FIX="$(mktemp -d)"` and the `env -i` run (:99-141)."""
    fix_root = fix / "root"
    fix_home = fix / "home"
    shim = fix / "shim"
    dump = fix / "cli-env.dump"
    for target in (
        fix_root / ".ci" / "config",
        fix_root / ".ci" / "lib",
        fix_root / "private" / "account",
        fix_root / "packages" / "cli" / "dist",
        fix_root / ".claude" / "skills" / "rdc",
        fix_home,
        shim,
    ):
        target.mkdir(parents=True, exist_ok=True)

    # `cp "$RDC_SH" "$FIX_ROOT/rdc.sh"` -- ROOT_DIR derives from the copy's own location, so the copy exercises the same code against fixture siblings.
    shutil.copy2(rdc_sh, fix_root / "rdc.sh")

    (fix_root / ".ci" / "config" / "constants.sh").write_text(FIXTURE_CONSTANTS, encoding="utf-8")
    (fix_root / ".ci" / "lib" / "local-common.sh").write_text(
        FIXTURE_LOCAL_COMMON, encoding="utf-8"
    )
    (fix_root / "private" / "account" / ".env").write_text(FIXTURE_ENV, encoding="utf-8")
    (fix_root / "packages" / "cli" / "dist" / "cli-bundle.cjs").write_text(
        "// fixture bundle\n", encoding="utf-8"
    )
    # Pre-seed the skill reference so rdc.sh's regen check is skipped (ref newer than the bundle -> no `npx tsx` invocation).
    (fix_root / ".claude" / "skills" / "rdc" / "reference.md").write_text(
        "# reference\n", encoding="utf-8"
    )
    (fix_root / ".claude" / "skills" / "rdc" / "reference.md").touch()

    node_shim = shim / "node"
    node_shim.write_text(NODE_SHIM % {"node": real_node, "dump": dump}, encoding="utf-8")
    node_shim.chmod(0o755)
    curl_shim = shim / "curl"
    curl_shim.write_text(CURL_SHIM, encoding="utf-8")
    curl_shim.chmod(0o755)
    return fix_root


def run_dev_path(fix: pathlib.Path, fix_root: pathlib.Path) -> int:
    """`env -i PATH=... HOME=... bash "$FIX_ROOT/rdc.sh" --dev config current`.

    The environment is built from scratch (two names), which is what `env -i`
    plus two assignments produces; bash then adds its own `PWD`/`SHLVL`/`_` on
    both sides identically.
    """
    with (fix / "run.out").open("wb") as out, (fix / "run.err").open("wb") as err:
        return subprocess.run(
            ["bash", str(fix_root / "rdc.sh"), "--dev", "config", "current"],
            env={"PATH": "%s:/usr/bin:/bin" % (fix / "shim"), "HOME": str(fix / "home")},
            stdout=out,
            stderr=err,
            check=False,
        ).returncode


def _json_field(config: pathlib.Path, expression: str) -> str:
    """The twin's `python3 -c ... || echo PARSE_ERR`, run in-process.

    The twin redirects the child's stderr to `/dev/null` here
    (`test-rdc-sh-env.sh:172`), so nothing of CPython's traceback is
    observable and reading the JSON in-process is exact. Its sibling
    `test-install-sh-config.sh:98` does NOT redirect, which is why THAT port
    shells out instead.
    """
    try:
        with config.open(encoding="utf-8") as handle:
            account = json.load(handle)["account"]
        return expression_value(account, expression)
    except Exception:  # noqa: BLE001 -- the twin swallows every failure the same way
        return "PARSE_ERR"


def expression_value(account: dict[str, object], expression: str) -> str:
    """The two accessor spellings the twin uses, kept apart as the twin does.

    `['accountServer']` RAISES on a config with no such key (PARSE_ERR), while
    `.get('e2ePublicKey','')` returns the empty string. That asymmetry is the
    twin's (`test-rdc-sh-env.sh:172-173`) and is preserved.
    """
    if expression == "accountServer":
        return str(account["accountServer"])
    return str(account.get("e2ePublicKey", ""))


def layer_two(tally: Tally, fix: pathlib.Path, rdc_sh: pathlib.Path) -> None:
    print("Layer 2 (functional): dev path seeds config, leaks no secrets", flush=True)

    real_node = _real_node()
    fix_root = build_fixture(fix, rdc_sh, real_node)
    dump = fix / "cli-env.dump"

    if run_dev_path(fix, fix_root) != 0:
        print("dev path exited non-zero:", file=sys.stderr, flush=True)
        sys.stderr.write((fix / "run.err").read_text(encoding="utf-8", errors="replace"))
        sys.stderr.flush()
        tally.fail("rdc.sh --dev exited non-zero")

    if not dump.is_file():
        tally.fail("CLI env dump not produced (dev path did not reach exec node)")
    else:
        text = dump.read_text(encoding="utf-8", errors="replace")
        config_line = re.compile(r"^REDIACC_CONFIG=dev$")
        if not grep_lines(text, config_line):
            tally.fail("CLI env missing REDIACC_CONFIG=dev")
        leaks = grep_lines(text, re.compile("LEAKSENTINEL"))
        if leaks:
            tally.fail(
                "SECRET LEAK: sentinel value reached the CLI environment: %s" % "\n".join(leaks)
            )
        else:
            tally.ok("no sentinel secret value in CLI environment")
        for name in SECRET_NAMES:
            if grep_lines(text, re.compile("^%s=" % re.escape(name))):
                tally.fail("SECRET LEAK: %s present in CLI environment" % name)
        # `grep -q ... && pass ...`: no PASS line when the grep fails, and no early exit either. See the module docstring.
        if grep_lines(text, config_line):
            tally.ok("CLI environment carries REDIACC_CONFIG=dev only")

    dev_json = fix / "home" / ".config" / "rediacc" / "dev.json"
    if not dev_json.is_file():
        tally.fail("seeder did not create %s" % dev_json)
    else:
        got_server = _json_field(dev_json, "accountServer")
        got_key = _json_field(dev_json, "e2ePublicKey")
        if got_server != "http://127.0.0.1:9":
            tally.fail("dev.json accountServer=%s (expected http://127.0.0.1:9)" % got_server)
        if got_key != "stubpublickey":
            tally.fail("dev.json e2ePublicKey=%s (expected stubpublickey)" % got_key)
        if got_server == "http://127.0.0.1:9" and got_key == "stubpublickey":
            tally.ok("dev.json seeded with accountServer + e2ePublicKey from the env file")


# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:  # noqa: ARG001 -- the twin takes no arguments
    rdc_sh = paths.repo_root() / "rdc.sh"
    if not rdc_sh.is_file():
        print("FAIL: rdc.sh not found at %s" % rdc_sh, file=sys.stderr, flush=True)
        return 1

    tally = Tally()
    fix = pathlib.Path(tempfile.mkdtemp())
    try:
        layer_one(tally, rdc_sh.read_text(encoding="utf-8", errors="replace"))
        layer_two(tally, fix, rdc_sh)
    except SilentExitError:
        return 1
    finally:
        shutil.rmtree(fix, ignore_errors=True)

    print(flush=True)  # the twin's bare `echo ""`
    print("Passed: %d" % tally.passed, flush=True)
    print("Failed: %d" % tally.failed, flush=True)
    return 1 if tally.failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
