"""Port of `.ci/scripts/test/proxies/proxy-license-e2e.sh`.

Local proxy for CI's licensing battery, `.ci/scripts/private/license-e2e.sh` (run in `ct-tests.yml:1848`), which is outside the parity surface. Wired as the registered gate `check:ci-proxy-license-e2e` (`package.json:387`, `scripts/ci-runner/manifest.ts:7435-7444`, `kind: 'local-only'`) -- the bash
proxy is what the gate calls; this port is the parity-verified alternative,
not yet the call site, same as every other file in this package. NO REDUCTION: unlike every other proxy here, this one runs the subject exactly as CI does, with no flag and no subset -- it needs no VM, no btrfs, no LUKS and no docker (the license gate fires before any storage work) and measured 15.8s on
this host. The subject itself stays bash and unported; only this proxy is.

WHAT THIS PROXY ADDS ON TOP OF THE SUBJECT'S OWN EXIT CODE. The subject is a three-run battery: an enforcing binary that must pass every scenario, and two deliberately broken binaries (nolicense, wrong-key) that must FAIL. "exit 0" is therefore a claim about six things, and a battery that silently degraded to running one binary would still exit 0. This proxy reads the summary lines
back and asserts the shape: the enforcing run recorded assertions and zero failures, the nolicense control really failed, and the wrong-key control really failed. A control that does not fire is the failure this exists for -- it would leave the battery unable to detect the exact defect class it was built for, while still exiting 0.

PRIVILEGE. The subject installs license fixtures under `/var/lib/rediacc/license` via `sudo -n`, backing up and restoring any pre-existing `chain-state.json`. That path is a hardcoded constant in renet
with no env override, so passwordless sudo is a hard requirement, not a
convenience, and its absence is cannot-run.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-license-e2e.observations.jsonl`.
"""

from __future__ import annotations

import re
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.core import proxyx

_ENFORCING_PASS_RE = re.compile(r"\[enforcing\].* PASS")
_ENFORCING_FAIL_RE = re.compile(r"\[enforcing\].* FAIL")
_NOLICENSE_FAIL_RE = re.compile(r"\[nolicense\].* FAIL")
_WRONGKEY_FAIL_RE = re.compile(r"\[wrong-key\].* FAIL")


def _count(pattern: re.Pattern[str], text: str) -> int:
    return sum(1 for line in text.splitlines() if pattern.search(line))


def run() -> int:
    root = paths.repo_root()
    subject = str(root / ".ci" / "scripts" / "private" / "license-e2e.sh")

    p = proxyx.Proxy("license-e2e", ".ci/scripts/private/license-e2e.sh")
    p.need_exec(subject, "the subject script is missing from this checkout")
    p.need_cmd("go", "./run.sh setup (the battery builds three renet binaries from source)")
    p.need_cmd("jq", "sudo apt-get install -y jq")
    p.need_file(
        str(root / "private" / "renet" / "go.mod"), "git submodule update --init private/renet"
    )
    # `need_file`, not `need_exec`, matching the twin's `proxy_need_file` (mere `-e` existence): `license-mint` is a Go SOURCE directory built on demand by the subject, not a prebuilt executable sitting on disk.
    #
    # The path is built with the SAME unresolved `../..` the twin's `"$PROXY_DIR/../../private/license-mint"` carries (`:31`), not the clean equivalent -- both sides must print byte-identical missing-requirement text, and pathlib does not collapse `..` on its own the way a `cd` would.
    p.need_file(
        str(
            root / ".ci" / "scripts" / "test" / "proxies" / ".." / ".." / "private" / "license-mint"
        ),
        "the license-mint helper the battery signs with is missing",
    )
    p.need_passwordless_sudo()
    p.preflight()

    # Read separately on purpose, as the twin does: this subject writes every log line to stderr and nothing at all to stdout, so a merged capture would hide that the stdout side is empty by design rather than by breakage.
    proc = subprocess.run([subject], capture_output=True, text=True, check=False)
    rc = proc.returncode
    both = proc.stdout + proc.stderr

    if rc == 0:
        p.ok("license-e2e.sh exited 0")
    else:
        p.bad(f"license-e2e.sh exited {rc}")
        print("  --- subject stderr (last 60) ---", file=sys.stderr)
        print("\n".join(proc.stderr.splitlines()[-60:]), file=sys.stderr)
        print("  --- subject stdout (last 20) ---", file=sys.stderr)
        print("\n".join(proc.stdout.splitlines()[-20:]), file=sys.stderr)

    enforcing_pass = _count(_ENFORCING_PASS_RE, both)
    enforcing_fail = _count(_ENFORCING_FAIL_RE, both)
    nolicense_fail = _count(_NOLICENSE_FAIL_RE, both)
    wrongkey_fail = _count(_WRONGKEY_FAIL_RE, both)

    if enforcing_pass > 0:
        p.ok(
            f"the enforcing binary asserted {enforcing_pass} scenario(s), {enforcing_fail} failure(s)"
        )
    else:
        p.bad(
            "the enforcing run recorded ZERO scenario assertions; the battery ran nothing "
            "and its exit code means nothing"
        )

    if nolicense_fail > 0:
        p.ok(f"the nolicense control FIRED ({nolicense_fail} scenario failures, as required)")
    else:
        p.bad(
            "the nolicense control did NOT fire: a build with -tags nolicense accepted "
            "everything and the battery did not notice, so it cannot detect a stub build"
        )
    if wrongkey_fail > 0:
        p.ok(f"the wrong-key control FIRED ({wrongkey_fail} scenario failures, as required)")
    else:
        p.bad(
            "the wrong-key control did NOT fire: a binary baked with a stranger's public "
            "key still validated licences, so the battery cannot detect a wrongly-baked key"
        )

    p.expect_contains(
        both,
        "both controls failed as required",
        "the subject printed its own both-controls verdict",
    )

    return p.finish()


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--selftest":
        return proxyx.run_selftest()
    return run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
