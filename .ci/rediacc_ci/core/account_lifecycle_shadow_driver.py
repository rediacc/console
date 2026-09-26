#!/usr/bin/env python3
"""Both sides of the `core.account_lifecycle` port differential, in one file.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.account_lifecycle_shadow_driver --side old --twin .ci/lib/account.sh --port .ci/rediacc_ci/core/account_lifecycle.py <scenario>
    PYTHONPATH=.ci python3 -m rediacc_ci.core.account_lifecycle_shadow_driver --side new --twin .ci/lib/account.sh --port .ci/rediacc_ci/core/account_lifecycle.py <scenario>

A SECOND DRIVER AND A SECOND PAIR (`w7p5b-account-lifecycle`) FOR THE SAME TWIN, on the `local_common_actions_shadow_driver.py` precedent: `core/shadow_driver.py` compares the deterministic half's answers inside one bash process per side, and this one runs every case as its OWN PROCESS per side with the external programs stubbed (`core/stubfarm.py`). RUN AS A MODULE, never by path, for the reason
`core/shadow_driver.py` records.

-----------------------------------------------------------------------------
WHAT A CASE PRINTS
-----------------------------------------------------------------------------
    obs <case> rc=<n>
    obs <case> out#<i>| <line>      stdout, numbered
    obs <case> err#<i>| <line>      stderr, numbered, bash's `<file>: line <N>: ` stamp dropped on both sides
    obs <case> call#<i>| <argv>     every LOGGED stub call, in order
    obs <case> side#<i>| <line>     what a foreground stub chose to record (an environment it was started with, the state file it saw)
    obs <case> bg| <argv>           every call to a BACKGROUND program, SORTED
    obs <case> child alive=<0|1>    whether the real process a cleanup case started survived it
    obs <case> foreign alive=<0|1>  the same for a process the DRIVER owns, so the side cannot `wait` it away
    obs <case> tree| <entry>        every path under the sandbox, with a content hash for files

THE BACKGROUND CALLS ARE SORTED, AND THAT IS THE ONE PLACE ORDER IS GIVEN UP. `account_dev` starts Astro and Vite with `&` and `account_stripe_auto` starts `stripe listen` the same way, and each of those races the foreground's own probes into one transcript. A background program (`stripe` always, `npx` in the `dev` cases) is therefore stubbed UNLOGGED and records its argv into a separate file, printed sorted, so the comparison
still sees every argument of every call and does not see which process the scheduler ran first.
TWO HANDSHAKES REMOVE THE OTHER RACES rather than sorting them away. The `stripe listen` stub waits for the foreground's first `sleep 1` before it prints its `whsec_` line, so exactly one sleep is ever logged on the happy path; and the dev gateway stub waits until the forked `account_dev_credentials` job has made its LAST logged call (`hostname -I`), so the credentials banner lands before the gateway returns.

-----------------------------------------------------------------------------
THE SANDBOX LIVES AT ONE FIXED PATH ON BOTH SIDES, UNDER A LOCK
-----------------------------------------------------------------------------
`ensure_deps` hashes absolute paths into its stamp, so each case builds `<tmp>/rediacc-account-lifecycle/{root,farm}` from nothing, and the run holds an `flock` on `<tmp>/rediacc-account-lifecycle.lock`, exactly as `local_common_actions_shadow_driver.py` does and for the same reason. The directory is removed after every case.
`.ci/lib`, `.ci/config`, `.ci/rediacc_ci`, `.ci/scripts/lib`, `.devcontainer` and `scripts` are SYMLINKS back to this checkout, so the code under comparison is the tracked code. `private/account` is a real per-case fixture with its own `dev.defaults.env`, never the real submodule. Both sides run with `CONSOLE_ROOT_DIR`, `REDIACC_CI_ROOT` and `PYTHONPATH` pointing into it, so the
`PYTHONPATH` the twin hands `bws_env` is the same string on both sides.

STUBBED AND LOGGED: `docker`, `curl`, `npm`, `npx` (outside `dev`), `lsof`, `pgrep`, `kill` (the PROGRAM, which the twin reaches through `xargs`), `sleep`, `ss` (how `rediacc_ci.core.ports` probes, on both sides), `openssl`, `hostname`, and the `build-packages.sh` path stub. STUBBED, NOT LOGGED: `node` (`-v` and the cpu-features buildcheck answered, everything else passed to the real node), `date` (`+%s` frozen), and in the `reset` cases `python3`, whose two
`bws_env` calls record themselves on the side channel with the LENGTH of each key they were handed, never a value. Everything else is the real program.

-----------------------------------------------------------------------------
THE SCENARIOS
-----------------------------------------------------------------------------
  helpers      `account_load_defaults` (the shell wins, an absent file, an unreadable one), `account_state_gateway_port` over five state-file shapes, `account_docker_ghost_clean` at every early return and with ids to remove, and `account_cleanup` propagating an exit code and killing a REAL child it was handed.
  stripe       `account_stripe_auto` with no key, no CLI, the happy path, stale listeners to kill, a thirty-sleep timeout, and a failing product sync (twin behaviour 5).
  credentials  `account_dev_credentials` never healthy, healthy late, an existing store, no store, a failed provisioning call, the silent deaths on an unreadable seed answer (twin behaviour 3) and a failing `hostname -I` (4), a JSON array answer, and a failing `openssl`.
  seed         `account_seed_demo`'s refusals, the four ways it finds a port, a non-200 answer with and without a JSON body, the dead "Could not reach" branch (twin behaviour 1), and no `jq`.
  reset        `account_reset` whole, with the Bitwarden push failing, the cache refresh failing, no database files, an old node, and a failing `openssl`.
  test         `account_test` passing arguments through, vitest failing, and no node.
  e2e          `account_test_e2e` finding its port three ways and not at all, a gateway that is not up, the webhook and sandbox switches, a failing install, and a failing Playwright run.
  dev          `account_dev` end to end: reusing a live RustFS, stopping a previous instance, no Docker with Stripe on, starting RustFS, RustFS never answering, Astro never starting, a pinned port that is busy, stale installs, a failing gateway, and a state file missing its key.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import fcntl
import hashlib
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

from rediacc_ci.core import account_lifecycle as lifecycle
from rediacc_ci.core.stubfarm import Farm

if TYPE_CHECKING:  # annotation-only import
    from collections.abc import Mapping

EXIT_CANNOT_RUN = 77
BASE_NAME = "rediacc-account-lifecycle"
FIXED_MTIME = 1700000000
FROZEN_NOW = 1700003725

LOGGED = (
    "docker",
    "curl",
    "npm",
    "npx",
    "lsof",
    "pgrep",
    "kill",
    "sleep",
    "ss",
    "openssl",
    "hostname",
)
BACKGROUND = ("stripe",)

FN = {
    "load-defaults": "account_load_defaults",
    "state-gateway-port": "account_state_gateway_port",
    "cleanup": "account_cleanup",
    "docker-ghost-clean": "account_docker_ghost_clean",
    "stripe-auto": "account_stripe_auto",
    "dev-credentials": "account_dev_credentials",
    "seed-demo": "account_seed_demo",
    "reset": "account_reset",
    "test": "account_test",
    "test-e2e": "account_test_e2e",
    "dev": "account_dev",
}


@dataclasses.dataclass
class Case:
    name: str
    verb: str
    args: list[str] = dataclasses.field(default_factory=list)
    rows: list[dict] = dataclasses.field(default_factory=list)
    env: Mapping[str, str | None] = dataclasses.field(default_factory=dict)
    setup: tuple[str, ...] = ()
    hidden: tuple[str, ...] = ()
    unstub: tuple[str, ...] = ()
    background: tuple[str, ...] = BACKGROUND
    show: tuple[str, ...] = ()
    pids: bool = False
    pre: str = ""
    python_stub: bool = False


def row(name: str, glob: str = "*", **kw) -> dict:
    return {"name": name, "glob": glob, **kw}


# ------------------------------------------------------------------ stub behaviours

RECORD = 'line="$me"; for a in "$@"; do line+=" $(printf "%%q" "$a")"; done; printf "%%s\\n" "$line" >>"$STUB_ROOT/%s"; '
BG = RECORD % "bg.log"
SIDE = RECORD % "side.log"


def envdump(*names: str) -> str:
    """A stub snippet recording the environment it was started with, on the side channel. Unset and empty are told apart."""
    parts = [
        'if [ -n "${%(n)s+x}" ]; then printf "env %(n)s=%%s\\n" "$%(n)s"; else printf "env %(n)s unset\\n"; fi'
        % {"n": name}
        for name in names
    ]
    return '{ %s; printf \'cwd %%s\\n\' "$PWD"; } >>"$STUB_ROOT/side.log"; ' % "; ".join(parts)


def keylens(*names: str) -> str:
    """The LENGTH of each named variable, never its value."""
    parts = ['v="${%s-}"; printf "len %s=%%s\\n" "${#v}"' % (n, n) for n in names]
    return '{ %s; } >>"$STUB_ROOT/side.log"; ' % "; ".join(parts)


# The state file the gateway sees, with every pid masked to `N` so the COUNT and the SEPARATOR are compared and the numbers, which differ per run, are not. The writer stamp is reduced to whether it is present: its value names this machine, and `account_writer_stamp` agreeing with `account.writer_stamp()` is pinned by its own test.
STATE_DUMP = (
    'while IFS= read -r l; do case "$l" in pids=*) printf "state pids=%s\\n" "$(printf "%s" "${l#pids=}" | tr -s "0-9" "N")";; '
    'writer=?*) printf "state writer=<stamp>\\n";; '
    '*) printf "state %s\\n" "$l";; esac; done <"$CONSOLE_ROOT_DIR/.account-state" >>"$STUB_ROOT/side.log"; '
)
WAIT_FOR_JOB = (
    'for i in $(seq 200); do grep -q "^hostname" "$STUB_LOG" && break; "$SHADOW_REAL_SLEEP" 0.05; done; '
    '"$SHADOW_REAL_SLEEP" 0.3; '
)
STRIPE_READY = (
    'for i in $(seq 200); do [ -f "$STUB_ROOT/go" ] && break; "$SHADOW_REAL_SLEEP" 0.05; done; '
    "printf 'Ready! Your webhook signing secret is whsec_shadowsecret0123456789 (^C to quit)\\n'; "
    ': >"$STUB_ROOT/written"'
)
# A job whose program leaves a long-lived CHILD behind it and waits: the pid file names the child, so `child_alive()` reports whether the cleanup reached past the pid it tracks.
TREE_JOB = '"$SHADOW_REAL_SLEEP" 30 & printf "%s\\n" "$!" >"$STUB_ROOT/child.pid.tmp"; mv "$STUB_ROOT/child.pid.tmp" "$STUB_ROOT/child.pid"; wait'
SLEEP_HANDSHAKE = (
    ': >"$STUB_ROOT/go"; for i in $(seq 200); do [ -f "$STUB_ROOT/written" ] && break; '
    '"$SHADOW_REAL_SLEEP" 0.05; done; "$SHADOW_REAL_SLEEP" 0.1'
)
NPM_ROOT_INSTALL = (
    "mkdir -p node_modules/.bin node_modules/@rediacc node_modules/cpu-features; "
    "printf '#!/bin/sh\\n' > node_modules/.bin/tsx; chmod +x node_modules/.bin/tsx; "
    "ln -sfn ../../packages/cli node_modules/@rediacc/cli; "
    "printf '// buildcheck\\n' > node_modules/cpu-features/buildcheck.js"
)
BUILD_PACKAGES = 'mkdir -p "$CONSOLE_ROOT_DIR/packages/shared/dist" "$CONSOLE_ROOT_DIR/packages/provisioning/dist"'
BUSY = "LISTEN 0 4096 0.0.0.0:%d 0.0.0.0:*\n"
RUSTFS_PROBE = "-s -o /dev/null -m 2 -w %{http_code} http://127.0.0.1:9100/"
HEALTH = "-sf -m 2 http://127.0.0.1:%d/health"
API = "http://127.0.0.1:%d/account/api/v1/test/"
SEED_URL = "-sS -m 60 *"
GATEWAY_ENV = (
    "GATEWAY_PORT",
    "VITE_PORT",
    "ASTRO_PORT",
    "CONFIG_R2_ENDPOINT",
    "CONFIG_R2_BUCKET",
    "CONFIG_R2_ACCESS_KEY_ID",
    "CONFIG_R2_SECRET_ACCESS_KEY",
    "CONFIG_RUSTFS_PORT",
    "WEBAUTHN_RP_ID",
    "WEBAUTHN_ORIGIN",
    "PORT",
    "DATABASE_PATH",
    "CI_MODE",
    "STRIPE_SANDBOX_WEBHOOK_SECRET",
)
E2E_ENV = (
    "E2E_PORT",
    "E2E_BASE_URL",
    "ROOT_EMAIL",
    "E2E_WEBHOOK_SECRET",
    "STRIPE_SANDBOX_SECRET_KEY",
    "STRIPE_E2E_WEBHOOK_SECRET",
)
KEY_NAMES = (
    "ACCOUNT_ED25519_PRIVATE_KEY",
    "ACCOUNT_ED25519_PUBLIC_KEY",
    "ACCOUNT_X25519_PRIVATE_KEY",
    "ACCOUNT_X25519_PUBLIC_KEY",
    "ACCOUNT_JWT_SECRET",
    "ACCOUNT_SERVER_API_KEY",
)


def busy(port: int, *, after: int = 0) -> list[dict]:
    """`ss` reporting PORT busy, after answering free AFTER times."""
    rows = [row("ss", "-tlnH sport = :%d" % port, times=after)] if after else []
    return [*rows, row("ss", "-tlnH sport = :%d" % port, out=BUSY % port)]


def healthy(port: int = 4800) -> list[dict]:
    return [row("curl", HEALTH % port)]


SEED_STORE = '{"existing":false,"recoveryCode":"RC-1234-5678","totpSecret":"JBSWY3DPEHPK3PXP"}'


def seed_answer(body: str | None, rc: int = 0) -> dict:
    return row("curl", "-sf -X POST " + API % 4800 + "seed-config-store *", rc=rc, out=body)


ALIVE_RUSTFS = row("curl", RUSTFS_PROBE, out="403")
DEV_PORTS = [*busy(4802, after=1), *busy(4801, after=1)]
DEV_JOB = [
    *healthy(),
    seed_answer(SEED_STORE),
    row("hostname", "-I", out="192.168.7.20 10.0.0.9 \n"),
]


def gateway(rc: int = 0) -> dict:
    return row(
        "npx",
        "tsx src/entry/dev-gateway.ts",
        rc=rc,
        sh=WAIT_FOR_JOB + envdump(*GATEWAY_ENV) + STATE_DUMP,
    )


DEV_ENV = {"REDIACC_BWS_PROFILES": "account-dev"}
E2E_ENV_BASE = {"REDIACC_BWS_PROFILES": "account-e2e"}
STRIPE_ENV = {"STRIPE_SANDBOX_SECRET_KEY": "sk_test_shadow", "GATEWAY_PORT": "4800"}


# ------------------------------------------------------------------ fixtures, by name, built identically for both sides


def _write(path: pathlib.Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)
    os.utime(path, (FIXED_MTIME, FIXED_MTIME))


def _touch_dir(path: pathlib.Path, mtime: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.utime(path, (mtime, mtime))


DEFAULTS = (
    "# shadow fixture: the committed dev constants\n"
    "PORT=3000\n"
    "DATABASE_PATH=account.db\n"
    "WEBAUTHN_RP_ID=localhost\n"
    "CI_MODE=true\n"
    "STRIPE_E2E_WEBHOOK_SECRET=whsec_e2e_fixture\n"
)


def fx_base(root: pathlib.Path) -> None:
    """What every case gets: the root manifests, the shared packages, and a `private/account` whose installs are FRESH."""
    _write(root / "package.json", '{"name":"sandbox","scripts":{"build":"x"}}\n')
    _write(root / "package-lock.json", '{"lockfileVersion":3}\n')
    _write(root / ".npmrc", "ignore-scripts=true\n")
    for pkg in ("shared", "provisioning", "cli"):
        _write(root / "packages" / pkg / "src" / "index.ts", "export const %s = 1;\n" % pkg)
        _write(root / "packages" / pkg / "package.json", '{"name":"@rediacc/%s"}\n' % pkg)
    _touch_dir(root / "packages" / "www", FIXED_MTIME)
    account = root / "private" / "account"
    _write(account / "dev.defaults.env", DEFAULTS)
    for sub in (account, account / "web", account / "e2e"):
        _write(sub / "package-lock.json", '{"lockfileVersion":3}\n')
    _touch_dir(account / "web" / "node_modules" / "react-router-dom", FIXED_MTIME + 100)
    for sub in (account, account / "web", account / "e2e"):
        _touch_dir(sub / "node_modules", FIXED_MTIME + 100)


def fx_stale_installs(root: pathlib.Path) -> None:
    """`private/account` never installed, and the web lockfile newer than its `node_modules`."""
    account = root / "private" / "account"
    shutil.rmtree(account / "node_modules")
    os.utime(account / "web" / "package-lock.json", (FIXED_MTIME + 500, FIXED_MTIME + 500))


def fx_no_e2e_modules(root: pathlib.Path) -> None:
    shutil.rmtree(root / "private" / "account" / "e2e" / "node_modules")


def fx_no_defaults(root: pathlib.Path) -> None:
    (root / "private" / "account" / "dev.defaults.env").unlink()


def fx_defaults_dir(root: pathlib.Path) -> None:
    """A defaults PATH that cannot be read: a directory where the file belongs."""
    (root / "private" / "account" / "dev.defaults.env").unlink()
    (root / "private" / "account" / "dev.defaults.env").mkdir()


def fx_defaults_no_webhook(root: pathlib.Path) -> None:
    _write(
        root / "private" / "account" / "dev.defaults.env",
        DEFAULTS.replace("STRIPE_E2E_WEBHOOK_SECRET=whsec_e2e_fixture\n", ""),
    )


def fx_state_port(root: pathlib.Path) -> None:
    _write(root / ".account-state", "gateway_port=4833\npids=4194301\nstarted=1\n")


def fx_state_no_port(root: pathlib.Path) -> None:
    _write(root / ".account-state", "pids=4194301\nstarted=1\n")


def fx_state_equals(root: pathlib.Path) -> None:
    _write(root / ".account-state", "gateway_port=48=33\npids=\n")


def fx_state_twice(root: pathlib.Path) -> None:
    _write(root / ".account-state", "gateway_port=4833\ngateway_port=4834\npids=1\n")


def fx_state_previous(root: pathlib.Path) -> None:
    _write(
        root / ".account-state", "gateway_port=4700\npids=4194301,4194302\nworktree=x\nstarted=1\n"
    )


def fx_db_files(root: pathlib.Path) -> None:
    account = root / "private" / "account"
    for name in ("account.db", "account.db-wal", "account.db-journal"):
        _write(account / name, "sqlite\n")


FIXTURES = {
    name[3:]: fn for name, fn in dict(globals()).items() if name.startswith("fx_") and callable(fn)
}


# ------------------------------------------------------------------ the cases

HEX = [row("openssl", "rand -hex 8", out="%s\n" % (c * 16), times=1) for c in "abc"]

SCENARIOS: dict[str, list[Case]] = {
    "helpers": [
        Case(
            "defaults-shell-wins",
            "load-defaults",
            env={"PORT": "4999"},
            show=(
                "PORT",
                "DATABASE_PATH",
                "CI_MODE",
                "WEBAUTHN_RP_ID",
                "STRIPE_E2E_WEBHOOK_SECRET",
            ),
        ),
        Case("defaults-absent", "load-defaults", setup=("no_defaults",), show=("PORT", "CI_MODE")),
        Case("defaults-unreadable", "load-defaults", setup=("defaults_dir",), show=("PORT",)),
        Case("state-port-absent", "state-gateway-port"),
        Case("state-port-present", "state-gateway-port", setup=("state_port",)),
        Case("state-port-missing", "state-gateway-port", setup=("state_no_port",)),
        Case("state-port-equals", "state-gateway-port", setup=("state_equals",)),
        Case("state-port-twice", "state-gateway-port", setup=("state_twice",)),
        Case("ghost-no-docker", "docker-ghost-clean", unstub=("docker",), hidden=("docker",)),
        Case("ghost-docker-down", "docker-ghost-clean", rows=[row("docker", "info", rc=1)]),
        Case("ghost-none", "docker-ghost-clean"),
        Case(
            "ghost-ids",
            "docker-ghost-clean",
            rows=[row("docker", "ps -aq *", out="c0ffee01\nc0ffee02\n")],
        ),
        Case(
            "ghost-rm-fails",
            "docker-ghost-clean",
            rows=[
                row("docker", "ps -aq *", out="c0ffee01\n"),
                row("docker", "rm -f *", rc=1, err="no such container\n"),
            ],
        ),
        Case("cleanup-exit-code", "cleanup", setup=("state_port",), pre="exit3"),
        Case("cleanup-no-state", "cleanup"),
        Case("cleanup-kills-child", "cleanup", setup=("state_port",), pre="child"),
        # A pid that is NOT the side's own child, which is what `account_dev` really leaves behind: `wait` refuses it at once, so only the `kill` can end it. The case above cannot tell a missing `kill` from a working one, because waiting on its own child outlasts the child.
        Case("cleanup-kills-foreign", "cleanup", setup=("state_port",), pre="foreign"),
        # A job started the way `account_dev` starts Astro and Vite, whose program has a CHILD of its own and dies on SIGTERM without passing it on. Signalling only the tracked pid orphans that child, which is how a dev server came to outlive `account dev` on its port; the process-group kill ends both.
        Case(
            "cleanup-kills-tree",
            "cleanup",
            setup=("state_port",),
            pre="tree",
            rows=[row("npx", "tree-job", sh=TREE_JOB)],
        ),
    ],
    "stripe": [
        Case("no-key", "stripe-auto", env={"GATEWAY_PORT": "4800"}, pids=True),
        Case(
            "no-cli",
            "stripe-auto",
            env=STRIPE_ENV,
            unstub=("stripe",),
            hidden=("stripe",),
            pids=True,
        ),
        Case(
            "happy",
            "stripe-auto",
            env=STRIPE_ENV,
            rows=[
                row(
                    "npx",
                    "tsx scripts/stripe-sync.ts",
                    out="".join("sync %d\n" % i for i in range(7)),
                ),
                row("stripe", "listen *", sh=STRIPE_READY),
                row("sleep", "1", sh=SLEEP_HANDSHAKE),
            ],
            show=("STRIPE_SANDBOX_WEBHOOK_SECRET",),
            pids=True,
        ),
        Case(
            "stale-listeners",
            "stripe-auto",
            env=STRIPE_ENV,
            rows=[
                row("pgrep", "*", out="111\n222\n"),
                row("sleep", "1", times=1),
                row("stripe", "listen *", sh=STRIPE_READY),
                row("sleep", "1", sh=SLEEP_HANDSHAKE),
            ],
            show=("STRIPE_SANDBOX_WEBHOOK_SECRET",),
            pids=True,
        ),
        Case(
            "no-secret",
            "stripe-auto",
            env=STRIPE_ENV,
            rows=[row("stripe", "listen *", out="Getting ready...\n")],
            show=("STRIPE_SANDBOX_WEBHOOK_SECRET",),
            pids=True,
        ),
        Case(
            "sync-fails",
            "stripe-auto",
            env=STRIPE_ENV,
            rows=[row("npx", "tsx scripts/stripe-sync.ts", rc=3, out="a\nb\n", err="sync broke\n")],
            pids=True,
        ),
    ],
    "credentials": [
        Case("never-healthy", "dev-credentials", ["4800"], rows=[row("curl", HEALTH % 4800, rc=7)]),
        Case(
            "healthy-late",
            "dev-credentials",
            ["4800"],
            rows=[row("curl", HEALTH % 4800, rc=7, times=2), *DEV_JOB, *HEX],
        ),
        Case(
            "existing-store",
            "dev-credentials",
            ["4800"],
            rows=[
                *healthy(),
                seed_answer('{"existing":true,"recoveryCode":"","totpSecret":"KRSXG5A"}'),
                row("hostname", "-I", out="\n"),
                *HEX,
            ],
            env={"ROOT_EMAIL": "ops@example.test"},
        ),
        Case(
            "no-store",
            "dev-credentials",
            ["4800"],
            rows=[
                *healthy(),
                seed_answer(None, rc=22),
                row("hostname", "-I", out="10.1.1.1\n"),
                *HEX,
            ],
        ),
        Case(
            "provisioning-fails",
            "dev-credentials",
            ["4800"],
            rows=[*healthy(), row("curl", "*ensure-subscription*", rc=22), *HEX],
        ),
        Case(
            "seed-null",
            "dev-credentials",
            ["4800"],
            rows=[*healthy(), seed_answer("null"), *HEX],
        ),
        Case(
            "seed-not-json",
            "dev-credentials",
            ["4800"],
            rows=[*healthy(), seed_answer("<html>bad gateway</html>"), *HEX],
        ),
        Case(
            "seed-array",
            "dev-credentials",
            ["4800"],
            rows=[*healthy(), seed_answer("[]"), row("hostname", "-I", out="10.2.2.2\n"), *HEX],
        ),
        Case(
            "hostname-fails",
            "dev-credentials",
            ["4800"],
            rows=[*healthy(), seed_answer(SEED_STORE), row("hostname", "-I", rc=64), *HEX],
        ),
        Case(
            "openssl-fails",
            "dev-credentials",
            ["4800"],
            rows=[*healthy(), row("openssl", "*", rc=2, err="openssl: no entropy\n")],
        ),
    ],
    "seed": [
        Case("no-args", "seed-demo"),
        Case("unknown-option", "seed-demo", ["-x"]),
        Case("two-emails", "seed-demo", ["a@example.test", "b@example.test"]),
        Case("port-without-value", "seed-demo", ["a@example.test", "--port"]),
        Case(
            "explicit-port",
            "seed-demo",
            ["a@example.test", "--port", "4900"],
            rows=[row("curl", SEED_URL, out='{"ok":true,"orgs":[1,2]}\n200')],
        ),
        Case(
            "port-equals",
            "seed-demo",
            ["--port=4901", "a@example.test"],
            rows=[row("curl", SEED_URL, out='{"ok":true}\n200')],
        ),
        Case(
            "port-from-state",
            "seed-demo",
            ["a@example.test"],
            setup=("state_port",),
            rows=[row("curl", SEED_URL, out='{"ok":true}\n200')],
        ),
        Case(
            "state-without-port",
            "seed-demo",
            ["a@example.test"],
            setup=("state_no_port",),
        ),
        Case(
            "default-port",
            "seed-demo",
            ["a@example.test"],
            rows=[row("curl", SEED_URL, out='{"ok":true}\n200')],
        ),
        Case(
            "http-500-json",
            "seed-demo",
            ["a@example.test"],
            rows=[row("curl", SEED_URL, out='{"error":"boom"}\n500')],
        ),
        Case(
            "http-502-text",
            "seed-demo",
            ["a@example.test"],
            rows=[row("curl", SEED_URL, out="Bad Gateway\n502")],
        ),
        Case(
            "curl-fails",
            "seed-demo",
            ["a@example.test"],
            rows=[row("curl", SEED_URL, rc=7, err="curl: (7) Failed to connect\n")],
        ),
        Case("no-jq", "seed-demo", ["a@example.test"], hidden=("jq",)),
    ],
    "reset": [
        Case("whole", "reset", setup=("db_files",), python_stub=True),
        Case(
            "push-fails",
            "reset",
            setup=("db_files",),
            python_stub=True,
            rows=[row("python3", "-m rediacc_ci.core.bws_env store-from-env *", rc=1, sh=SIDE)],
        ),
        Case(
            "cache-fails",
            "reset",
            python_stub=True,
            rows=[row("python3", "-m rediacc_ci.core.bws_env cache-to *", rc=2, sh=SIDE)],
        ),
        Case("no-db", "reset", python_stub=True),
        Case("old-node", "reset", python_stub=True, rows=[row("node", "-v", out="v16.20.2\n")]),
        Case(
            "openssl-fails",
            "reset",
            python_stub=True,
            rows=[row("openssl", "rand -base64 48", rc=1, err="openssl: boom\n")],
        ),
    ],
    "test": [
        Case("args", "test", ["--reporter", "dot", "src/a.test.ts"]),
        Case("vitest-fails", "test", rows=[row("npx", "vitest *", rc=4, out="1 failed\n")]),
        Case("no-node", "test", unstub=("node",), hidden=("node",)),
    ],
    "e2e": [
        Case(
            "gateway-env",
            "test-e2e",
            ["--grep", "billing"],
            env={**E2E_ENV_BASE, "GATEWAY_PORT": "4811"},
            rows=[*busy(4811), row("npx", "playwright *", sh=envdump(*E2E_ENV))],
            show=E2E_ENV,
        ),
        Case(
            "server-env",
            "test-e2e",
            env={**E2E_ENV_BASE, "REDIACC_ACCOUNT_SERVER": "http://localhost:4822/account"},
            rows=[*busy(4822), row("npx", "playwright *", sh=envdump(*E2E_ENV))],
            setup=("no_e2e_modules",),
        ),
        Case(
            "state-file",
            "test-e2e",
            env={**E2E_ENV_BASE, "ROOT_EMAIL": "root@example.test"},
            rows=[*busy(4833), row("npx", "playwright *", sh=envdump(*E2E_ENV))],
            setup=("state_port", "defaults_no_webhook"),
        ),
        Case("no-port", "test-e2e", env=E2E_ENV_BASE),
        Case("not-running", "test-e2e", env={**E2E_ENV_BASE, "GATEWAY_PORT": "4844"}),
        Case(
            "sandbox-on",
            "test-e2e",
            env={
                **E2E_ENV_BASE,
                "GATEWAY_PORT": "4855",
                "STRIPE_SANDBOX_SECRET_KEY": "sk_test_shadow",
                "STRIPE_E2E_WEBHOOK_SECRET": "whsec_from_shell",
            },
            rows=[*busy(4855), row("npx", "playwright *", sh=envdump(*E2E_ENV))],
        ),
        Case(
            "install-fails",
            "test-e2e",
            env={**E2E_ENV_BASE, "GATEWAY_PORT": "4811"},
            rows=[
                *busy(4811),
                row("npm", "install --prefer-offline *", rc=5, out="one\ntwo\nthree\n"),
            ],
            setup=("no_e2e_modules",),
        ),
        Case(
            "playwright-fails",
            "test-e2e",
            env={**E2E_ENV_BASE, "GATEWAY_PORT": "4811"},
            rows=[*busy(4811), row("npx", "playwright *", rc=2, err="2 failed\n")],
        ),
    ],
    "dev": [
        Case(
            "reuse-rustfs",
            "dev",
            env=DEV_ENV,
            background=("stripe", "npx"),
            rows=[ALIVE_RUSTFS, *DEV_PORTS, *DEV_JOB, gateway(), *HEX],
        ),
        Case(
            "previous-instance",
            "dev",
            env=DEV_ENV,
            background=("stripe", "npx"),
            setup=("state_previous",),
            rows=[
                row("lsof", "-ti:4700", out="4194303\n"),
                ALIVE_RUSTFS,
                *DEV_PORTS,
                *DEV_JOB,
                gateway(),
                *HEX,
            ],
        ),
        # A state file whose `pids=` names a REAL process the driver owns. Stamped by this writer, `account_dev` ends it (`foreign alive=0 signal=15`); stamped by another host or container, or not stamped, it is refused and the process lives (`foreign alive=1`). The host and the devbox share `.account-state`, which is how a container's pids came to be signalled on the host.
        Case(
            "previous-owned",
            "dev",
            env=DEV_ENV,
            background=("stripe", "npx"),
            pre="state-owned",
            rows=[ALIVE_RUSTFS, *DEV_PORTS, *DEV_JOB, gateway(), *HEX],
        ),
        Case(
            "previous-foreign",
            "dev",
            env=DEV_ENV,
            background=("stripe", "npx"),
            pre="state-foreign",
            rows=[ALIVE_RUSTFS, *DEV_PORTS, *DEV_JOB, gateway(), *HEX],
        ),
        Case(
            "previous-unstamped",
            "dev",
            env=DEV_ENV,
            background=("stripe", "npx"),
            pre="state-unstamped",
            rows=[ALIVE_RUSTFS, *DEV_PORTS, *DEV_JOB, gateway(), *HEX],
        ),
        Case(
            "no-docker-with-stripe",
            "dev",
            env={**DEV_ENV, **STRIPE_ENV, "REDIACC_DEV_BIND": "192.0.2.10"},
            background=("stripe", "npx"),
            unstub=("docker",),
            hidden=("docker",),
            rows=[
                *DEV_PORTS,
                *DEV_JOB,
                gateway(),
                *HEX,
                row("stripe", "listen *", sh=STRIPE_READY),
                row("sleep", "1", sh=SLEEP_HANDSHAKE),
            ],
        ),
        Case(
            "start-rustfs",
            "dev",
            env=DEV_ENV,
            background=("stripe", "npx"),
            rows=[
                row("curl", RUSTFS_PROBE, out="000", rc=7, times=1),
                ALIVE_RUSTFS,
                row("docker", "ps -aq *", out="deadbeef\n"),
                row("docker", "compose up *", out="Container config-rustfs Started\n"),
                *busy(9100),
                *DEV_PORTS,
                *DEV_JOB,
                gateway(),
                *HEX,
            ],
        ),
        Case(
            "rustfs-never",
            "dev",
            env=DEV_ENV,
            background=("stripe", "npx"),
            rows=[
                row("curl", RUSTFS_PROBE, out="000", rc=7),
                row("docker", "compose up *", rc=1, err="ghost container\n"),
                *DEV_PORTS,
                *DEV_JOB,
                gateway(),
                *HEX,
            ],
        ),
        Case(
            "astro-never",
            "dev",
            env=DEV_ENV,
            background=("stripe", "npx"),
            rows=[ALIVE_RUSTFS],
        ),
        Case(
            "pinned-busy",
            "dev",
            env={**DEV_ENV, "REDIACC_DEV_PORT_BASE": "4900"},
            background=("stripe", "npx"),
            rows=[*busy(4901)],
        ),
        Case(
            "stale-installs",
            "dev",
            env=DEV_ENV,
            background=("stripe", "npx"),
            setup=("stale_installs",),
            rows=[ALIVE_RUSTFS, *DEV_PORTS, *DEV_JOB, gateway(), *HEX],
        ),
        Case(
            "gateway-fails",
            "dev",
            env=DEV_ENV,
            background=("stripe", "npx"),
            rows=[ALIVE_RUSTFS, *DEV_PORTS, *DEV_JOB, gateway(rc=3), *HEX],
        ),
        Case(
            "state-missing-key",
            "dev",
            env=DEV_ENV,
            background=("stripe", "npx"),
            setup=("state_no_port",),
        ),
    ],
}


# ------------------------------------------------------------------ the sandbox


def base_dir() -> pathlib.Path:
    return pathlib.Path(tempfile.gettempdir()) / BASE_NAME


def _real(name: str) -> str:
    """The host program a passthrough stub hands off to, resolved on the caller's PATH before any farm exists."""
    found = shutil.which(name)
    if found is None:
        raise SystemExit("account_lifecycle_shadow_driver: %s is not installed" % name)
    return found


