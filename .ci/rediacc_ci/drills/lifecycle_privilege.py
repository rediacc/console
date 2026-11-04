"""L1 of agent/plans/PLAN-rediaccfile-unprivileged.md (boxes P1 and T1): a Rediaccfile's `up()` and `down()` run as the universal user, and a repository gets more only by an operator's grant. The rows assert the FIXED behaviour; a defect is a FAIL row, so the same drill on the tree before the drop is the failing evidence.

`vm_check.py` registers this module once, through `EXTRA_RENET_STEPS`, as the `L1` step of the renet phase; `--only L1` drags in P5, so the run's parent grand exists. `ctx` is the running `VmCheck`: every VM action goes through its `./rdc.sh` helpers (`rdc`, `shell`), its raw ssh probe recipe (`vm_ssh.ssh_argv` through `host_run`) and its ledger (`check`).

THE PROBE. A fork of the parent grand gets a probe `Rediaccfile` written through `term connect` (the repository's own sandbox shell, which may write its mount). Its `up()` and `down()` write `key=value` lines to `lifecycle-probe.<function>` in the mount, reporting verdicts only, never the content of what they tried to read: the uid, CapEff, `/proc/kcore`, `/etc/shadow`, the first block device, `/etc/rediacc/grants`, `none` for a block device or grants directory the worker does not have (nothing was probed, which L1.2 fails instead of reading as denied), whether a fake credential reached the function's environment or its parent's `/proc/<pid>/environ`, `sudo -n`, the owner of a file `up()` creates (`created_owner`) and of the `.env` it appends to (`env_owner`), and what an open of the fake CDI node answers (`cdi_open`, in the C locale the probe sets). The drill reads the lines back through `term connect` and judges them with the pure functions below.

THE ROWS. L1.0 the probe is installed in the fork; L1.1 `repo up` runs the probe as a uid other than 0 with an empty CapEff; L1.2 every denied probe is denied and the fake credential in `rdc`'s own environment never reached `up()`; L1.3 `sudo` fails on `no_new_privs`; L1.4 a file `up()` creates belongs to the function's uid; L1.5 a failing `renet compose` inside `up()` fails the `repo up`; L1.6 `repo down` runs the probe's `down()` as the same uid; L1.7 the fork's grant holds no lifecycle root or path; L1.8 the root grant is the positive control (the same probe reports uid 0 under `--lifecycle-root=true`) and its removal restores the drop; L1.9 a FAKE CDI node (gpu_grants' `/dev/rediacc-fake`) is out of reach for `up()` without the repository's device grant and reachable with it. L1.4 also judges the owner of the `.env` file `up()` appends to.

L1.10 (F12) is the cold barrier: a root `renet backup snapshot --cold` on the worker with the fake credential in renet's own environment, which stops and restarts the running fork, so the probe `up()` the barrier runs must report the credential absent. The run's exit status is not read (the barrier is what is judged). L1.11 stops the fork's Docker daemon unit with a probe `down()` that asks the daemon, and `repo down` must fail naming that complaint. L1.12 enables autostart, takes the fork down with `--unmount` and runs one `renet repository reconcile` tick, which must exit 0 with `up()` having run dropped.

TEARDOWN. The fork joins `ctx.forks`, so the run's own teardown deletes it even when L1 crashes. The root grant is removed here; anything that stays rides `ctx.sweep_leftovers`.

The CLI-free pieces (the probe text, the root scripts, and the parsers and verdicts of probe output and grant files) are pure functions, pinned by `tests/test_drills_lifecycle_privilege.py` without a machine.
"""

from __future__ import annotations

import base64
import json
import re
import shlex
from typing import Any

from rediacc_ci.drills import gpu_grants, vm_ssh
from rediacc_ci.well_known import DATASTORE_PATH, ETC_DIR

STEP_ID = "L1"

