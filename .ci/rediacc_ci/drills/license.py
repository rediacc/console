"""Port of `scripts/drills/license.sh` (1071 lines): the live licensing battery, on real machines.

    PYTHONPATH=.ci python3 -m rediacc_ci.drills.license [--legs a,b,c,d,e,f] [--selftest] [--no-restart] [--vm <ip>] [--vm2 <ip>] [--ssh-user <u>] [--ssh-key <p>] [--keep-work]

THIS ONE COSTS REAL RESOURCES, so it says so before it does anything and refuses to start when the machines are not already there. It never provisions them: bringing up VMs is minutes of the operator's hardware.

LEGS, one licensing claim each. a: a DATASTORE FORK RE-METERS (the fork's datastoreId is re-minted, so the repo inside reads `missing`, a reissue claims a fresh slot, and the parent's licence is untouched). b: a PLAIN MIGRATION DOES NOT (`datastore attach --to` carries the descriptor, and so the identity, along; `repo migrate` moves the repo out of its datastore and legitimately re-meters). c: RENEWAL FROM A CREDENTIAL-LESS MACHINE (the installed blob carries its own renewalUrl and its signature is the credential). d: RENEWAL REFUSAL ON A LAPSED SUBSCRIPTION, with the code surfaced. e: SOFT CLAIM OVER CAP (past maxActivations renewal still succeeds and the overage is visible; only new issuance blocks). f: THE DTO BOUNDARY (chainHash, and on a delegated deployment delegationCert, survive the HTTP response, with a planted-strip control).

COST. Legs b through e need the basic cluster (b needs the second worker, so the cluster is `ops up` without the Ceph trio at least); leg a needs Ceph (the full cluster); leg f needs no machine. The preflight reports which legs the machines present can support and refuses the rest by name.

REUSE. The VM-less form of leg a is `.ci/scripts/private/license-e2e.sh` scenarios S8a-S8e: the cheap control. If a leg fails here and its S8 twin passes there, the difference is the machine, not the licence logic.

SELFTEST. `--selftest` plants one assertion that cannot pass and stops before any VM work.

RULE T: WHERE THIS DELIBERATELY DIFFERS FROM THE BASH (each pinned by a test in `tests/test_drills_backup_license.py`).

  1. THE GATEWAY DOES NOT INHERIT THE SANDBOX. The bash exported `XDG_CONFIG_HOME`, `REDIACC_CONFIG`, `RDC_RENET_LICENSE` and the rest into its own environment before it restarted the gateway, so the gateway's secret loader looked for the Bitwarden token under the throwaway config home (see `rediacc_ci.drills.lib`). They reach only the `rdc` commands under test here.
  2. NO `curl`, `node` AND `uuidgen`. HTTP is `urllib`, JSON expressions are Python, ids are `secrets`/`uuid`; the preflight no longer demands the three tools.
  3. THE MAX SEQUENCE OF AN EMPTY RESULT LIST IS 0. `Math.max(...[])` is `-Infinity`, which the bash then compared against 0 and accepted as a fresh sequence; `renewed_sequence` answers 0 and the assertion fails, as it should.
  4. A FAILED RESTORE OF THE SUBSCRIPTION IS REPORTED. The bash teardown discarded both the output and the exit code of the patch that puts the cap and the status back (`>/dev/null 2>&1 || true`), so a drill that left the subscription suspended said nothing; the failure is a warning naming what was left behind.
  5. A TRANSPORT FAILURE ENDS THE DRILL WITH ITS CAUSE (`OSError` naming the method and URL) where a failed `curl` in a pipeline stage was swallowed and read as an empty field.
"""

from __future__ import annotations

import base64
import contextlib
import getpass
import http.cookiejar
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from typing import TYPE_CHECKING

from rediacc_ci import log
from rediacc_ci.drills import lib, wire

if TYPE_CHECKING:
    import pathlib

KNOWN_LEGS = ["a", "b", "c", "d", "e", "f"]
USAGE = (
    "Usage: ./run.sh drill license [--legs a,b,c,d,e,f] [--selftest] "
    "[--no-restart] [--vm <ip>] [--vm2 <ip>] [--ssh-user <u>] [--ssh-key <p>]"
)
DRILL_PASSWORD = "DrillLicense123!"  # noqa: S105 -- a throwaway dev-gateway login
# The activation cap this drill starts from, seeded explicitly rather than inherited from the dev server's default, so leg e asserts against a number this file owns and teardown restores that same number.
START_MAX_ACTIVATIONS = 3
CONFIG_NAME = "drill-license"
MACHINE_NAME = "drill-lic-1"
MACHINE2_NAME = "drill-lic-2"
DATASTORE_NAME = "drill-ds"
FORK_TAG = "remeter"
REPO_NAME = "drill-repo"


class Options:
    def __init__(self) -> None:
        self.restart_gateway = True
        self.legs = "a,b,c,d,e,f"
        self.net_base = os.environ.get("VM_NET_BASE") or "192.168.111"
        self.vm_ip = self.net_base + ".11"
        self.vm2_ip = self.net_base + ".12"
        self.ssh_user = os.environ.get("SSH_USER") or os.environ.get("USER") or getpass.getuser()
        # The ops VMs authorize the key `renet ops` itself provisions them with: id_rsa under the renet staging folder (rooted at RENET_DATA_DIR or ~/.renet), NOT ~/.ssh/id_ed25519. A plain `ssh` still connects with the wrong -i because OpenSSH falls through to its default identities, while the CLI (ssh2, one explicit key) fails with "All configured authentication methods failed".
        renet_data = os.environ.get("RENET_DATA_DIR") or os.path.join(
            os.environ.get("HOME", "~"), ".renet"
        )
        self.ssh_key = os.environ.get("SSH_KEY") or os.path.join(
            renet_data, "staging", ".ssh", "id_rsa"
        )
        # `renet` (in PATH) is the CLI's own default for a provisioned machine.
        self.vm_renet = os.environ.get("DRILL_RENET_PATH") or "renet"

    def enabled(self, leg: str) -> bool:
        return leg in self.legs.split(",")

    def needs_vm(self) -> bool:
        """True when any selected leg touches a machine. Leg f is the only one that does not, so `--legs f` skips every VM-shaped precondition."""
        return any(self.enabled(leg) for leg in "abcde")


def parse_args(argv: list[str], opts: Options) -> int | None:
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--no-restart":
            opts.restart_gateway = False
        elif arg in ("--legs", "--vm", "--vm2", "--ssh-user", "--ssh-key"):
            i += 1
            value = argv[i] if i < len(argv) else ""
            if arg == "--legs":
                opts.legs = value
            elif arg == "--vm":
                opts.vm_ip = value
            elif arg == "--vm2":
                opts.vm2_ip = value
            elif arg == "--ssh-user":
                opts.ssh_user = value
            else:
                opts.ssh_key = value
        else:
            log.error("Unknown option: %s" % arg)
            print(USAGE, file=sys.stderr)
            return 2
        i += 1
    return None