def build_sandbox(repo: pathlib.Path, case: Case) -> tuple[pathlib.Path, Farm]:
    base = base_dir()
    if base.exists():
        shutil.rmtree(base)
    root = base / "root"
    (root / ".ci" / "scripts").mkdir(parents=True)
    for rel in (
        ".ci/lib",
        ".ci/config",
        ".ci/rediacc_ci",
        ".ci/scripts/lib",
        ".devcontainer",
        "scripts",
    ):
        (root / rel).symlink_to(repo / rel)
    (root / "home").mkdir()
    fx_base(root)
    for name in case.setup:
        FIXTURES[name](root)

    farm = Farm(base / "farm")
    logged = [n for n in LOGGED if n not in case.unstub and n not in case.background]
    farm.stub(*logged)
    farm.stub(*(n for n in case.background if n not in case.unstub), logged=False)
    farm.stub("date", logged=False)
    if "node" not in case.unstub:
        farm.stub("node", logged=False)
    if case.python_stub:
        farm.stub("python3", logged=False)
    farm.stub_at(root / ".ci" / "scripts" / "setup" / "build-packages.sh")

    def respond(spec: dict) -> None:
        fields = dict(spec)
        name = fields.pop("name")
        glob = fields.pop("glob")
        if name in case.background:
            fields["sh"] = BG + (fields.get("sh") or "")
        farm.respond(name, glob, **fields)

    for spec in case.rows:
        respond(spec)
    defaults = [
        row("docker", "ps -aq *"),
        row("curl", RUSTFS_PROBE, out="000", rc=7),
        # The dev-only provisioning routes answer by default; a case that needs one to fail says so with an earlier row.
        row("curl", "-sf -X POST " + API % 4800 + "*"),
        row("curl", "*", rc=7),
        row("lsof", "*", rc=1),
        row("pgrep", "*", rc=1),
        row("npm", "install", sh=NPM_ROOT_INSTALL),
        row("npm", "install --prefer-offline --no-audit --no-fund", out="added 1 package\n"),
        *HEX,
        row("openssl", "rand -base64 48", out="Ab/cd+Ef=" * 7 + "\n"),
        row("build-packages.sh", "*", sh=BUILD_PACKAGES),
        row("node", "-v", out="v22.23.2\n"),
        row("node", "buildcheck.js", out="{ 'gypi': 1 }\n"),
        row("node", "*", sh='exec "$SHADOW_REAL_NODE" "$@"'),
        row("date", "+%s", out="%d\n" % FROZEN_NOW),
        row("date", "*", sh='exec "$SHADOW_REAL_DATE" "$@"'),
        row(
            "python3",
            "-m rediacc_ci.core.bws_env store-from-env *",
            sh=SIDE + keylens(*KEY_NAMES) + envdump("PYTHONPATH"),
        ),
        row("python3", "-m rediacc_ci.core.bws_env cache-to *", sh=SIDE),
        row("python3", "*", sh='exec "$SHADOW_REAL_PYTHON" "$@"'),
    ]
    for spec in defaults:
        respond(spec)
    for name in case.background:
        respond(row(name, "*"))
    return root, farm