# Written to the probe files; the value is never printed, only whether it was visible.
CREDENTIAL_VAR = "LIFECYCLE_PROBE_CRED"
CREDENTIAL_VALUE = "l1-fake-credential-do-not-print"
UP_FILE = "lifecycle-probe.up"
DOWN_FILE = "lifecycle-probe.down"
CREATED_FILE = ".lifecycle-probe-created"
FAIL_MARKER = "lifecycle-probe-fail-compose"
# While present, down() asks the repository's Docker daemon something and fails loudly when the daemon does not answer.
DOWN_MARKER = "lifecycle-probe-down-docker"
DOWN_FAIL_MARK = "lifecycle-probe-down-daemon-unreachable"
BAD_COMPOSE = "lifecycle-probe-bad.yml"
NNP_TEXT = "no new privileges"
# gpu_grants' fake CDI device: a 0666 character node no driver claims, so opening it is ENXIO whenever the sandbox lets the function reach it.
CDI_NODE = gpu_grants.NODE_PATH
CDI_REACHED = gpu_grants.ENXIO
# Probe keys the denied-read verdicts judge.
# The one service of `bad_compose()`; a failing `renet compose` names its image.
BAD_IMAGE_HOST = "rediacc.invalid"
BAD_IMAGE_NAME = "lifecycle-probe-missing"
DENIED_KEYS = ("kcore", "shadow", "block", "grants")


def probe_rediaccfile() -> str:
    """The probe Rediaccfile. `up()` and `down()` each write one `key=value` line per probe into the mount; a denied read prints `denied`, a successful one `readable`, and a target the worker does not have `none`."""
    return (
        "#!/bin/bash\n"
        "_report() {\n"
        "  export LC_ALL=C\n"
        '  out="$REDIACC_WORKING_DIR/$1"\n'
        '  : > "$out"\n'
        '  echo "uid=$(id -u)" >> "$out"\n'
        '  echo "capeff=$(awk \'/^CapEff/{print $2}\' /proc/self/status)" >> "$out"\n'
        '  if head -c1 /proc/kcore >/dev/null 2>&1; then echo kcore=readable >> "$out"; else echo kcore=denied >> "$out"; fi\n'
        '  if head -c1 /etc/shadow >/dev/null 2>&1; then echo shadow=readable >> "$out"; else echo shadow=denied >> "$out"; fi\n'
        "  blk=$(ls /sys/block 2>/dev/null | grep -v '^loop\\|^ram\\|^zram' | head -n1)\n"
        '  if [ -z "$blk" ]; then echo block=none >> "$out"; elif head -c1 "/dev/$blk" >/dev/null 2>&1; then echo block=readable >> "$out"; else echo block=denied >> "$out"; fi\n'
        '  if [ ! -e %(etc)s/grants ]; then echo grants=none >> "$out"; elif ls %(etc)s/grants >/dev/null 2>&1; then echo grants=readable >> "$out"; else echo grants=denied >> "$out"; fi\n'
        '  if [ -n "${%(cred)s:-}" ]; then echo cred_env=present >> "$out"; else echo cred_env=absent >> "$out"; fi\n'
        "  if tr '\\0' '\\n' < /proc/$PPID/environ 2>/dev/null | grep -q '^%(cred)s='; then echo cred_parent=readable >> \"$out\"; else echo cred_parent=denied >> \"$out\"; fi\n"
        '  so=$(sudo -n true 2>&1); echo "sudo_rc=$?" >> "$out"; echo "sudo_msg=$(echo "$so" | head -n1)" >> "$out"\n'
        '  : > "$REDIACC_WORKING_DIR/%(created)s"; echo "created_owner=$(stat -c %%u "$REDIACC_WORKING_DIR/%(created)s")" >> "$out"\n'
        '  : >> "$REDIACC_WORKING_DIR/.env"; echo "env_owner=$(stat -c %%u "$REDIACC_WORKING_DIR/.env")" >> "$out"\n'
        '  echo "cdi_open=$( (: < %(cdinode)s) 2>&1 | head -n1 | sed \'s/^.*: //\')" >> "$out"\n'
        "}\n"
        "up() {\n"
        "  _report %(upf)s\n"
        '  if [ -f "$REDIACC_WORKING_DIR/%(marker)s" ]; then\n'
        '    renet compose -- -f "$REDIACC_WORKING_DIR/%(badc)s" up -d\n'
        "  fi\n"
        "}\n"
        "down() {\n"
        "  _report %(downf)s\n"
        '  if [ -f "$REDIACC_WORKING_DIR/%(downmarker)s" ]; then\n'
        "    docker info >/dev/null 2>&1 || { echo %(downtoken)s >&2; return 1; }\n"
        "  fi\n"
        "}\n"
    ) % {
        "cred": CREDENTIAL_VAR,
        "created": CREATED_FILE,
        "etc": ETC_DIR,
        "upf": UP_FILE,
        "downf": DOWN_FILE,
        "marker": FAIL_MARKER,
        "downmarker": DOWN_MARKER,
        "downtoken": DOWN_FAIL_MARK,
        "badc": BAD_COMPOSE,
        "cdinode": CDI_NODE,
    }