def running_ips(status_json: str) -> list[str]:
    """The `ip` of every VM whose status is `running`. `rdc ops status -o json` wraps the renet payload in the CLI envelope (the array is at `data.vms`); the bare shape is accepted too. `ops status` lists every CONFIGURED VM including absent ones, so the gate is on each entry's status, never on the array's length."""
    parsed = wire.parse(status_json)
    vms = wire.lookup(parsed, "data.vms")
    if not isinstance(vms, list):
        vms = wire.lookup(parsed, "vms")
    if not isinstance(vms, list):
        return []
    return [str(v.get("ip")) for v in vms if isinstance(v, dict) and v.get("status") == "running"]


def renewed_sequence(results: object) -> int:
    """The highest `newSequence` among renewal results, 0 for none (Rule T 3)."""
    if not isinstance(results, list):
        return 0
    return max([int(r.get("newSequence") or 0) for r in results if isinstance(r, dict)] or [0])


def _result_any(results: object, key: str, value: str) -> bool:
    return isinstance(results, list) and any(
        isinstance(r, dict) and r.get(key) == value for r in results
    )


def _result_none(results: object, key: str, value: str) -> bool:
    return isinstance(results, list) and all(
        isinstance(r, dict) and r.get(key) != value for r in results
    )


PRECLEAN_QUIET = "is not registered on this machine"
"""The one renet error the pre-clean expects: the datastore is not on this machine (a fresh VM, or a previous run that cleaned up after itself). Every other failure is reported."""


def preclean_script(renet: str) -> str:
    """The machine-side pre-clean of leg a. The installed licence store is machine-local and SURVIVES every datastore this drill deletes, so a machine that has run the drill before holds blobs for repos and datastores that no longer exist; legs c-e are only deterministic on a machine whose licences all belong to THIS run. Mounted repos inside a drill datastore are unmounted first (a datastore with a mounted repo refuses to detach), the fork is discarded with `detach --discard` before the parent, and the parent is detached (when attached) and deleted.

    SILENT ONLY ON THE EXPECTED. Every step used to end in `>/dev/null 2>&1`, so after a VM crash left drill-ds registered but held detached, the parent's delete failed for a reason nobody saw and the NEXT step, `datastore create`, failed with "already exists". Now a step that fails with anything but `PRECLEAN_QUIET` prints `PRECLEAN FAILED: <command> (rc=N)` and the tail of its output on stderr, and the script exits 1; the caller reports it before the create it would otherwise break."""
    return (
        "fail=0\n"
        "report() {\n"
        '    printf \'PRECLEAN FAILED: %%s (rc=%%s)\\n\' "$1" "$2" >&2\n'
        "    printf '%%s\\n' \"$3\" | grep -v '^[[:space:]]*$' | tail -n 3 | sed 's/^/    /' >&2\n"
        "    fail=1\n"
        "}\n"
        "step() {\n"
        '    out=$("$@" 2>&1) && return 0\n'
        "    rc=$?\n"
        "    case \"$out\" in *'%(quiet)s'*) return 0 ;; esac\n"
        '    report "$*" "$rc" "$out"\n'
        "}\n"
        "step sudo rm -rf /var/lib/rediacc/license/repos \\\n"
        "    /var/lib/rediacc/license/datastores \\\n"
        "    /var/lib/rediacc/license/failed \\\n"
        "    /var/lib/rediacc/license/renew-state.json \\\n"
        "    /var/lib/rediacc/license/chain-state.json\n"
        "errf=$(mktemp)\n"
        "trap 'rm -f \"$errf\"' EXIT\n"
        'list=$(sudo %(renet)s datastore list --json 2>"$errf") || { report \'datastore list --json\' "$?" "$(cat "$errf")"; exit 1; }\n'
        "for ds in %(ds)s:%(tag)s %(ds)s; do\n"
        "    row=$(printf '%%s' \"$list\" | python3 -c \"import json,sys; d=next((d for d in json.load(sys.stdin) if d.get('name')=='$ds'),None); print('' if d is None else d.get('state','?')+' '+d.get('mountPath',''))\" 2>&1) || { report \"read $ds from the datastore list\" \"$?\" \"$row\"; continue; }\n"
        '    [ -n "$row" ] || continue\n'
        '    read -r state mount <<< "$row"\n'
        '    if [ "$state" = attached ]; then\n'
        '        listing=$(sudo %(renet)s repository list --datastore "$mount" --json 2>"$errf") || { report "repository list --datastore $mount" "$?" "$(cat "$errf")"; listing=\'[]\'; }\n'
        "        repos=$(printf '%%s' \"$listing\" | python3 -c \"import json,sys; [print(r['name'], r.get('network_id',0)) for r in json.load(sys.stdin) if r.get('mounted')]\" 2>&1) || { report \"read the mounted repos in $mount\" \"$?\" \"$repos\"; repos=''; }\n"
        "        while read -r guid nid; do\n"
        '            [ -n "$guid" ] || continue\n'
        '            step sudo %(renet)s repository unmount --name "$guid" --network-id "$nid" --datastore "$mount" --stop-docker --force\n'
        '        done <<< "$repos"\n'
        "    fi\n"
        '    if [ "$ds" != "${ds%%:*}" ]; then\n'
        '        step sudo %(renet)s datastore detach --name "$ds" --discard\n'
        "        continue\n"
        "    fi\n"
        '    [ "$state" = attached ] && step sudo %(renet)s datastore detach --name "$ds"\n'
        '    step sudo %(renet)s datastore delete --name "$ds"\n'
        "done\n"
        "exit $fail\n"
        % {"ds": DATASTORE_NAME, "tag": FORK_TAG, "renet": renet, "quiet": PRECLEAN_QUIET}
    )