def side_env(root: pathlib.Path, farm: Farm, case: Case) -> dict[str, str]:
    base = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(root / "home"),
        "USER": "sandbox-user",
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
        "CONSOLE_ROOT_DIR": str(root),
        "REDIACC_CI_ROOT": str(root),
        "PYTHONPATH": str(root / ".ci"),
        "SHADOW_REAL_SLEEP": _real("sleep"),
        "SHADOW_REAL_NODE": _real("node"),
        "SHADOW_REAL_DATE": _real("date"),
        "SHADOW_REAL_PYTHON": _real("python3"),
        "SHADOW_SHOW": " ".join(case.show),
        "SHADOW_PIDS": "1" if case.pids else "",
        "SHADOW_PRE": case.pre,
    }
    for key, value in case.env.items():
        if value is None:
            base.pop(key, None)
        else:
            base[key] = value
    return farm.env(base, hidden=case.hidden)


OLD_PROGRAM = r"""
set -euo pipefail
R="$1"; shift
source "$R/.ci/config/constants.sh"
source "$R/.ci/scripts/lib/toolchain.sh"
source "$R/.ci/lib/local-common.sh"
source "$R/.ci/lib/account.sh"
shadow_epilogue() {
    local rc=$? n
    for n in ${SHADOW_SHOW:-}; do
        if [[ -n "${!n+x}" ]]; then printf 'env| %s=%s\n' "$n" "${!n}"; else printf 'env| %s unset\n' "$n"; fi
    done
    if [[ -n "${SHADOW_PIDS:-}" ]]; then printf 'pids| %s\n' "${#ACCOUNT_PIDS[@]}"; fi
    exit "$rc"
}
trap shadow_epilogue EXIT
fn="$1"; shift
case "${SHADOW_PRE:-}" in
    exit3) set +e; (exit 3) ;;
    child) "$SHADOW_REAL_SLEEP" 30 & ACCOUNT_PIDS+=("$!"); printf '%s\n' "$!" >"$STUB_ROOT/child.pid" ;;
    foreign) ACCOUNT_PIDS+=("$SHADOW_FOREIGN_PID") ;;
    tree)
        account_spawn "$CONSOLE_ROOT_DIR" "$STUB_ROOT/tree.log" npx tree-job
        for i in $(seq 200); do [[ -f "$STUB_ROOT/child.pid" ]] && break; "$SHADOW_REAL_SLEEP" 0.05; done
        ;;
esac
"$fn" "$@"
"""