def bad_compose() -> str:
    """A compose file whose only service cannot start: the image does not exist, so `renet compose up` must fail."""
    return "services:\n  probe:\n    image: %s/%s:0\n" % (
        BAD_IMAGE_HOST,
        BAD_IMAGE_NAME,
    )


def install_command() -> str:
    """The repository shell's command that writes the probe Rediaccfile and the failing compose file into the mount (through base64, so no quoting meets the script)."""
    rf = base64.b64encode(probe_rediaccfile().encode()).decode()
    bc = base64.b64encode(bad_compose().encode()).decode()
    return (
        "printf %%s %s | base64 -d > Rediaccfile && printf %%s %s | base64 -d > %s && "
        "rm -f %s %s %s %s %s && ls -l Rediaccfile"
        % (rf, bc, BAD_COMPOSE, UP_FILE, DOWN_FILE, CREATED_FILE, FAIL_MARKER, DOWN_MARKER)
    )


def read_command(name: str) -> str:
    """The repository shell's read of one probe output file."""
    return "cat %s" % shlex.quote(name)


def fail_marker_command(on: bool) -> str:
    """The repository shell's switch of the failing-compose mode."""
    return "touch %s" % FAIL_MARKER if on else "rm -f %s" % FAIL_MARKER


def down_marker_command(on: bool) -> str:
    """The repository shell's switch of the daemon-asking `down()` mode."""
    return "touch %s" % DOWN_MARKER if on else "rm -f %s" % DOWN_MARKER


def remove_probe_output_command(name: str) -> str:
    """The repository shell's removal of one probe output file, so the next read can only be what a later function wrote."""
    return "rm -f %s" % shlex.quote(name)


def daemon_unit(network_id: int | str) -> str:
    """The systemd unit of a repository's Docker daemon."""
    return "rediacc-docker-%d" % int(network_id)


def daemon_stop_script(network_id: int | str, on: bool) -> str:
    """Root on the worker: stop (`on`) or start the repository's Docker daemon unit."""
    return "systemctl %s %s" % ("stop" if on else "start", daemon_unit(network_id))


def cold_barrier_script(datastore: str, guid: str) -> str:
    """Root on the worker: a cold `renet backup snapshot` of the repository, run with the fake credential in renet's OWN environment the way a unit's would carry one (F12). The run may end in a refusal after the barrier (no session, no store); only what the barrier's `up()` saw matters, so the exit status is not read."""
    return "env %s=%s renet backup snapshot --datastore %s --repo %s --cold" % (
        CREDENTIAL_VAR,
        CREDENTIAL_VALUE,
        shlex.quote(datastore),
        shlex.quote(guid),
    )


def reconcile_script(datastore: str) -> str:
    """Root on the worker: one reconcile tick, what the autostart-reconcile timer runs."""
    return "renet repository reconcile --datastore %s" % shlex.quote(datastore)


def cold_barrier_verdict(probe: dict[str, str]) -> tuple[bool, str]:
    """(ok, evidence) of the cold-barrier row (F12): the barrier restarted the repository (the probe it wrote is there), `up()` ran dropped, and the credential renet carried reached neither its environment nor its parent's environ. An empty probe means the barrier never ran `up()`, which is a failure and not a pass."""
    if not probe:
        return False, "the barrier wrote no probe: up() did not run"
    ok_drop, why_drop = dropped_verdict(probe)
    ok_cred = probe.get("cred_env") == "absent" and probe.get("cred_parent") == "denied"
    return ok_drop and ok_cred, "%s cred_env=%s cred_parent=%s" % (
        why_drop,
        probe.get("cred_env", "<missing>"),
        probe.get("cred_parent", "<missing>"),
    )