class License:
    def __init__(self, drill: lib.Drill, opts: Options) -> None:
        self.d = drill
        self.o = opts
        self.rdc = str(drill.root / "rdc.sh")
        self.email = "drill-license-%d@rediacc.io" % int(time.time())
        self.server_url = ""
        self.api_token = ""
        self.subscription_id = ""
        self.jar: http.cookiejar.CookieJar | None = None
        self.admin_jar: http.cookiejar.CookieJar | None = None
        self.ceph_available = False
        self.subscription_lapsed = False
        self.cap_lowered = False

    @property
    def work(self) -> pathlib.Path:
        assert self.d.work is not None  # noqa: S101
        return self.d.work

    # ------------------------------------------------------------------ plumbing

    def ssh_argv(self, host: str, command: str) -> list[str]:
        """`ssh` with EXACTLY one identity. -F /dev/null, IdentitiesOnly and IdentityAgent=none are load-bearing: without them OpenSSH quietly tries the agent, ~/.ssh/config and its default identities after the -i key is refused, so the drill's own SSH could connect with a different key than the one it handed the CLI. That divergence is what made the first live run so confusing."""
        return [
            "ssh",
            "-F",
            "/dev/null",
            "-i",
            self.o.ssh_key,
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "IdentityAgent=none",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "LogLevel=ERROR",
            "%s@%s" % (self.o.ssh_user, host),
            command,
        ]

    def ssh_out(self, host: str, command: str, stdin: str | None = None) -> tuple[int, str]:
        """(exit code, stdout) of a remote command, stderr discarded (the bash `2>/dev/null` before a pipe)."""
        proc = subprocess.run(
            self.ssh_argv(host, command),
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout

    def ssh_run(self, host: str, command: str) -> None:
        self.d.run(self.ssh_argv(host, command))

    def cli(self, *args: str) -> None:
        self.d.setup_run([self.rdc, *args])

    def api_base(self) -> str:
        return self.d.api_base()

    def bearer(self) -> dict[str, str]:
        return {"Authorization": "Bearer %s" % self.api_token}

    def capture(self, description: str, body: str) -> None:
        """Stage a captured HTTP body as if `run` had produced it, so the JSON assertions and the failure dump work unchanged."""
        self.d.last_cmd = description
        if self.d.stdout_file is None or self.d.stderr_file is None:
            raise RuntimeError("Drill.init() must run first")
        self.d.stdout_file.write_text(body)
        self.d.stderr_file.write_text("")
        self.d.code = 0

    def aj(self, path: str, expected: object, desc: str) -> None:
        self.d.assert_equal(wire.jstr(expected), lib.json_get(self.d.stdout_text(), path), desc)

    def av(self, value: object, expected: object, desc: str) -> None:
        self.d.assert_equal(wire.jstr(expected), wire.jstr(value), desc)

    def stdout_field(self, path: str) -> object:
        return wire.lookup(wire.parse(self.d.stdout_text()), path)

    def patch_subscription(self, patch: dict) -> str:
        assert self.admin_jar is not None  # noqa: S101
        return self.d.account_patch_subscription(self.admin_jar, self.subscription_id, patch)

    # ------------------------------------------------------------------ cost and preflight

    def announce_cost(self) -> None:
        base = self.o.net_base
        self.d.out.write(
            "\n  This drill runs against the ops VM cluster. It does NOT provision anything.\n\n"
            "    legs b,c,d,e   need the BASIC cluster   ./rdc.sh ops up --basic\n"
            "                   2 VMs: %(b)s.1 (bridge) + %(b)s.11 (worker)\n"
            "                   about 4 GB RAM and 16 GB disk each\n\n"
            "    leg  a         needs the FULL cluster   ./rdc.sh ops up\n"
            "                   6 VMs including the three Ceph nodes %(b)s.21/.22/.23\n"
            "                   about 24 GB RAM and ~190 GB disk in total\n"
            "                   (a datastore fork is RBD-only; a local-backend fork is\n"
            "                    refused outright, so leg a cannot run without Ceph)\n\n"
            "    leg  f         needs no VM at all: it is an HTTP-boundary assertion\n\n"
            "  VMs persist across sessions and are torn down only by ./rdc.sh ops down.\n"
            "  Selected legs: %(legs)s\n\n" % {"b": base, "legs": self.o.legs}
        )
        self.d.out.flush()

    def preflight_tools(self) -> None:
        d, o = self.d, self.o
        d.step("Preflight: tools")
        ok = True
        if not shutil.which("ssh"):
            log.error("Missing required tool: ssh (openssh-client)")
            ok = False
        if o.needs_vm() and not os.path.isfile(o.ssh_key):
            log.error("SSH key not found at %s (override with --ssh-key)" % o.ssh_key)
            ok = False
        if not ok:
            raise SystemExit(1)
        d.note("ssh user=%s key=%s" % (o.ssh_user, o.ssh_key))

    def preflight_ssh(self) -> None:
        """Prove THIS key authenticates to the machine, before any setup step depends on it: the CLI's failure here is a single unhelpful line emitted from deep inside `machine setup`."""
        d, o = self.d, self.o
        if not o.needs_vm():
            return
        d.step("Preflight: the SSH key actually authenticates")
        code, _ = self.ssh_out(o.vm_ip, "true")
        if code == 0:
            d.note(
                "authenticated to %s as %s with %s"
                % (o.vm_ip, o.ssh_user, os.path.basename(o.ssh_key))
            )
            return
        log.error("Cannot authenticate to %s as %s using %s." % (o.vm_ip, o.ssh_user, o.ssh_key))
        log.error("This is the key 'renet ops' provisions the VMs with; if you rebuilt them")
        log.error("with a different one, pass it:  ./run.sh drill license --ssh-key <path>")
        log.error(
            "A plain 'ssh' may still succeed here while this fails, because OpenSSH falls back"
        )
        log.error("to your other default identities, and the CLI does not.")
        raise SystemExit(1)

    def agent_override_blocked_message(self, missing: list[str]) -> None:
        log.error("This drill's selected legs are blocked in agent mode. Missing override(s):")
        for item in missing:
            log.error("    %s" % item)
        log.error("")
        log.error("These verbs provision and tear down real infrastructure, so an agent cannot")
        log.error("authorize them itself, and an override exported from inside the session is")
        log.error("rejected on purpose.")
        log.error("")
        log.error("  To run them:  export the variable(s) in YOUR terminal BEFORE starting the")
        log.error("                agent session, or run this drill directly as the operator.")
        log.error("  To skip them: ./run.sh drill license --legs c,d,e,f   (needs a licensed")
        log.error("                repo already on the machine), or --legs f (no VM at all).")

    def preflight_agent_overrides(self) -> None:
        """Both guards (REDIACC_ALLOW_CLUSTER_OPS for datastore verbs, REDIACC_ALLOW_GRAND_REPO for grand-repo verbs) are ancestry-verified: the OPERATOR exports them before the agent session starts. Both missing vars are reported at once, because discovering them one failed run at a time is two wasted cluster runs."""
        d, o = self.d, self.o
        d.step("Preflight: agent-mode authorization")
        if not _agent_session():
            d.note("not an agent session: these guards do not apply")
            return
        missing: list[str] = []
        if o.enabled("a") or o.enabled("b"):
            if not os.environ.get("REDIACC_ALLOW_CLUSTER_OPS"):
                missing.append(
                    "REDIACC_ALLOW_CLUSTER_OPS=*  (leg a: datastore create/fork, leg b: datastore attach)"
                )
            if not os.environ.get("REDIACC_ALLOW_GRAND_REPO"):
                missing.append(
                    "REDIACC_ALLOW_GRAND_REPO=*   (leg a: repo create, leg b: repo down)"
                )
        if not missing:
            d.note(
                "required overrides are present (the CLI still verifies they predate this session)"
            )
            return
        self.agent_override_blocked_message(missing)
        raise SystemExit(1)

    def ensure_repo_present(self) -> None:
        """Legs b-e operate on the licensed repository leg a creates. Selecting them without leg a is legitimate (the repo may survive from an earlier run), but it must be CHECKED."""
        o = self.o
        if o.enabled("a"):
            return
        guid = self.repo_status(o.vm_ip, "repositoryGuid")
        if guid:
            self.d.note("reusing the licensed repo already on %s (%s)" % (o.vm_ip, guid))
            return
        log.error("Legs b-e operate on a licensed repository, and %s has none." % o.vm_ip)
        log.error("Leg a is what creates it, so there is nothing here to migrate, renew or meter.")
        log.error("Run leg a in the same invocation:  ./run.sh drill license --legs a,%s" % o.legs)
        raise SystemExit(1)

    def preflight_vms(self) -> None:
        """Which cluster is actually up, and therefore which legs can run."""
        d, o = self.d, self.o
        d.step("Preflight: ops VM availability")
        proc = subprocess.run(
            [self.rdc, "ops", "status", "-o", "json"],
            capture_output=True,
            text=True,
            env=d.cli_env(),
            check=False,
        )
        if proc.returncode != 0:
            log.error("Could not read ops status. Is renet built and libvirt reachable?")
            raise SystemExit(1)
        running = running_ips(proc.stdout)
        d.note("running VMs: %s" % (" ".join(running) or "<none>"))
        if o.needs_vm() and o.vm_ip not in running:
            log.error("Worker VM %s is not running, and legs a-e need it." % o.vm_ip)
            log.error("Provision it first:  ./rdc.sh ops up --basic")
            log.error("Or run only the VM-less leg:  ./run.sh drill license --legs f")
            raise SystemExit(1)
        if o.enabled("b") and o.vm2_ip not in running:
            log.error(
                "Leg b (migration) needs a SECOND machine at %s, which is not running." % o.vm2_ip
            )
            log.error("Provision the full cluster:  ./rdc.sh ops up")
            raise SystemExit(1)
        self.ceph_available = ("%s.21" % o.net_base) in running
        if o.enabled("a") and not self.ceph_available:
            log.error(
                "Leg a (datastore fork re-meters) needs Ceph, and %s.21 is not running."
                % o.net_base
            )
            log.error(
                "A local-backend datastore fork is refused by design, so this leg cannot be faked."
            )
            log.error("Provision the full cluster:  ./rdc.sh ops up")
            log.error("Or drop the leg:            ./run.sh drill license --legs b,c,d,e,f")
            raise SystemExit(1)
        d.note("ceph available: %s" % ("yes" if self.ceph_available else "no"))

    # ------------------------------------------------------------------ setup

    def setup_sandbox(self) -> None:
        d = self.d
        d.step("Setup: isolated config directory")
        home = self.work / "xdg"
        (home / "rediacc").mkdir(parents=True, exist_ok=True)
        d.extra_env["XDG_CONFIG_HOME"] = str(home)
        d.extra_env["REDIACC_CONFIG"] = CONFIG_NAME
        # This drill is ABOUT enforcement, so the renet it deploys must be the license-enforcing flavor with the dev account key baked in: the default dev build is nolicense (a permit-all stub that would make every leg vacuous). The build stamp hashes the effective mode, so this forces a rebuild here and the next plain ./rdc.sh rebuilds nolicense right back.
        d.extra_env["RDC_RENET_LICENSE"] = "1"
        # See the universe drill: unpinned, a drill measures the json surface while describing the human one.
        d.extra_env["REDIACC_DEFAULT_OUTPUT"] = "table"

    def setup_gateway_address(self) -> None:
        """Advertise the gateway at an address the MACHINES can reach, not just this workstation: a license blob's renewalUrl is stamped from the Host header of the request that issued it, so issuing over 127.0.0.1 hands every machine a URL pointing at itself and `renet license renew` on the VM fails with connection refused. The workstation's own address on the VM network is reachable from BOTH sides, and an API token binds to the first host it is used with. Leg f alone needs no VM, so it keeps the loopback default."""
        d, o = self.d, self.o
        if not o.needs_vm():
            return
        host = wire.bridge_host(o.net_base)
        if not host:
            log.error("No interface on the %s.0/24 VM network, so no address the" % o.net_base)
            log.error("machines could reach this gateway at. The ops bridge (renet<N>) is created")
            log.error("by ./rdc.sh ops up; without it leg c cannot be honest about renewal.")
            raise SystemExit(1)
        d.host = host
        d.note("gateway advertised at %s (reachable from the VMs and from here)" % d.host)

    def setup_gateway(self) -> None:
        d = self.d
        if self.o.restart_gateway:
            d.restart_gateway()
        else:
            d.step("Reusing the running dev gateway (--no-restart)")
            if not d.gateway_alive():
                log.error("No healthy dev gateway. Start one: ./run.sh account dev")
                raise SystemExit(1)
            d.gateway_port_cached = d.gateway_port()
        self.server_url = d.server_url()
        d.note("account server: %s" % self.server_url)

    def setup_account(self) -> None:
        d = self.d
        d.step("Setup: dev subscription and API token")
        d.account_ensure_login(self.email, DRILL_PASSWORD)
        d.account_ensure_subscription(self.email, "PROFESSIONAL", START_MAX_ACTIVATIONS)
        self.jar = http.cookiejar.MozillaCookieJar(str(self.work / "cookies.txt"))
        if not d.account_session(self.email, DRILL_PASSWORD, self.jar):
            raise SystemExit(1)
        self.subscription_id = d.account_subscription_id(self.jar)
        self.api_token = d.account_mint_token(
            self.jar,
            self.subscription_id,
            "drill-license",
            ["license:read", "license:activate", "subscription:read"],
        )
        d.note("subscription %s" % self.subscription_id)
        # A separate root+elevated session for the admin edits legs d and e need.
        self.admin_jar = http.cookiejar.MozillaCookieJar(str(self.work / "admin-cookies.txt"))
        if not d.account_admin_session(self.email, DRILL_PASSWORD, self.admin_jar):
            raise SystemExit(1)

    def verify_renet_flavor(self) -> None:
        """Prove the flavor BEFORE deploying it. A wrong-flavored renet fails every leg with an error that reads like a licensing bug: an enforcing keyless build refuses everything with "public key not configured", a nolicense build permits everything. The buildinfo of an enforcing build carries no `-tags=nolicense` and DOES carry the baked dev key in ldflags."""
        d = self.d
        d.step("Setup: the local renet build enforces licenses with the dev key")
        binary = d.root / "private" / "renet" / "bin" / "renet"
        try:
            info = subprocess.run(
                ["go", "version", "-m", str(binary)], capture_output=True, text=True, check=False
            ).stdout
        except OSError:
            info = ""
        if not info:
            log.error("Cannot read build info from %s (missing or not a Go binary)." % binary)
            raise SystemExit(1)
        if "tags=nolicense" in info:
            log.error("The renet at %s is a NOLICENSE build: every licensing" % binary)
            log.error("assertion would be vacuous. RDC_RENET_LICENSE=1 should have")
            log.error("forced an enforcing rebuild; check the build stamp logic.")
            raise SystemExit(1)
        if "ProductionPublicKey=" not in info:
            log.error("The renet at %s has NO account public key baked in: every" % binary)
            log.error("validation fails as 'public key not configured'. This is the")
            log.error("signature of a foreign 'go build' overwriting bin/renet.")
            log.error("Rebuild: RDC_RENET_LICENSE=1 (cd private/renet && ./build.sh dev)")
            raise SystemExit(1)
        d.note("enforcing build with baked key confirmed")

    def setup_config(self) -> None:
        d, o = self.d, self.o
        d.step("Setup: config, machines and subscription login")
        self.cli("config", "init", CONFIG_NAME, "--server", self.server_url)
        # config init above was the first CLI invocation, so the renet (re)build has happened by now; prove its flavor before machine setup deploys it.
        self.verify_renet_flavor()
        # Sync the target server's E2E public key before anything tunnels; without this the first tunnelled call dies as "Decryption failed".
        self.cli("config", "current", "-o", "json")
        self.cli("config", "ssh", "set", "--key", o.ssh_key)
        self.cli("subscription", "login", "--token", self.api_token, "--server", self.server_url)
        # `rdc machine add` also writes an SSH alias into the user's real home (on WSL, into the WINDOWS home), which no sandbox here can contain: reported, unavoidable for a drill that must drive a registered machine.
        self.cli("machine", "add", MACHINE_NAME, "--ip", o.vm_ip, "--user", o.ssh_user)
        if o.enabled("b"):
            self.cli("machine", "add", MACHINE2_NAME, "--ip", o.vm2_ip, "--user", o.ssh_user)
        # Setup steps, not assertions: as assertions they produced a cascade (the provisioning failure reported once, then the renet-on-PATH check failing too with empty streams). `setup_run` aborts on the FIRST failure with both streams printed.
        self.cli("machine", "setup", MACHINE_NAME)
        d.setup_run(self.ssh_argv(o.vm_ip, "command -v %s" % o.vm_renet))
        d.note("renet provisioned on %s" % o.vm_ip)

    def teardown_hook(self) -> None:
        """Restore anything the drill changed on the SUBSCRIPTION, because those edits outlive the work directory: a suspended subscription or a cap of 1 left behind makes the next run fail for a reason that has nothing to do with what it tests. The VMs are deliberately NOT torn down: they are the operator's."""
        if self.admin_jar is None or not self.subscription_id:
            return
        if self.subscription_lapsed or self.cap_lowered:
            try:
                self.patch_subscription(
                    {"status": "active", "maxActivations": START_MAX_ACTIVATIONS}
                )
            except OSError as exc:
                log.warn(
                    "teardown: restoring the subscription (status=active, maxActivations=%d) failed: %s"
                    % (START_MAX_ACTIVATIONS, exc)
                )

    # ------------------------------------------------------------------ shared probes

    def repo_status(self, host: str, field: str) -> str:
        """One field of the repo's licence status, read the way license-e2e.sh's assert_status reads it: the JSON array from `repository license-status`, first entry that has a repositoryGuid, stdout only."""
        _, out = self.ssh_out(
            host,
            "sudo %s repository license-status --all-datastores --output json" % self.o.vm_renet,
        )
        parsed = wire.parse(out)
        if not isinstance(parsed, list):
            return ""
        entry = next((e for e in parsed if isinstance(e, dict) and e.get("repositoryGuid")), {})
        return wire.jstr(entry.get(field, wire.MISSING))

    def meter_snapshot(self) -> str:
        """The subscription-side counters, as one line, so a leg can assert on the DELTA rather than on an absolute nobody can predict."""
        _, text = wire.http_call("GET", "%s/portal/subscription" % self.api_base(), jar=self.jar)
        parsed = wire.parse(text)
        used = wire.lookup(parsed, "repoLicenseIssuances.effectiveUsed")
        activations = wire.lookup(parsed, "activations")
        return "%s:%s" % (_js_text(used), _js_text(activations))

    def license_status(self) -> str:
        return wire.http_call("GET", "%s/licenses/status" % self.api_base(), headers=self.bearer())[
            1
        ]

    def activate_repo_for(self, machine_id: str) -> str:
        """Issue a repo licence for a machine over raw HTTP and return the whole response."""
        body = {
            "machineId": machine_id,
            "clientMachineId": machine_id,
            "repositoryGuid": str(uuid.uuid4()),
            "kind": "grand",
            "requestedSizeGb": 1,
        }
        return wire.http_call(
            "POST", "%s/licenses/activate-repo" % self.api_base(), wire.compact(body), self.bearer()
        )[1]

    def renew_blob_for(self, machine_id: str, activated: str) -> str:
        """Present an installed blob back to /licenses/renew as that machine would: the credential-less path leg c drives through renet, reached here over HTTP because the machine in question is synthetic."""
        license_blob = wire.lookup(wire.parse(activated), "license")
        body = wire.compact(
            {
                "license": None if license_blob is wire.MISSING else license_blob,
                "machineId": machine_id,
            }
        )
        return wire.http_call("POST", "%s/licenses/renew" % self.api_base(), body)[1]

    # ------------------------------------------------------------------ leg a

    def claimed_machine_ids(self) -> list[str]:
        """The machine ids this drill's subscription has an activation row for."""
        parsed = wire.parse(self.license_status())
        machines = wire.lookup(parsed, "machines")
        if not isinstance(machines, list):
            return []
        return sorted(
            wire.jstr(m.get("machineId"))
            for m in machines
            if isinstance(m, dict) and m.get("machineId")
        )

    def assert_meter_baseline(self) -> None:
        """THE STARTING METER IS A PRECONDITION, NOT AN OBSERVATION. Each run mints its own user and subscription, so the meter starts empty by construction and the only way to hold more than the one machine under test is for that machine to have been counted under a SECOND id.
        That happened on 2026-10-01 (first run on a fresh Ceph fleet: activations 2, not 1; the account DB showed the repo's first issuance by 42e1cfb3..., the reissue a minute later by c99b905a..., the id `sudo renet machine-id` reports for the VM). Two causes were found and fixed at the root: renet's `GetMachineID` hashed the MAC of every non-blocklisted interface, so a transient veth/tap/bridge moved the id (it now counts only device-backed Ethernet with a permanent address, read from sysfs), and the CLI fell back to a NON-ROOT `renet machine-id`, which hashes without the root-only product_uuid (that fallback is gone and renet refuses the non-root read).
        Every later cap-dependent step (leg e's seed of 3, leg f's third machine) would fail with 'Maximum machines reached', far from the cause, so the baseline is still asserted here, where the cause is in sight, and a mismatch names the foreign ids."""
        d, o = self.d, self.o
        _, own = self.ssh_out(o.vm_ip, "sudo %s machine-id" % o.vm_renet)
        own = own.strip()
        claimed = self.claimed_machine_ids()
        foreign = [m for m in claimed if m != own]
        if foreign:
            d.note("machine under test (sudo renet machine-id on %s): %s" % (o.vm_ip, own or "?"))
            for machine in claimed:
                d.note(
                    "  claimed on the subscription: %s%s"
                    % (machine, "" if machine == own else "   <-- FOREIGN")
                )
            d.note("a foreign id on a fresh subscription is the machine under test counted under")
            d.note("a second id (a renet older than the sysfs NIC filter, or a non-root read of")
            d.note(
                "`renet machine-id`), not a second machine; legs e and f assume exactly one here"
            )
        d.last_cmd = "GET /licenses/status (machines claimed before the fork)"
        d.assert_equal(
            own,
            ",".join(claimed),
            "the subscription's meter holds exactly this machine (no phantom claim)",
        )

    def leg_a_preclean(self) -> None:
        o = self.o
        hosts = [o.vm_ip]
        # Only when leg b is in play: the preflight proves VM2 is running for that leg and for no other, and an unreachable host here would abort the drill for a step that is pure hygiene.
        if o.enabled("b"):
            hosts.append(o.vm2_ip)
        for host in hosts:
            proc = subprocess.run(
                self.ssh_argv(host, "bash -s"),
                input=preclean_script(o.vm_renet),
                capture_output=True,
                text=True,
                check=False,
            )
            self.report_preclean(host, proc.returncode, proc.stderr)

    def report_preclean(self, host: str, code: int, stderr: str) -> None:
        """A pre-clean that did not finish clean is said out loud, with renet's own words, BEFORE the `datastore create` it would otherwise break with a bare "already exists". It stays a warning, not an assertion: the pre-clean is hygiene, and the step it guards asserts on its own."""
        if code == 0:
            return
        log.warn(
            "leg a pre-clean on %s did not finish clean (exit %d); what it could not remove may fail the datastore create below:"
            % (host, code)
        )
        for line in stderr.strip().splitlines() or ["<no stderr; ssh itself may have failed>"]:
            log.warn("  %s" % line)

    def datastore_entry(self, name: str) -> dict:
        _, out = self.ssh_out(self.o.vm_ip, "sudo %s datastore list --json" % self.o.vm_renet)
        parsed = wire.parse(out)
        if isinstance(parsed, list):
            for entry in parsed:
                if isinstance(entry, dict) and entry.get("name") == name:
                    return entry
        return {}

    def fork_status(self, mount: str) -> str:
        _, out = self.ssh_out(
            self.o.vm_ip,
            "sudo %s repository license-status --datastore %s --output json"
            % (self.o.vm_renet, mount),
        )
        parsed = wire.parse(out)
        first = parsed[0] if isinstance(parsed, list) and parsed else {}
        return wire.jstr(first.get("status")) if isinstance(first, dict) else ""

    def leg_a_fork_remeters(self) -> None:
        d, o = self.d, self.o
        d.step("Leg a: forking a datastore re-meters the repo inside it")
        self.leg_a_preclean()

        # The ops provisioner creates pool rediacc_rbd_pool, not the rbd default.
        d.run(
            [
                self.rdc,
                "datastore",
                "create",
                DATASTORE_NAME,
                "-m",
                MACHINE_NAME,
                "--size",
                "10G",
                "--backend",
                "rbd",
                "--pool",
                "rediacc_rbd_pool",
            ]
        )
        # The preflight catches the common case from here, but it cannot evaluate the CLI's ancestry check on an override that IS set. If the CLI refuses, report the precondition rather than a bare assertion failure.
        if "blocked in agent mode" in d.stderr_text():
            self.agent_override_blocked_message(
                ["REDIACC_ALLOW_CLUSTER_OPS=*  (rejected by the CLI's ancestry check)"]
            )
            raise SystemExit(1)
        d.assert_exit(0, "a Ceph-backed datastore is created")

        # A newly created datastore is DETACHED by design; attach before use.
        d.run([self.rdc, "datastore", "attach", DATASTORE_NAME, "--to", MACHINE_NAME])
        d.assert_exit(0, "the datastore is attached to the machine")

        # Exactly ONE placement flag: --machine (docker, default datastore) XOR --datastore (named datastore).
        d.run(
            [
                self.rdc,
                "repo",
                "create",
                REPO_NAME,
                "--datastore",
                DATASTORE_NAME,
                "--size",
                "1G",
                "--debug",
            ]
        )
        d.assert_exit(0, "a repo is created inside it (issuance happens here)")

        parent_status = self.repo_status(o.vm_ip, "status")
        parent_ds = self.repo_status(o.vm_ip, "datastoreId")
        d.last_cmd = "renet repository license-status --all-datastores (parent)"
        d.assert_equal("valid", parent_status, "the parent repo's licence is valid")
        d.assert_not_equal("", parent_ds, "and it is scoped to a real datastoreId")

        self.assert_meter_baseline()
        before = self.meter_snapshot()

        d.run(
            [
                self.rdc,
                "datastore",
                "fork",
                DATASTORE_NAME,
                "--tag",
                FORK_TAG,
                "--attach-to",
                MACHINE_NAME,
                "--writes",
                "local",
            ]
        )
        d.assert_exit(0, "the datastore is forked")

        entry = self.datastore_entry("%s:%s" % (DATASTORE_NAME, FORK_TAG))
        fork_ds = wire.jstr(entry.get("datastoreId"))
        d.last_cmd = "renet datastore list --json"
        d.assert_not_equal(
            parent_ds,
            fork_ds,
            "the clone carries a NEWLY minted datastoreId (fork time is the stamp point)",
        )

        # The fork's mount is NOT /mnt/rediacc-ds/<name>:<tag>: renet mounts a fork at <parent>-<tag> (hyphen). Read the real path from the registry rather than deriving it; a wrong path makes license-status answer [] and every status read after it an empty string.
        fork_mount = wire.jstr(entry.get("mountPath"))
        status = self.fork_status(fork_mount)
        d.last_cmd = "renet repository license-status (fork)"
        d.assert_equal(
            "missing", status, "the repo inside the clone reads 'missing' under the new scope (S8b)"
        )

        d.run([self.rdc, "subscription", "refresh", "-m", MACHINE_NAME])
        d.assert_exit(0, "a refresh reissues for the new scope")

        status = self.fork_status(fork_mount)
        d.last_cmd = "renet repository license-status (fork, after reissue)"
        d.assert_equal("valid", status, "the fork's own licence is now valid (S8c)")

        d.assert_equal(
            "valid",
            self.repo_status(o.vm_ip, "status"),
            "and the PARENT's licence is still valid (S8d: the fork did not steal it)",
        )

        after = self.meter_snapshot()
        d.assert_not_equal(
            before,
            after,
            "the reissue claimed a slot: the subscription's meter moved (%s -> %s)"
            % (before, after),
        )

    # ------------------------------------------------------------------ leg b

    def leg_b_migration_does_not_remeter(self) -> None:
        """WHAT "MIGRATION" MEANS HERE. A repo-level `repo migrate` is a backup_push of the repo IMAGE: the licence blobs stay behind and the peer vault gives the target its DEFAULT datastore, so the repo lands in a different scope by construction and re-metering there is correct. The claim 02-licensing-design.md §2 makes is about DATASTORE migration, "same datastore, new node: identity travels with the datastore", and the verb for that is `datastore attach --to <other machine>`. The descriptor rides inside the image, so its identity arrives unchanged and nothing re-mints.

        The assertion is EQUALITY OF THE ID, not "the licence still validates": a PRE-IDENTITY datastore gets a fresh id minted on its first read-write plain attach, every repo inside re-scopes and reissues, and "still validates" would sail through that silent re-meter. The relocation is undone at the end because legs c-e read the machine this drill set up."""
        d, o = self.d, self.o
        d.step("Leg b: relocating the datastore keeps its identity")
        # A datastore with a mounted repo inside refuses to detach, and the relocation detaches implicitly, so the repo comes down first. Setup for the claim, not part of it.
        d.setup_run([self.rdc, "repo", "down", REPO_NAME, "--unmount"])

        before_ds = self.repo_status(o.vm_ip, "datastoreId")
        before_meter = self.meter_snapshot()
        d.last_cmd = "renet repository license-status --all-datastores on %s" % o.vm_ip
        d.assert_not_equal("", before_ds, "the datastore has an identity to travel with")

        d.run([self.rdc, "datastore", "attach", DATASTORE_NAME, "--to", MACHINE2_NAME])
        d.assert_exit(0, "the datastore relocates to the second machine")

        after_ds = self.repo_status(o.vm2_ip, "datastoreId")
        d.last_cmd = "renet repository license-status --all-datastores on %s" % o.vm2_ip
        d.assert_equal(
            before_ds,
            after_ds,
            "the datastoreId travelled with the descriptor: no datastore re-mint",
        )

        after_meter = self.meter_snapshot()
        d.last_cmd = "GET /portal/subscription (meter after the relocation)"
        d.assert_equal(
            before_meter,
            after_meter,
            "and the subscription's meter did not move (%s): no re-metering" % before_meter,
        )

        # Put it back where legs c-e (and the next run's leg a preclean) expect it.
        d.run([self.rdc, "datastore", "attach", DATASTORE_NAME, "--to", MACHINE_NAME])
        d.assert_exit(0, "the datastore relocates back to the first machine")

        # The DETACHED relocation is a different code path: with nothing holding the datastore there is no current holder to ferry its registry row from, so the CLI has to remember who held it last. Both halves are exercised because only the pair proves it.
        d.run([self.rdc, "datastore", "detach", DATASTORE_NAME])
        d.assert_exit(0, "the datastore detaches, holding no machine at all")

        d.run([self.rdc, "datastore", "attach", DATASTORE_NAME, "--to", MACHINE2_NAME])
        d.assert_exit(
            0, "a DETACHED datastore still attaches elsewhere (ferried from its last holder)"
        )

        after_ds = self.repo_status(o.vm2_ip, "datastoreId")
        d.last_cmd = (
            "renet repository license-status --all-datastores on %s (after the detached move)"
            % o.vm2_ip
        )
        d.assert_equal(
            before_ds,
            after_ds,
            "and it arrives with the same identity: a detached move re-meters nothing either",
        )

        d.run([self.rdc, "datastore", "attach", DATASTORE_NAME, "--to", MACHINE_NAME])
        d.assert_exit(0, "the datastore comes home again")

    # ------------------------------------------------------------------ leg c

    def installed_renewal_url(self) -> str:
        _, out = self.ssh_out(
            self.o.vm_ip,
            "sudo find /var/lib/rediacc/license -name '*.json' -path '*/repos/*' | head -1 | xargs -r sudo cat",
        )
        parsed = wire.parse(out)
        payload = wire.lookup(parsed, "payload")
        if not isinstance(payload, str):
            return ""
        try:
            return wire.jstr(json.loads(base64.b64decode(payload).decode()).get("renewalUrl"))
        except (ValueError, UnicodeDecodeError):
            return ""

    def leg_c_credentialless_renewal(self) -> None:
        d, o = self.d, self.o
        d.step("Leg c: renewal driven only by the installed blob")
        # The blob is the credential AND the address book. If it carries no renewalUrl, or the machine cannot reach the one it carries, renewal cannot work: a finding about the deployment, asserted rather than worked around.
        url = self.installed_renewal_url()
        d.last_cmd = "read renewalUrl out of the installed blob on %s" % o.vm_ip
        d.assert_not_equal("", url, "the installed blob carries a renewalUrl")

        health = url.removesuffix("/licenses/renew")
        self.ssh_run(
            o.vm_ip,
            "curl -sf -m 5 -o /dev/null '%s/health' || curl -sf -m 5 -o /dev/null '%s'"
            % (health, url),
        )
        d.assert_exit(0, "the machine can reach that URL (a localhost baseUrl would fail here)")

        self.ssh_run(o.vm_ip, "test ! -e /root/.config/rediacc && test ! -e ~/.config/rediacc")
        d.assert_exit(0, "the machine holds no rdc config and no account token")

        self.ssh_run(o.vm_ip, "sudo %s license renew --force --output json" % o.vm_renet)
        d.assert_exit(0, "renet license renew exits 0")
        results = self.stdout_field("results")
        self.av(
            _result_any(results, "outcome", "renewed"), True, "at least one licence was renewed"
        )
        self.av(_result_none(results, "outcome", "error"), True, "and nothing errored")

        seq = renewed_sequence(results)
        d.assert_not_equal("0", str(seq), "the renewed blob carries a fresh sequence (%d)" % seq)

    # ------------------------------------------------------------------ leg d

    def leg_d_refusal_on_lapse(self) -> None:
        d, o = self.d, self.o
        d.step("Leg d: renewal refuses, by name, once the subscription has lapsed")
        self.patch_subscription({"status": "suspended"})
        self.subscription_lapsed = True
        d.note("subscription suspended")

        self.ssh_run(o.vm_ip, "sudo %s license renew --force --output json" % o.vm_renet)
        d.assert_exit(0, "renew still exits 0: one dead repo must not stop every other backup")
        results = self.stdout_field("results")
        self.av(
            _result_any(results, "outcome", "refused"),
            True,
            "the refusal is reported per repository",
        )
        self.av(
            _result_any(results, "code", "SUBSCRIPTION_LAPSED"),
            True,
            "and carries the exact refusal code, not a generic failure",
        )

        self.patch_subscription({"status": "active"})
        self.subscription_lapsed = False
        d.note("subscription restored to active")

    # ------------------------------------------------------------------ leg e

    def leg_e_soft_claim_over_cap(self) -> None:
        """WHICH MACHINE GOES OVER, and why this leg needs a second one at all. The cap is on MACHINES, and over-limit is positional: an activation row is over the cap when its INDEX among the subscription's rows, ordered by id, reaches maxActivations (subscription.service.ts, touchActivationSoftClaim). The first machine to claim is never over the cap, so a second machine is part of the SETUP, activated over raw HTTP (the claim under test is about the metering, not renet) and BEFORE the cap drops, because new issuance past the cap blocks hard by design and only renewal soft-claims."""
        d, o = self.d, self.o
        d.step("Leg e: past the cap, renewal still succeeds and the overage is visible")
        # Start from a known cap rather than a hoped-for one, so "the cap moved" is an assertion instead of an assumption.
        status_json = self.license_status()
        d.last_cmd = "GET /licenses/status (before lowering the cap)"
        d.assert_equal(
            str(START_MAX_ACTIVATIONS),
            lib.json_get(status_json, "maxMachines"),
            "the subscription starts at the cap this drill seeded (%d)" % START_MAX_ACTIVATIONS,
        )

        second_machine = secrets.token_hex(32)
        activated = self.activate_repo_for(second_machine)
        d.last_cmd = "POST /licenses/activate-repo (a second machine, still under the cap)"
        d.assert_equal(
            "string",
            wire.typeof(wire.lookup(wire.parse(activated), "license.payload")),
            "a second machine claims a slot while the subscription is still under its cap",
        )

        # Lowering the cap on a LIVE subscription is the only way to reach an overage, and it is also the realistic one (a downgrade). /test/ensure-subscription would delete this subscription and orphan its licences.
        self.patch_subscription({"maxActivations": 1})
        self.cap_lowered = True
        d.note("maxActivations lowered to 1, below the two machines already claiming")

        # The first machine is still within the cap, so its own results are not flagged; what it proves is that a subscription in overage does not break the renewals of the machines still inside it.
        self.ssh_run(o.vm_ip, "sudo %s license renew --force --output json" % o.vm_renet)
        d.assert_exit(0, "renew exits 0 while the subscription is over its cap")
        self.av(
            _result_any(self.stdout_field("results"), "outcome", "renewed"),
            True,
            "renewal SUCCEEDS over the cap (soft claim: meter honestly, never block)",
        )

        renewed = self.renew_blob_for(second_machine, activated)
        self.capture("POST /licenses/renew (the machine that is past the cap)", renewed)
        d.assert_equal(
            "string",
            wire.typeof(self.stdout_field("license.payload")),
            "the over-cap machine's renewal is honoured, not refused",
        )
        self.aj("overLimit", True, "and the renewed result is flagged overLimit")

        status_json = self.license_status()
        d.last_cmd = "GET /licenses/status (after the overage)"
        count = wire.lookup(wire.parse(status_json), "overLimitCount")
        d.assert_not_equal(
            "0",
            wire.jstr(count) if count not in (wire.MISSING, None, 0, "") else "0",
            "/licenses/status reports the overage (overLimitCount > 0)",
        )

        self.patch_subscription({"maxActivations": START_MAX_ACTIVATIONS})
        self.cap_lowered = False

    # ------------------------------------------------------------------ leg f

    def leg_f_dto_boundary(self) -> None:
        """The response airlock used to strip chainHash and delegationCert from every licence response, and every existing assertion about those fields ran at the SERVICE layer, where the airlock does not exist. So this leg reads the raw HTTP body, and ships a planted-strip control so that a pass cannot come from a check that is incapable of failing."""
        d = self.d
        d.step("Leg f: chainHash and delegationCert survive the HTTP boundary")
        machine_id = secrets.token_hex(32)
        body = self.activate_repo_for(machine_id)
        self.capture("POST /licenses/activate-repo (raw HTTP)", body)

        # The signed blob is nested under `license` in the activate-repo response.
        self.at_stdout("license.payload", "string", "the response carries a payload")
        self.at_stdout("license.signature", "string", "and a signature")
        self.at_stdout(
            "license.chainHash",
            "string",
            "and chainHash SURVIVES the response airlock (this is the field it used to strip)",
        )

        # Planted-strip control: the same assertion against a body with the field removed must report it missing. Without this, "chainHash is a string" could be passing because the check never looks.
        # A refusal body (`{"error": ...}`) or a non-JSON one has no `license` to strip; the three assertions above already reported it as a failure, so the control degrades to an empty object instead of crashing the drill with a raw traceback.
        parsed_body = wire.parse(body)
        stripped = parsed_body if isinstance(parsed_body, dict) else {}
        if isinstance(stripped.get("license"), dict):
            stripped["license"].pop("chainHash", None)
            stripped["license"].pop("delegationCert", None)
        (self.work / "stripped.json").write_text(wire.compact(stripped))
        stripped_type = wire.typeof(wire.lookup(stripped, "license.chainHash"))
        d.last_cmd = "planted-strip control"
        d.assert_equal(
            "undefined",
            stripped_type,
            "planted-strip control: with chainHash removed the same check sees it gone",
        )

        cert_type = wire.typeof(self.stdout_field("license.delegationCert"))
        if cert_type == "undefined":
            d.note("this account server is not a delegated (on-premise) deployment, so it")
            d.note("attaches no delegationCert. The chainHash half of the boundary is proven")
            d.note("above; to prove the delegationCert half, point the drill at a server")
            d.note("started from src/entry/on-premise.ts with DELEGATION_CERT_PATH set.")
            d.last_cmd = "POST /licenses/activate-repo (non-delegated server)"
            d.assert_equal(
                "undefined",
                cert_type,
                "non-delegated server: no delegationCert to strip (delegated half NOT covered)",
            )
        else:
            d.last_cmd = "POST /licenses/activate-repo (delegated server)"
            d.assert_equal(
                "string",
                cert_type,
                "delegationCert SURVIVES the response airlock on a delegated deployment",
            )

    def at_stdout(self, path: str, expected_type: str, desc: str) -> None:
        self.d.assert_equal(expected_type, wire.typeof(self.stdout_field(path)), desc)

    # ------------------------------------------------------------------ main

    def run_all(self) -> int:
        o, d = self.o, self.d
        self.announce_cost()
        d.selftest_probe()
        if d.selftest:
            self.setup_sandbox()
            d.note("selftest mode: stopping before any VM or server work")
            return d.summary()

        # Preflight BEFORE the sandbox exports: preflight_vms runs `rdc ops status`, a full CLI invocation, and the CLI auto-creates the config named by REDIACC_CONFIG on startup. With the export in place first, that auto-creation races the later `config init` and it dies with "already exists" (found live 2026-08-04).
        self.preflight_tools()
        self.preflight_vms()
        self.preflight_ssh()
        self.preflight_agent_overrides()
        self.setup_sandbox()
        self.setup_gateway_address()
        self.setup_gateway()
        self.setup_account()

        if o.needs_vm():
            self.setup_config()
            self.ensure_repo_present()

        for leg, fn in (
            ("a", self.leg_a_fork_remeters),
            ("b", self.leg_b_migration_does_not_remeter),
            ("c", self.leg_c_credentialless_renewal),
            ("d", self.leg_d_refusal_on_lapse),
            ("e", self.leg_e_soft_claim_over_cap),
            ("f", self.leg_f_dto_boundary),
        ):
            if o.enabled(leg):
                fn()
        return d.summary()


def _agent_session() -> bool:
    """True when any agent-mode marker is set (the five the bash tested)."""
    return bool(
        os.environ.get("REDIACC_AGENT")
        or os.environ.get("CLAUDECODE")
        or os.environ.get("GEMINI_CLI")
        or os.environ.get("COPILOT_CLI")
        or os.environ.get("CURSOR_TRACE_ID")
    )


def _js_text(value: object) -> str:
    """String concatenation of a parsed-JSON value the way JavaScript prints it (`undefined` for an absent field)."""
    if value is wire.MISSING:
        return "undefined"
    return "null" if value is None else wire.jstr(value)


def main(argv: list[str]) -> int:
    selftest, keep_work, rest = lib.parse_common_args(argv)
    opts = Options()
    code = parse_args(rest, opts)
    if code is not None:
        return code
    drill = lib.Drill("license", selftest=selftest, keep_work=keep_work)
    # This drill targets only the disposable local ops VMs, so a renet built from a dirty private/renet tree may be uploaded to them.
    drill.extra_env["REDIACC_ALLOW_DIRTY_RENET"] = "1"
    drill.init()
    license_drill = License(drill, opts)
    rc = 1
    try:
        rc = license_drill.run_all()
    except SystemExit as exc:
        rc = int(exc.code) if isinstance(exc.code, int) else 1
    except (lib.GatewayError, OSError) as exc:
        log.error(str(exc))
        rc = 1
    finally:
        with contextlib.suppress(Exception):
            license_drill.teardown_hook()
        drill.teardown()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