def run_side(
    side: str, root: pathlib.Path, case: Case, env: dict[str, str]
) -> subprocess.CompletedProcess:
    if side == "old":
        argv = ["bash", "-c", OLD_PROGRAM, "account-old", str(root), FN[case.verb], *case.args]
    else:
        argv = [sys.executable, "-m", __spec__.name, "--inner", case.verb, *case.args]
    return subprocess.run(
        argv, cwd=root, env=env, input="", capture_output=True, text=True, check=False, timeout=600
    )


# ------------------------------------------------------------------ the new side, in its own process


def _inner_cleanup(lc, _args: list[str]) -> int:
    pre = os.environ.get("SHADOW_PRE", "")
    code = 3 if pre == "exit3" else 0
    if pre == "child":
        pid = lc.spawn_background([os.environ["SHADOW_REAL_SLEEP"], "30"])
        pathlib.Path(os.environ["STUB_ROOT"], "child.pid").write_text(
            "%d\n" % pid, encoding="utf-8"
        )
    if pre == "foreign":
        lc.PIDS.append(int(os.environ["SHADOW_FOREIGN_PID"]))
    if pre == "tree":
        stub_root = pathlib.Path(os.environ["STUB_ROOT"])
        lc.spawn_background(
            ["npx", "tree-job"],
            cwd=os.environ["CONSOLE_ROOT_DIR"],
            log_path=str(stub_root / "tree.log"),
        )
        for _ in range(200):
            if (stub_root / "child.pid").is_file():
                break
            subprocess.run([os.environ["SHADOW_REAL_SLEEP"], "0.05"], check=False)
    return lc.cleanup(code)