def down_honest_verdict(rc: int, text: str) -> tuple[bool, str]:
    """(ok, evidence) of the stopped-daemon row: a `repo down` whose down() could not reach a stopped Docker daemon fails, and its output carries down()'s own complaint, so a success report or an unrelated failure does not pass."""
    named = DOWN_FAIL_MARK in text
    return rc != 0 and named, "repo down rc=%d down() complaint named=%s %s" % (
        rc,
        named,
        " ".join(text.split())[-200:],
    )


def reboot_verdict(probe: dict[str, str], reconcile_rc: int) -> tuple[bool, str]:
    """(ok, evidence) of the reboot-shaped row: after the mount and daemon were taken away, one reconcile tick exited 0 and its recovery ran `up()` as a dropped uid (the probe file was removed before, so only that run could have written it)."""
    if not probe:
        return False, "reconcile rc=%d and no probe written by the reconcile's up()" % reconcile_rc
    ok_drop, why = dropped_verdict(probe)
    return reconcile_rc == 0 and ok_drop, "reconcile rc=%d %s" % (reconcile_rc, why)


def parse_probe(text: str) -> dict[str, str]:
    """The `key=value` lines of a probe output file; the last value of a key wins, a line without `=` is ignored."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^([a-z_]+)=(.*)$", line.strip())
        if m:
            found[m.group(1)] = m.group(2)
    return found


def uid_of(probe: dict[str, str]) -> int | None:
    return int(probe["uid"]) if probe.get("uid", "").isdigit() else None


def dropped_verdict(probe: dict[str, str]) -> tuple[bool, str]:
    """(ok, evidence) of L1.1: the function ran as a uid other than 0 with an empty effective capability set."""
    uid = uid_of(probe)
    cap = probe.get("capeff", "")
    empty = bool(cap) and set(cap) == {"0"}
    return uid is not None and uid != 0 and empty, "uid=%s capeff=%s" % (uid, cap or "<none>")


def denied_verdict(probe: dict[str, str]) -> tuple[bool, str]:
    """(ok, evidence) of L1.2: every probed read is denied (a `none` probed nothing and is not a denial), and the fake credential reached neither the function's environment nor its parent's environ."""
    bad = [k for k in DENIED_KEYS if probe.get(k) != "denied"]
    if probe.get("cred_env") != "absent":
        bad.append("cred_env")
    if probe.get("cred_parent") != "denied":
        bad.append("cred_parent")
    shown = ", ".join(
        "%s=%s" % (k, probe.get(k, "<missing>")) for k in (*DENIED_KEYS, "cred_env", "cred_parent")
    )
    return not bad, "%s%s" % (shown, "; open: %s" % ", ".join(bad) if bad else "")


def sudo_verdict(probe: dict[str, str]) -> tuple[bool, str]:
    """(ok, evidence) of L1.3: `sudo -n true` failed and the message names `no_new_privs`."""
    rc = probe.get("sudo_rc", "")
    msg = probe.get("sudo_msg", "")
    ok = rc.isdigit() and int(rc) != 0 and NNP_TEXT in msg
    return ok, "sudo rc=%s msg=%s" % (rc or "<none>", msg or "<none>")


def owner_verdict(probe: dict[str, str]) -> tuple[bool, str]:
    """(ok, evidence) of L1.4: the file `up()` created belongs to the uid it ran as, which is not root."""
    uid, owner = uid_of(probe), probe.get("created_owner", "")
    ok = uid is not None and uid != 0 and owner == str(uid)
    return ok, "function uid=%s created-file owner=%s" % (uid, owner or "<none>")


def env_verdict(probe: dict[str, str]) -> tuple[bool, str]:
    """(ok, evidence) of L1.4's `.env` row: the `.env` file `up()` appended to belongs to the uid it ran as, which is not root."""
    uid, owner = uid_of(probe), probe.get("env_owner", "")
    ok = uid is not None and uid != 0 and owner == str(uid)
    return ok, "function uid=%s .env owner=%s" % (uid, owner or "<none>")