def _inner_state_port(lc, _args: list[str]) -> int:
    status, out = lc.state_gateway_port()
    sys.stdout.write(out)
    return status


INNER = {
    "load-defaults": lambda lc, _: lc.load_defaults(),
    "state-gateway-port": _inner_state_port,
    "cleanup": _inner_cleanup,
    "docker-ghost-clean": lambda lc, _: lc.docker_ghost_clean(),
    "stripe-auto": lambda lc, _: lc.stripe_auto(),
    "dev-credentials": lambda lc, a: lc.dev_credentials(a[0]),
    "seed-demo": lambda lc, a: lc.seed_demo(a),
    "reset": lambda lc, _: lc.reset(),
    "test": lambda lc, a: lc.test(a),
    "test-e2e": lambda lc, a: lc.test_e2e(a),
    "dev": lambda lc, _: lc.dev(),
}


def inner(argv: list[str]) -> int:
    """The port's side of one case: the function, then the same epilogue the bash side's EXIT trap prints."""
    verb, args = argv[0], argv[1:]
    code = 1
    try:
        code = INNER[verb](lifecycle, args)
    except lifecycle.DEATHS as exc:
        code = lifecycle.code_of(exc)
    finally:
        sys.stdout.flush()
        for name in os.environ.get("SHADOW_SHOW", "").split():
            value = os.environ.get(name)
            print("env| %s=%s" % (name, value) if value is not None else "env| %s unset" % name)
        if os.environ.get("SHADOW_PIDS"):
            print("pids| %d" % len(lifecycle.PIDS))
        sys.stdout.flush()
    return code


# ------------------------------------------------------------------ observing


def tree_listing(root: pathlib.Path) -> list[str]:
    """Every path under the sandbox that is not a symlink into the checkout: kind, and a content hash for files."""
    out = []
    for current, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(dirs + files):
            path = pathlib.Path(current) / name
            rel = path.relative_to(root)
            if path.is_symlink():
                out.append("%s link %s" % (rel, os.readlink(path)))
                with contextlib.suppress(ValueError):
                    dirs.remove(name)
            elif path.is_dir():
                out.append("%s dir" % rel)
            else:
                out.append("%s file %s" % (rel, hashlib.sha256(path.read_bytes()).hexdigest()[:16]))
    return out


LINE_STAMP = re.compile(r"^.*?: line \d+: ")
# `scripts/lib/shadow-gate.ts`'s REFUSAL vocabulary matches `CANNOT READ` case-insensitively anywhere in a finding, so the twin's own `env: cannot read env file ...` diagnostic, quoted in an observation, made the gate record the whole row as ERROR_REFUSAL. The phrase is rewritten the same way on BOTH sides, so the message is still compared; this is the same class of accommodation `core/shadow_driver.py` makes for banner whitespace.
GATE_VOCABULARY = (("cannot read", "cannot-read"),)
PID = re.compile(r"\bpid \d+")