def cdi_verdict(probe: dict[str, str], granted: bool) -> tuple[bool, str]:
    """(ok, evidence) of L1.9: the fake CDI node is reachable from `up()` exactly when the repository holds its device grant. Reached is the ENXIO an open of the unclaimed node ends in; any other answer is a denial, and an empty answer is neither."""
    answer = probe.get("cdi_open", "")
    reached = CDI_REACHED in answer
    ok = bool(answer) and reached == granted
    return ok, "cdi_open=%r (%s, expected %s)" % (
        answer or "<none>",
        "reached" if reached else "denied",
        "reached" if granted else "denied",
    )


def root_verdict(probe: dict[str, str]) -> tuple[bool, str]:
    """(ok, evidence) of L1.8's positive control: under the root grant the same probe runs as uid 0."""
    uid = uid_of(probe)
    return uid == 0, "uid=%s" % uid


def up_failed_verdict(rc: int, text: str) -> tuple[bool, str]:
    """(ok, evidence) of L1.5: the `repo up` of a fork whose up() ran a failing `renet compose` failed, and its output names the compose file's missing image, so an unrelated failure (a broken install) does not pass."""
    named = BAD_IMAGE_HOST in text or BAD_IMAGE_NAME in text
    return rc != 0 and named, "repo up rc=%d compose failure named=%s %s" % (
        rc,
        named,
        " ".join(text.split())[-200:],
    )


def grant_show_script(network_id: int | str) -> str:
    """Root on the worker: the network's grant as renet prints it."""
    return "renet daemon grant --network-id %d --show" % int(network_id)


def root_grant_script(network_id: int | str, on: bool) -> str:
    """Root on the worker: set or clear the network's lifecycle root grant (the drill is the operator here; an agent session cannot give `--root`)."""
    return "renet daemon grant --network-id %d --lifecycle-root=%s --show" % (
        int(network_id),
        "true" if on else "false",
    )


def parse_lifecycle(text: str) -> tuple[bool, list[str]] | None:
    """(root, paths) of the first grant object in `text` (one with `version`, `devices`, `lifecycle` or `repo_mount_path`), or None when there is none. A grant with no lifecycle is `(False, [])`."""
    decoder = json.JSONDecoder()
    pos = text.find("{")
    while pos >= 0:
        try:
            doc, _end = decoder.raw_decode(text, pos)
        except ValueError:
            pos = text.find("{", pos + 1)
            continue
        if isinstance(doc, dict) and any(
            k in doc for k in ("version", "devices", "lifecycle", "repo_mount_path")
        ):
            life = doc.get("lifecycle") or {}
            paths = [
                str(p.get("path"))
                for p in (life.get("paths") or [])
                if isinstance(p, dict) and p.get("path")
            ]
            return bool(life.get("root")), paths
        pos = text.find("{", pos + 1)
    return None


def no_grant_verdict(parsed: tuple[bool, list[str]] | None) -> tuple[bool, str]:
    """(ok, evidence) of L1.7: the grant was read and holds no lifecycle root or path."""
    if parsed is None:
        return False, "no grant object in the output"
    root, paths = parsed
    return (not root and not paths), "root=%s paths=%s" % (root, paths)


def fork_tag(tags: tuple[str, str]) -> str:
    """L1's fork tag: fork A's run tag with `-a` turned into `-f`, so the stale-fork sweep (`vm_check.FORK_TAG`) still recognises it."""
    return tags[0].removesuffix("-a") + "-f"


def _clip(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "..."


# --------------------------------------------------------------------------- live


def run(ctx: Any) -> None:
    """The live L1 step. Records L1 rows on `ctx`; removes its root grant and appends any leftover to `ctx.sweep_leftovers`."""
    _LiveL1(ctx).execute()


# The registration entry vm_check's EXTRA_RENET_STEPS takes: (step id, the steps `--only` drags in, the live function). L1 forks the run's parent grand, so it needs P5.
STEP = (STEP_ID, ("P5",), run)


class _LiveL1:
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.tag = fork_tag(ctx.tags)
        self.ref = ctx.ref(self.tag)
        self.nid = 0
        self.guid = ""
        self.root_granted = False
        self.fake_written = False
        self.device_granted = False
        self.daemon_stopped = False
        self.autostart_enabled = False

    # -- helpers ---------------------------------------------------------------

    def check(self, desc: str, ok: bool, res: Any = None, evidence: str = "") -> bool:
        return self.ctx.check(STEP_ID, desc, ok, res, evidence)

    def root(self, command: str, timeout: float = 60.0) -> Any:
        """`command` as root on the worker, through the run's own ssh recipe."""
        argv = vm_ssh.ssh_argv(
            self.ctx.ssh_user,
            self.ctx.ssh_key,
            self.ctx.worker_ip,
            "sudo sh -c %s" % shlex.quote(command),
        )
        return self.ctx.host_run(argv, env=self.ctx.environ, timeout=timeout)

    def shell(self, command: str) -> Any:
        return self.ctx.rdc("term", "connect", self.ref, "-c", command, refuse=False)

    def read_probe(self, name: str) -> dict[str, str]:
        return parse_probe(self.shell(read_command(name)).out)

    def up(self, extra_env: dict[str, str] | None = None) -> Any:
        return self.ctx.rdc("repo", "up", self.ref, timeout=900, refuse=False, extra_env=extra_env)

    def down(self) -> Any:
        return self.ctx.rdc("repo", "down", self.ref, timeout=900, refuse=False)

    # -- the run ---------------------------------------------------------------

    def execute(self) -> None:
        try:
            if not self.fork():
                return
            if not self.install():
                return
            self.l1_1_to_4()
            self.l1_5_failing_compose()
            self.l1_6_down()
            self.l1_7_no_grant()
            self.l1_10_cold_barrier()
            self.l1_11_down_stopped_daemon()
            self.l1_12_reboot_path()
            self.l1_8_root_control()
            self.l1_9_device_grant()
        finally:
            self.cleanup()

    def fork(self) -> bool:
        entry = {"tag": self.tag, "guid": "", "created": True, "deleted": False}
        self.ctx.forks.append(entry)
        res = self.ctx.rdc("repo", "fork", self.ctx.opts.parent, "--tag", self.tag, timeout=1800)
        if not self.check("L1 fork %s (no --up)" % self.ref, res.rc == 0, res):
            return False
        listed, entries = self.ctx.repo_list()
        for item in entries:
            if item.get("name") == self.ref:
                self.guid = str(item.get("guid", ""))
                nid = item.get("networkId", item.get("network_id"))
                if str(nid or "").isdigit():
                    self.nid = int(nid)
        entry["guid"] = self.guid
        return self.check(
            "L1 fork %s listed with a guid and network id" % self.ref,
            bool(self.guid) and bool(self.nid),
            listed,
            "guid %s network id %s" % (self.guid, self.nid),
        )

    def install(self) -> bool:
        res = self.shell(install_command())
        return self.check(
            "L1.0 the probe Rediaccfile is installed in %s" % self.ref,
            res.rc == 0,
            res,
            self.ctx.remote_evidence(res) if res.rc != 0 else "",
        )

    def l1_1_to_4(self) -> None:
        up = self.up(extra_env={CREDENTIAL_VAR: CREDENTIAL_VALUE})
        if not self.check("L1.1 repo up %s runs the probe" % self.ref, up.rc == 0, up):
            return
        probe = self.read_probe(UP_FILE)
        ok, why = dropped_verdict(probe)
        self.check("L1.1 up() runs as a uid other than 0 with an empty CapEff", ok, up, why)
        ok, why = denied_verdict(probe)
        self.check(
            "L1.2 up() is denied kcore, shadow, a block device and the grants directory, and sees no credential",
            ok,
            up,
            why,
        )
        ok, why = sudo_verdict(probe)
        self.check("L1.3 sudo in up() fails on no_new_privs", ok, up, why)
        ok, why = owner_verdict(probe)
        self.check("L1.4 a file up() creates belongs to the function's uid", ok, up, why)
        ok, why = env_verdict(probe)
        self.check("L1.4 the .env file up() writes belongs to the function's uid", ok, up, why)

    def l1_5_failing_compose(self) -> None:
        self.shell(fail_marker_command(True))
        up = self.up()
        ok, why = up_failed_verdict(up.rc, up.out + "\n" + up.err)
        self.check("L1.5 a failing renet compose inside up() fails repo up", ok, up, why)
        self.shell(fail_marker_command(False))

    def l1_6_down(self) -> None:
        down = self.down()
        probe = self.read_probe(DOWN_FILE)
        ok, why = dropped_verdict(probe)
        self.check(
            "L1.6 repo down runs down() as a uid other than 0",
            down.rc == 0 and ok,
            down,
            "down rc=%d %s" % (down.rc, why),
        )

    def l1_7_no_grant(self) -> None:
        res = self.root(grant_show_script(self.nid))
        ok, why = no_grant_verdict(parse_lifecycle(res.out) if res.rc == 0 else None)
        self.check(
            "L1.7 the fork's grant holds no lifecycle root or path",
            ok,
            res,
            "rc=%d %s" % (res.rc, why),
        )

    def l1_10_cold_barrier(self) -> None:
        """F12: a cold backup barrier in a process that carries the credential. The repository is up, its probe output is cleared, and the barrier's own down() and up() are the only writers of the next one."""
        up = self.up()
        if not self.check("L1.10 repo up %s before the cold barrier" % self.ref, up.rc == 0, up):
            return
        self.shell(remove_probe_output_command(UP_FILE))
        barrier = self.root(cold_barrier_script(DATASTORE_PATH, self.guid), timeout=900)
        ok, why = cold_barrier_verdict(self.read_probe(UP_FILE))
        self.check(
            "L1.10 a cold barrier whose renet carries a credential restarts up() without it",
            ok,
            barrier,
            "snapshot rc=%d %s" % (barrier.rc, why),
        )

    def l1_11_down_stopped_daemon(self) -> None:
        """`repo down` against a stopped Docker daemon: down() fails on it, and the verb says so. The daemon is started again before the next row."""
        up = self.up()
        if not self.check("L1.11 repo up %s before the daemon stops" % self.ref, up.rc == 0, up):
            return
        self.shell(down_marker_command(True))
        stopped = self.root(daemon_stop_script(self.nid, True))
        self.daemon_stopped = stopped.rc == 0 or self.daemon_stopped
        try:
            if not self.check(
                "L1.11 the Docker daemon of net-%d is stopped" % self.nid,
                stopped.rc == 0,
                stopped,
                "rc=%d" % stopped.rc,
            ):
                return
            down = self.down()
            ok, why = down_honest_verdict(down.rc, down.out + "\n" + down.err)
            self.check("L1.11 repo down with a stopped daemon reports the failure", ok, down, why)
        finally:
            started = self.root(daemon_stop_script(self.nid, False))
            if started.rc == 0:
                self.daemon_stopped = False
            self.shell(down_marker_command(False))

    def l1_12_reboot_path(self) -> None:
        """Reboot-shaped: autostart on, the repository taken down and unmounted, then one reconcile tick brings it back, running up() dropped."""
        up = self.up()
        if not self.check("L1.12 repo up %s before the reboot shape" % self.ref, up.rc == 0, up):
            return
        enabled = self.ctx.rdc("repo", "admin", "autostart", "enable", self.ref, refuse=False)
        self.autostart_enabled = enabled.rc == 0 or self.autostart_enabled
        if not self.check("L1.12 autostart is enabled for %s" % self.ref, enabled.rc == 0, enabled):
            return
        self.shell(remove_probe_output_command(UP_FILE))
        down = self.ctx.rdc("repo", "down", self.ref, "--unmount", timeout=900, refuse=False)
        if not self.check("L1.12 repo down --unmount takes %s away" % self.ref, down.rc == 0, down):
            return
        tick = self.root(reconcile_script(DATASTORE_PATH), timeout=900)
        ok, why = reboot_verdict(self.read_probe(UP_FILE), tick.rc)
        self.check(
            "L1.12 one reconcile tick ends with the repository running, up() dropped",
            ok,
            tick,
            why,
        )

    def l1_8_root_control(self) -> None:
        granted = self.root(root_grant_script(self.nid, True))
        self.root_granted = granted.rc == 0 or self.root_granted
        if not self.check(
            "L1.8 the operator's root grant is recorded for net-%d" % self.nid,
            granted.rc == 0,
            granted,
            "rc=%d" % granted.rc,
        ):
            return
        up = self.up()
        ok, why = root_verdict(self.read_probe(UP_FILE))
        self.check(
            "L1.8 under the root grant the same probe runs as uid 0 (positive control)",
            up.rc == 0 and ok,
            up,
            "up rc=%d %s" % (up.rc, why),
        )
        cleared = self.root(root_grant_script(self.nid, False))
        if cleared.rc == 0:
            self.root_granted = False
        up = self.up()
        ok, why = dropped_verdict(self.read_probe(UP_FILE))
        self.check(
            "L1.8 withdrawing the root grant restores the drop",
            cleared.rc == 0 and up.rc == 0 and ok,
            up,
            "clear rc=%d up rc=%d %s" % (cleared.rc, up.rc, why),
        )

    def l1_9_device_grant(self) -> None:
        """A fake CDI node is out of reach for `up()` without the device grant and reachable with it; the grant is revoked afterwards."""
        setup = self.root(gpu_grants.setup_script())
        self.fake_written = True
        if not self.check(
            "L1.9 the fake device %s and its CDI spec are written on the worker" % CDI_NODE,
            setup.rc == 0 and gpu_grants.setup_verdict(setup.out),
            setup,
            setup.text(),
        ):
            return
        up = self.up()
        ok, why = cdi_verdict(self.read_probe(UP_FILE), False)
        self.check(
            "L1.9 without a device grant up() cannot open the fake node",
            up.rc == 0 and ok,
            up,
            "up rc=%d %s" % (up.rc, why),
        )
        granted = self.ctx.rdc(
            "repo", "gpu", "grant", self.ref, "--device", gpu_grants.CDI_NAME, refuse=False
        )
        self.device_granted = granted.rc == 0 or self.device_granted
        if not self.check(
            "L1.9 %s is granted to %s" % (gpu_grants.CDI_NAME, self.ref),
            granted.rc == 0,
            granted,
        ):
            return
        up = self.up()
        ok, why = cdi_verdict(self.read_probe(UP_FILE), True)
        self.check(
            "L1.9 with the device grant up() reaches the fake node",
            up.rc == 0 and ok,
            up,
            "up rc=%d %s" % (up.rc, why),
        )

    # -- teardown --------------------------------------------------------------

    def cleanup(self) -> None:
        left: list[str] = []
        if self.root_granted and self.nid:
            res = self.root(root_grant_script(self.nid, False))
            if res.rc != 0:
                left.append("L1 root grant on net-%d (clear rc=%d)" % (self.nid, res.rc))
        if self.daemon_stopped and self.nid:
            res = self.root(daemon_stop_script(self.nid, False))
            if res.rc != 0:
                left.append("L1 stopped Docker daemon of net-%d (start rc=%d)" % (self.nid, res.rc))
        if self.autostart_enabled:
            res = self.ctx.rdc("repo", "admin", "autostart", "disable", self.ref, refuse=False)
            if res.rc != 0:
                left.append("L1 autostart of %s (disable rc=%d)" % (self.ref, res.rc))
        if self.device_granted:
            res = self.ctx.rdc(
                "repo", "gpu", "revoke", self.ref, "--device", gpu_grants.CDI_NAME, refuse=False
            )
            if res.rc != 0:
                left.append("L1 device grant of %s on %s" % (gpu_grants.CDI_NAME, self.ref))
        if self.fake_written:
            res = self.root(gpu_grants.teardown_script())
            if res.rc != 0:
                left.append("L1 fake device %s / spec on the worker (rc=%d)" % (CDI_NODE, res.rc))
        self.ctx.sweep_leftovers.extend(self.ctx.scrub(x) for x in left)


__all__ = [
    "STEP",
    "STEP_ID",
    "bad_compose",
    "cdi_verdict",
    "cold_barrier_script",
    "cold_barrier_verdict",
    "daemon_stop_script",
    "daemon_unit",
    "denied_verdict",
    "down_honest_verdict",
    "down_marker_command",
    "dropped_verdict",
    "env_verdict",
    "fork_tag",
    "grant_show_script",
    "install_command",
    "no_grant_verdict",
    "owner_verdict",
    "parse_lifecycle",
    "parse_probe",
    "probe_rediaccfile",
    "reboot_verdict",
    "reconcile_script",
    "remove_probe_output_command",
    "root_grant_script",
    "root_verdict",
    "run",
    "sudo_verdict",
    "up_failed_verdict",
]