def child_alive(farm: Farm) -> str | None:
    """Whether the real process a cleanup case handed over outlived the side, and kill it either way."""
    pid_file = farm.root / "child.pid"
    if not pid_file.is_file():
        return None
    pid = int(pid_file.read_text(encoding="utf-8").strip())
    alive = True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        alive = False
    if alive:
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGKILL)
    return "1" if alive else "0"


# The `pre` values that plant a state file naming a real driver-owned process, and the stamp each writes (None: no `writer=` line at all).
STATE_WRITERS = {
    "state-owned": lifecycle.account.writer_stamp,
    "state-foreign": lambda: "another-host/pid:[4026532999]",
    "state-unstamped": None,
}


def observe(side: str, repo: pathlib.Path, case: Case) -> list[str]:
    """Run one case on one side in the fixed sandbox; return its observation lines."""
    root, farm = build_sandbox(repo, case)

    def norm(text: str) -> str:
        text = text.replace(str(root), "<root>").replace(str(farm.root), "<farm>")
        text = text.replace(str(repo), "<repo>")
        # This machine's writer stamp, which both sides print in a refusal and no other machine shares.
        text = text.replace(lifecycle.account.writer_stamp(), "<self-stamp>")
        for phrase, spelled in GATE_VOCABULARY:
            text = text.replace(phrase, spelled)
        return PID.sub("pid <n>", text)

    foreign = None
    try:
        env = side_env(root, farm, case)
        if case.pre == "foreign":
            foreign = subprocess.Popen([env["SHADOW_REAL_SLEEP"], "30"])
            env["SHADOW_FOREIGN_PID"] = str(foreign.pid)
        if case.pre in STATE_WRITERS:
            foreign = subprocess.Popen([env["SHADOW_REAL_SLEEP"], "30"])
            stamp = STATE_WRITERS[case.pre]
            _write(
                root / ".account-state",
                "gateway_port=4700\npids=%d\n%sstarted=1\n"
                % (foreign.pid, "writer=%s\n" % stamp() if stamp else ""),
            )
        proc = run_side(side, root, case, env)
        tag = case.name
        lines = ["obs %s rc=%d" % (tag, proc.returncode)]
        lines += [
            "obs %s out#%d| %s" % (tag, i, norm(t)) for i, t in enumerate(proc.stdout.splitlines())
        ]
        # bash stamps `<file>: line <N>: ` on its own diagnostics; a port cannot reproduce the twin's line numbers, so the stamp is dropped on both sides and the message compared.
        lines += [
            "obs %s err#%d| %s" % (tag, i, norm(LINE_STAMP.sub("", t)))
            for i, t in enumerate(proc.stderr.splitlines())
        ]
        lines += ["obs %s call#%d| %s" % (tag, i, norm(t)) for i, t in enumerate(farm.transcript())]
        side_log = farm.root / "side.log"
        if side_log.is_file():
            text = side_log.read_text(encoding="utf-8").splitlines()
            lines += ["obs %s side#%d| %s" % (tag, i, norm(t)) for i, t in enumerate(text)]
        bg_log = farm.root / "bg.log"
        if bg_log.is_file():
            lines += [
                "obs %s bg| %s" % (tag, norm(t))
                for t in sorted(bg_log.read_text(encoding="utf-8").splitlines())
            ]
        alive = child_alive(farm)
        if alive is not None:
            lines.append("obs %s child alive=%s" % (tag, alive))
        if foreign is not None:
            try:
                foreign.wait(timeout=5)
                lines.append("obs %s foreign alive=0 signal=%d" % (tag, -foreign.returncode))
            except subprocess.TimeoutExpired:
                lines.append("obs %s foreign alive=1" % tag)
        lines += ["obs %s tree| %s" % (tag, norm(t)) for t in tree_listing(root)]
        return lines
    finally:
        if foreign is not None and foreign.poll() is None:
            foreign.kill()
            foreign.wait()
        shutil.rmtree(base_dir(), ignore_errors=True)


@contextlib.contextmanager
def locked():
    lock = pathlib.Path(tempfile.gettempdir()) / (BASE_NAME + ".lock")
    with open(lock, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def main(argv: list[str]) -> int:
    if argv[:1] == ["--inner"]:
        return inner(argv[1:])
    parser = argparse.ArgumentParser(
        description="one side of the core.account_lifecycle differential"
    )
    parser.add_argument("--side", choices=("old", "new"), required=True)
    parser.add_argument("--twin", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--case", help="run only the named case (for debugging a mismatch)")
    parser.add_argument("scenario", choices=sorted(SCENARIOS))
    args = parser.parse_args(argv)
    repo = pathlib.Path.cwd().resolve()
    for label, rel in (("twin", args.twin), ("port", args.port)):
        if not (repo / rel).is_file():
            sys.stderr.write(
                "account_lifecycle_shadow_driver: the %s %s does not exist under %s, so a row would attest to nothing\n"
                % (label, rel, repo)
            )
            return EXIT_CANNOT_RUN
    with locked():
        for case in SCENARIOS[args.scenario]:
            if args.case and case.name != args.case:
                continue
            for line in observe(args.side, repo, case):
                print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
