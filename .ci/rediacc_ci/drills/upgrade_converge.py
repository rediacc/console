"""U1 of agent/plans/PLAN-renet-runtime-converge.md: a renet UPGRADE converges every repo daemon that a pre-isolation renet left on the flat `/var/run/rediacc` layout onto the per-network `net-<N>/` layout.

This is the live half of U1. `vm_check.py` registers it as the `U1` step of the renet phase and calls `run(ctx)` once the fleet, the account token and the ops grand are in hand; `ctx` is the running `VmCheck`, so every VM action still goes through its `./rdc.sh` helpers and its ssh probe, and the forks and the throwaway config this step creates are torn down here (leftovers ride `ctx.sweep_leftovers`, so the run cannot reach VERIFIED over one). The CLI-free pieces -- the layout path strings, the build and status command text, and the parsers that read their output -- are pure functions so `tests/test_drills_upgrade_converge.py` can pin them without a machine.

WHY A PRE-ISOLATION renet AT ALL. A daemon started by a renet older than `0c3a88a` (the per-network layout) keeps the flat layout until something restarts it, and the converge pass (R1/C1) is what moves a machine an upgrade left behind. So U1 installs the commit BEFORE `0c3a88a` (`PRE_ISOLATION_COMMIT`), brings two forks up on it, upgrades through `rdc machine setup`, and asserts the convergence facts: the `net-<N>` socket present, the legacy socket gone, the runtime stamp naming the deployed renet, containers running, and a second dry run reporting nothing stale. Two rows read the cross-reach itself, from fork A's dockerd mount namespace: before the upgrade it lists fork B's socket (the breach), after the converge it lists only its own `net-<N>` directory. Isolation of a running workload is asserted by the I1 tenant drill (agent/plans/PLAN-sandbox-tenant-separation.md).
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shlex
import shutil
import uuid
from typing import TYPE_CHECKING, Any, NamedTuple

from rediacc_ci.drills import lib, vm_ssh
from rediacc_ci.well_known import DATASTORE_PATH, RUNTIME_DIR

if TYPE_CHECKING:
    from collections.abc import Sequence

STEP = "U1"

# The commit BEFORE the per-network layout landed. `0c3a88a` is "fix(sandbox): per-network runtime directories", so its first parent is the last pre-isolation renet. Verified 2026-10-24:
#   git -C private/renet log --oneline 0c3a88a^ -1  ->  7070d28
# but the parent is resolved live in `build_old_renet` so a rebase cannot stale it.
PRE_ISOLATION_COMMIT = "0c3a88a^"

RUNTIME_STATE_DIR = "/var/lib/rediacc/runtime"


def old_docker_socket(network_id: int | str) -> str:
    """The flat Docker socket of the pre-isolation layout, `/var/run/rediacc/docker-<N>.sock`."""
    return "%s/docker-%s.sock" % (RUNTIME_DIR, network_id)


def new_docker_socket(network_id: int | str) -> str:
    """The per-network Docker socket, `/var/run/rediacc/net-<N>/docker-<N>.sock`."""
    return "%s/net-%s/docker-%s.sock" % (RUNTIME_DIR, network_id, network_id)


def runtime_stamp_path(network_id: int | str) -> str:
    """`/var/lib/rediacc/runtime/net-<N>.json`, the stamp StartForeground writes."""
    return "%s/net-%s.json" % (RUNTIME_STATE_DIR, network_id)


def build_old_renet_script(src_dir: str, out_binary: str, commit: str) -> str:
    """The shell that materialises a pre-isolation renet source tree at `commit` and builds it, WITHOUT touching private/renet/bin (the CLI uploads what `renetPath` names).

    A `git clone --shared --no-checkout` of private/renet then a detached `checkout` gives the full tree: renet's `.gitattributes` sets `* export-ignore`, so `git archive` exports only LICENSE and is useless here, while a checkout ignores export-ignore. `go build -tags nolicense -o <out> ./cmd/renet` from inside is the old binary. The tag is honoured only because `PRE_ISOLATION_COMMIT` predates renet aa872edb, which deleted `runtime_nolicense.go` (agent/plans/PLAN-production-key-only.md N1): at that commit the tag still selects the no-licence stub, so the old binary needs no baked key, and U1 tests the runtime layout, not licensing. The current binary it upgrades to is the one licensed build. `commit` is a concrete sha resolved against the submodule before the build, so the shared clone always finds it.
    """
    src = shlex.quote(src_dir)
    out = shlex.quote(out_binary)
    sha = shlex.quote(commit)
    return (
        "set -eu\n"
        "rm -rf %(src)s\n"
        "git clone --quiet --shared --no-checkout private/renet %(src)s\n"
        "git -C %(src)s -c advice.detachedHead=false checkout --quiet %(sha)s\n"
        "cd %(src)s && go build -tags nolicense -o %(out)s ./cmd/renet\n"
        % {"src": src, "out": out, "sha": sha}
    )


# The path every provisioned machine resolves `renet` through: /usr/bin/renet -> current/renet -> the versioned slot (packages/cli/src/services/renet/renet-provisioner.ts REMOTE_CURRENT_PATH), and the host-scoped lock the provisioner installs under.
RENET_CURRENT = "/usr/lib/rediacc/renet/current/renet"
RENET_PROVISION_LOCK = "/tmp/.rdc-renet-provision.lock"


def staged_renet_path(run_id: str, step: str) -> str:
    """Where the old binary is uploaded on the worker before the install, e.g. `/tmp/.rdc-drill-renet-u1-vmc-...`."""
    return "/tmp/.rdc-drill-renet-%s-%s" % (step.lower(), run_id)


def with_stdin_from(path: str, argv: Sequence[str]) -> list[str]:
    """`argv` with its stdin read from the local file `path`, through `bash -c`. The file's content never reaches any argv, which is how a repo credential travels to `--password-stdin`."""
    return ["bash", "-c", 'exec "$@" < "$0"', path, *argv]


def install_current_renet_script(staged: str, sudo: str = "sudo") -> str:
    """The ssh user on the worker: replace the binary `RENET_CURRENT` resolves to with `staged`, under the provisioner's lock, and print `INSTALLED <sha256>`.

    This is what the CLI's own provision did to the slot when `renetPath` named the old build (the dev VERSION is constant, so old and new share one slot), without a job: since console 87455a94f every CLI machine command is a renet job, and a renet older than the job flags refuses it. `NOTARGET` (exit 3) when `current` resolves outside the install root, which would mean the CLI never provisioned this machine.

    The lock is taken as the ssh user and only the install runs under `sudo`, as the provisioner does: the lock file in /tmp belongs to that user, and with `fs.protected_regular=2` (Ubuntu's default) root cannot open another user's file in a sticky directory (`flock: cannot open lock file ...: Permission denied`, rc 66 on ops-worker, 2026-10-30). `sudo` is a parameter so the tests run the script unprivileged.
    """
    return (
        # The staged upload goes on every exit, a failed install included.
        "set -eu; staged=%(staged)s; trap 'rm -f \"$staged\"' EXIT; "
        "target=$(readlink -f %(current)s || true); "
        'case "$target" in %(root)s/*/renet) ;; *) echo "NOTARGET $target"; exit 3;; esac; '
        'flock -w 120 %(lock)s %(sudo)s sh -c \'install -m 0755 "$1" "$2.drill" && mv -f "$2.drill" "$2"\' _ "$staged" "$target"; '
        'echo "INSTALLED $(sha256sum "$target" | cut -d" " -f1)"'
        % {
            "staged": shlex.quote(staged),
            "current": shlex.quote(RENET_CURRENT),
            "root": shlex.quote(os.path.dirname(os.path.dirname(RENET_CURRENT))),
            "lock": shlex.quote(RENET_PROVISION_LOCK),
            "sudo": sudo,
        }
    )


def installed_sha(text: str) -> str:
    """The sha256 an `install_current_renet_script` run printed, "" when it printed none."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "INSTALLED" and len(parts[1]) == 64:
            return parts[1]
    return ""


def old_repo_up_command(guid: str, network_id: int, repo_name: str, grand_guid: str) -> str:
    """The command the pre-isolation renet's `repository_up` builder produced for a fork (renet 7070d28 `pkg/functions/commands/repository.go` RepositoryUpCommand.Build), run directly instead of through a job. The credential arrives on stdin."""
    return " ".join(
        shlex.quote(a)
        for a in (
            "sudo",
            "renet",
            "repository",
            "up",
            "--name",
            guid,
            "--datastore",
            DATASTORE_PATH,
            "--network-id",
            str(network_id),
            "--repo-name",
            repo_name,
            "--grand-guid",
            grand_guid,
            "--password-stdin",
        )
    )


class ForkRecord(NamedTuple):
    """What the old renet's `repository up` needs about one fork, as the CLI recorded it."""

    guid: str
    network_id: int
    credential: str
    grand_guid: str


def fork_record(config_doc: Any, parent: str, tag: str) -> ForkRecord | None:
    """Fork `parent:tag` from a config document, None when any field is missing. The guid, credential and grand guid are in `resources.repositories.<parent>.tags.<tag>` (the grand guid falls back to the parent's `latest`), the network id in the state half, `state.repos.<parent>.<tag>.networkId`. Read from the config, not `repo list`: that verb is a renet job and lists no network id for a fork that was never started (measured 2026-10-30)."""
    doc = config_doc if isinstance(config_doc, dict) else {}
    resources = doc.get("resources")
    repos = resources.get("repositories") if isinstance(resources, dict) else None
    entry = repos.get(parent) if isinstance(repos, dict) else None
    tags = entry.get("tags") if isinstance(entry, dict) else None
    if not isinstance(tags, dict):
        return None
    raw_fork, raw_latest = tags.get(tag), tags.get("latest")
    fork: dict[str, Any] = raw_fork if isinstance(raw_fork, dict) else {}
    latest: dict[str, Any] = raw_latest if isinstance(raw_latest, dict) else {}
    state = doc.get("state")
    state_repos = state.get("repos") if isinstance(state, dict) else None
    state_parent = state_repos.get(parent) if isinstance(state_repos, dict) else None
    state_fork = state_parent.get(tag) if isinstance(state_parent, dict) else None
    nid = state_fork.get("networkId") if isinstance(state_fork, dict) else None
    guid = fork.get("repositoryGuid")
    cred = fork.get("credential")
    grand = fork.get("grandGuid") or latest.get("repositoryGuid")
    fields = (guid, cred, grand)
    if not all(isinstance(f, str) and f for f in fields):
        return None
    if not isinstance(nid, int) or isinstance(nid, bool) or nid <= 0:
        return None
    return ForkRecord(str(guid), nid, str(cred), str(grand))


def old_docker_pid_file(network_id: int | str) -> str:
    """The flat dockerd pid file of the pre-isolation layout, `/var/run/rediacc/docker-<N>.pid` (renet `pkg/daemon/systemd.go`, the daemon.json `pidfile`)."""
    return "%s/docker-%s.pid" % (RUNTIME_DIR, network_id)


def new_docker_pid_file(network_id: int | str) -> str:
    """The per-network dockerd pid file, `/var/run/rediacc/net-<N>/docker-<N>.pid` (renet `pkg/runpaths` `DockerPid`)."""
    return "%s/net-%s/docker-%s.pid" % (RUNTIME_DIR, network_id, network_id)


def runtime_view_script(pid_file: str, *, allow_host_ns: bool = False) -> str:
    """Root on the worker: list `RUNTIME_DIR` as the dockerd named by `pid_file` sees it, through the mount namespace of that process.

    The pid comes from the pid file, never from `pgrep -f`: renet starts dockerd as `dockerd --config-file=...`, so its command line never names the socket, and an unanchored pattern matched the probe's own `sudo sh -c` process and listed the HOST view (measured 2026-10-26). Prints `NOPID` (exit 3) unless the pid file names a live process whose `/proc/<pid>/comm` is `dockerd`.

    When that dockerd shares the host's mount namespace the listing is the host view. By default that is refused, printing `HOSTNS` (exit 4), so an isolation row can never pass or fail on the host's listing; an unreadable mount-namespace link on either side is refused the same way, so the guard fails closed. The before-upgrade row passes `allow_host_ns=True`: under the old layout a dockerd sharing the host namespace IS the breach (the whole directory, peer sockets included, is reachable from it), and because the pid is a verified dockerd the listing is its genuine view, so the row stays meaningful.

    The old layout bound the whole directory into every repo's dockerd sandbox, so a container started through repo A's Docker API could bind repo B's socket and drive B's daemon (the breach of `0c3a88a`, verified live 2026-10-23); the view listing is that reach, read without starting a container.
    """
    host_check = (
        ""
        if allow_host_ns
        # An unreadable namespace on either side would make the comparison pass, so it is refused as HOSTNS too: the guard fails closed.
        else "own=$(readlink /proc/$pid/ns/mnt); host=$(readlink /proc/1/ns/mnt); "
        '[ -n "$own" ] && [ -n "$host" ] && [ "$own" != "$host" ] '
        "|| { echo HOSTNS; exit 4; }; "
    )
    return (
        "pid=$(cat -- %(pidfile)s 2>/dev/null); "
        "case $pid in ''|*[!0-9]*) echo NOPID; exit 3;; esac; "
        '[ "$(cat /proc/$pid/comm 2>/dev/null)" = dockerd ] || { echo NOPID; exit 3; }; '
        "%(host_check)s"
        "nsenter -t $pid -m ls -1 %(dir)s"
        % {
            "pidfile": shlex.quote(pid_file),
            "host_check": host_check,
            "dir": shlex.quote(RUNTIME_DIR),
        }
    )


def peer_entries(network_id: int | str) -> frozenset[str]:
    """The names under `RUNTIME_DIR` that belong to one network in either layout."""
    return frozenset({"docker-%s.sock" % network_id, "net-%s" % network_id})


def runtime_view_verdict(
    text: str, own: int | str, peer: int | str, *, expect_peer_visible: bool
) -> tuple[bool, str]:
    """(ok, evidence) for one listing from `runtime_view_script`. `expect_peer_visible` is the old layout's breach (the peer's socket or net directory is listed beside the daemon's own); its opposite is the converged layout, where the daemon sees its own `net-<own>` and none of the peer's names. A listing that never ran (`NOPID`, empty) is never ok either way, so a probe that saw nothing cannot read as isolation."""
    entries = {line.strip() for line in text.splitlines() if line.strip()}
    if "HOSTNS" in entries:
        return False, "NOT ISOLATED-CHECKABLE: dockerd shares the host mount namespace (host view)"
    if not entries or "NOPID" in entries:
        return False, "no runtime listing (%s)" % (text.strip()[:80] or "empty")
    sees_peer = bool(entries & peer_entries(peer))
    sees_own = bool(entries & peer_entries(own))
    evidence = "sees_own=%s sees_peer=%s entries=%s" % (sees_own, sees_peer, sorted(entries)[:8])
    if expect_peer_visible:
        return sees_peer, evidence
    return sees_own and not sees_peer, evidence


def dry_run_reports_zero_stale(report_json: str) -> bool:
    """True when a `rdc machine converge --dry-run --json` report shows nothing stale: its summary has `would_converge == 0` and its plan names no stale repo. The CLI prints the report inside its `{"success": ..., "data": {...}}` envelope (measured 2026-10-24), so `data` is unwrapped first; a bare report is read as is."""
    try:
        doc = json.loads(report_json)
    except (ValueError, TypeError):
        return False
    if isinstance(doc, dict) and isinstance(doc.get("data"), dict):
        if doc.get("success") is False:
            return False
        doc = doc["data"]
    if not isinstance(doc, dict):
        return False
    summary = doc.get("summary")
    # An absent count is NOT zero: a report whose field was renamed would otherwise pass the gate vacuously.
    if not isinstance(summary, dict) or summary.get("would_converge") != 0:
        return False
    plan = doc.get("plan")
    if not isinstance(plan, list):
        return False
    return not any(isinstance(e, dict) and e.get("stale_reasons") for e in plan)


def config_name(run_id: str) -> str:
    """The throwaway config name for this run, e.g. `u1-10240427-94d613`."""
    return "u1-%s" % run_id


# --------------------------------------------------------------------------- live


def run(ctx: Any) -> None:
    """The live U1 step. Records U1 assertion rows on `ctx`; cleans up its forks, grand and config, and appends any leftover to `ctx.sweep_leftovers`.

    Delegated here (not inlined in vm_check) so the step is one named unit and the pure helpers it is built from are tested without a VM.
    """
    _LiveU1(ctx).execute()


class _LiveU1:
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.cfg = config_name(ctx.run_id)
        self.parent = "u1base-%s" % ctx.run_id[-6:]
        self.tag_a = "u1a"
        self.tag_b = "u1b"
        self.tmp = pathlib.Path(ctx.work) / ("u1-%s" % ctx.run_id)
        self.old_bin = self.tmp / "renet-old"
        self.new_bin = self.tmp / "renet-new"
        self.symlink = self.tmp / "renet"
        self.src_old = self.tmp / "src-old"
        self.created_cfg = False
        self.created_grand = False
        self.net_ids: dict[str, int] = {}
        self.guids: dict[str, str] = {}
        self.new_sha = ""

    # -- helpers ---------------------------------------------------------------

    def say(self, text: str = "") -> None:
        self.ctx.say(text)

    def cfg_env(self) -> dict[str, str]:
        """Select the throwaway config. The minted token and gateway still travel in the child environment (the base `child_env`); only `REDIACC_CONFIG` changes, and RDC_DEV is cleared so `./rdc.sh` does not re-select the dev config over it."""
        return {"REDIACC_CONFIG": self.cfg, "RDC_DEV": ""}

    def crdc(self, *args: str, timeout: float | None = None, refuse: bool = False) -> Any:
        return self.ctx.rdc(*args, timeout=timeout, refuse=refuse, extra_env=self.cfg_env())

    def probe(self, command: str, timeout: float = 60.0) -> Any:
        argv = vm_ssh.ssh_argv(self.ctx.ssh_user, self.ctx.ssh_key, self.ctx.worker_ip, command)
        return self.ctx.host_run(argv, env=self.ctx.environ, timeout=timeout)

    # -- the run ---------------------------------------------------------------

    def execute(self) -> None:
        try:
            if not self._build_renets():
                return
            if not self._make_config():
                return
            if not self._bring_up_old():
                return
            self._old_layout_before_upgrade()
            if not self._upgrade():
                return
            self._assert_converged()
            self._view_rows(before=False)
            self._assert_dry_run_clean()
        finally:
            self._teardown()

    def _build_renets(self) -> bool:
        self.tmp.mkdir(parents=True, exist_ok=True)
        resolved = self.ctx.host_run(
            ["git", "-C", "private/renet", "rev-parse", PRE_ISOLATION_COMMIT],
            env=self.ctx.environ,
            timeout=60,
        )
        if not self.ctx.check(
            STEP,
            "resolve the pre-isolation commit %s" % PRE_ISOLATION_COMMIT,
            resolved.rc == 0 and bool(resolved.out.strip()),
            resolved,
        ):
            return False
        sha = resolved.out.strip()
        script = build_old_renet_script(str(self.src_old), str(self.old_bin), sha)
        res = self.ctx.host_run(["bash", "-c", script], env=self.ctx.environ, timeout=1800)
        if not self.ctx.check(
            STEP,
            "build the pre-isolation renet (%s %s)" % (PRE_ISOLATION_COMMIT, sha[:12]),
            res.rc == 0,
            res,
        ):
            return False
        built = self.ctx.host_run(
            ["cp", str(self.ctx.renet_bin), str(self.new_bin)], env=self.ctx.environ, timeout=120
        )
        if built.rc == 0:
            self.new_sha = file_sha256(self.new_bin)
        return self.ctx.check(
            STEP,
            "stage the current renet build (sha %s)" % self.new_sha[:12],
            built.rc == 0 and bool(self.new_sha),
            built,
        )

    def _point_symlink(self, target: pathlib.Path) -> None:
        if self.symlink.is_symlink() or self.symlink.exists():
            self.symlink.unlink()
        self.symlink.symlink_to(target)

    def _make_config(self) -> bool:
        """The throwaway config: a copy of the dev config this run already seeded (so it carries the gateway's address and E2E key), with `renetPath` pointed at the symlink. The symlink starts on the CURRENT binary: the CLI creates the repos through renet jobs, which the old binary cannot run."""
        self._point_symlink(self.new_bin)
        dev_json = self._config_path("dev")
        target = self._config_path(self.cfg)
        if not dev_json.exists():
            self.ctx.check(
                STEP,
                "the dev config exists to seed the U1 config from",
                False,
                evidence="no %s; P4 did not mint under the dev config" % dev_json,
            )
            return False
        try:
            doc = json.loads(dev_json.read_text())
        except (OSError, ValueError) as exc:
            self.ctx.check(
                STEP,
                "the dev config parses to seed the U1 config from",
                False,
                evidence="%s: %s" % (dev_json, exc),
            )
            return False
        doc["renetPath"] = str(self.symlink)
        # A fresh identity so the two configs are distinct universes on disk; the schema requires a valid UUID here, so set one rather than drop the field.
        doc["id"] = str(uuid.uuid4())
        # Created 0600 from the first byte: the copy carries the gateway E2E key, and write-then-chmod leaves a window where another local user can read it.
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        # O_CREAT keeps the mode of a file left by an earlier run, so the mode is set on the open descriptor before the secret is written.
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(doc, indent=2) + "\n")
        self.created_cfg = True
        listed = self.crdc("machine", "list", "-o", "json")
        names = [str(m.get("name")) for m in _data_list(listed.out)] if listed.rc == 0 else []
        if self.ctx.machine not in names:
            self.crdc(
                "machine",
                "add",
                self.ctx.machine,
                "--ip",
                self.ctx.worker_ip,
                "--user",
                self.ctx.ssh_user,
            )
        self.crdc("machine", "scan-keys", self.ctx.machine)
        return self.ctx.check(
            STEP,
            "U1 config %s created with renetPath -> the drill symlink" % self.cfg,
            target.exists(),
            evidence="renetPath=%s" % self.symlink,
        )

    def _config_path(self, name: str) -> pathlib.Path:
        base = pathlib.Path(self.ctx.environ.get("HOME", "~")) / ".config" / "rediacc"
        return base / ("%s.json" % name)

    def _bring_up_old(self) -> bool:
        """Create the grand and two forks through the CLI on the current renet, then start the forks under the OLD renet (`OldLayoutBringUp`), so their daemons come up on the flat layout."""
        bring = OldLayoutBringUp(
            self.ctx,
            step=STEP,
            check=lambda desc, ok, res=None, evidence="": self.ctx.check(
                STEP, desc, ok, res, evidence=evidence
            ),
            crdc=self.crdc,
            parent=self.parent,
            tags=(self.tag_a, self.tag_b),
            config_path=self._config_path(self.cfg),
            point_symlink=self._point_symlink,
            clear_provision_cache=self._clear_provision_cache,
            old_bin=self.old_bin,
            new_bin=self.new_bin,
            tmp=self.tmp,
        )
        try:
            return bring.run()
        finally:
            self.created_grand = bring.created_grand
            self.net_ids.update(bring.net_ids)
            self.guids.update(bring.guids)

    def _old_layout_before_upgrade(self) -> None:
        """Before the upgrade each fork's daemon serves the flat socket and not the `net-<N>` one: the precondition that makes the converge rows mean something (a fork already on the new layout would pass them vacuously)."""
        for tag in (self.tag_a, self.tag_b):
            nid = self.net_ids.get(tag)
            if not nid:
                continue
            cmd = "test -S %s && echo OLDSOCK; test -S %s && echo NEWSOCK" % (
                shlex.quote(old_docker_socket(nid)),
                shlex.quote(new_docker_socket(nid)),
            )
            res = self.probe("sudo sh -c %s" % shlex.quote(cmd))
            text = res.out + res.err
            self.ctx.check(
                STEP,
                "before the upgrade fork %s serves the flat socket only (net-%s)" % (tag, nid),
                "OLDSOCK" in text and "NEWSOCK" not in text,
                res,
                evidence="old=%s new=%s" % ("OLDSOCK" in text, "NEWSOCK" in text),
            )
        self._view_rows(before=True)

    def _upgrade(self) -> bool:
        """Point the symlink at the current renet and run `rdc machine setup`, so the provision cache sees a new mtime/size and uploads the new binary; the setup converge pass then moves the stale daemons onto net-<N>/."""
        self._point_symlink(self.new_bin)
        self._clear_provision_cache()
        setup = self.crdc("machine", "setup", self.ctx.machine, timeout=1800)
        return self.ctx.check(
            STEP, "rdc machine setup uploads the current renet and converges", setup.rc == 0, setup
        )

    def _clear_provision_cache(self) -> None:
        """Drop the U1 config's per-machine provision entry so `machine setup` re-uploads rather than trusting a cached (mtime,size). The symlink's target changed, which already moves the fingerprint, but clearing is the belt-and-braces the lead asked
        for, through the config file this drill owns."""
        path = self._config_path(self.cfg)
        try:
            doc = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        state = doc.get("state")
        if isinstance(state, dict) and "renetProvision" in state:
            state.pop("renetProvision", None)
            path.write_text(json.dumps(doc, indent=2) + "\n")

    def _assert_converged(self) -> None:
        for tag in (self.tag_a, self.tag_b):
            nid = self.net_ids.get(tag)
            if not nid:
                continue
            new_sock = new_docker_socket(nid)
            old_sock = old_docker_socket(nid)
            stamp_path = runtime_stamp_path(nid)
            cmd = ("test -S %s && echo NEWSOCK; test -S %s && echo OLDSOCK; cat %s 2>/dev/null") % (
                shlex.quote(new_sock),
                shlex.quote(old_sock),
                shlex.quote(stamp_path),
            )
            res = self.probe("sudo sh -c %s" % shlex.quote(cmd))
            text = res.out + res.err
            new_present = "NEWSOCK" in text
            old_gone = "OLDSOCK" not in text
            stamp = parse_stamp(res.out)
            stamp_current = stamp_is_current(stamp, self.new_sha)
            self.ctx.check(
                STEP,
                "fork %s converged: net-%s socket present, legacy gone, stamp current" % (tag, nid),
                new_present and old_gone and stamp_current,
                res,
                evidence="new=%s old_gone=%s stamp=%s (epoch=%s pid=%s sha=%s, deployed sha %s)"
                % (
                    new_present,
                    old_gone,
                    stamp_current,
                    (stamp or {}).get("epoch"),
                    (stamp or {}).get("pid"),
                    str((stamp or {}).get("renet_sha256", ""))[:12],
                    self.new_sha[:12],
                ),
            )
            # The forks of an empty grand run no service, so this proves the daemon answers on the new socket, not that a workload survived.
            running = self.probe("sudo docker -H unix://%s ps -q" % shlex.quote(new_sock))
            self.ctx.check(
                STEP, "fork %s daemon answers on the new socket" % tag, running.rc == 0, running
            )

    def _view_rows(self, *, before: bool) -> None:
        """Fork A's dockerd against fork B's names under `RUNTIME_DIR`: before the upgrade A's daemon lists B's socket (the breach the old layout allowed), after it A lists only its own `net-<N>` (the cross-reach is gone)."""
        nid_a, nid_b = self.net_ids.get(self.tag_a), self.net_ids.get(self.tag_b)
        if not nid_a or not nid_b:
            return
        pid_file = old_docker_pid_file(nid_a) if before else new_docker_pid_file(nid_a)
        script = runtime_view_script(pid_file, allow_host_ns=before)
        res = self.probe("sudo sh -c %s" % shlex.quote(script))
        ok, evidence = runtime_view_verdict(res.out, nid_a, nid_b, expect_peer_visible=before)
        if before:
            desc = (
                "before the upgrade net-%s's dockerd lists net-%s's socket (the old-layout breach)"
                % (nid_a, nid_b)
            )
        else:
            desc = (
                "after the converge net-%s's dockerd lists its own net directory and none of net-%s's"
                % (nid_a, nid_b)
            )
        self.ctx.check(STEP, desc, ok, res, evidence=evidence)

    def _assert_dry_run_clean(self) -> None:
        res = self.crdc("machine", "converge", self.ctx.machine, "--dry-run", "--json")
        ok = res.rc == 0 and dry_run_reports_zero_stale(res.out)
        self.ctx.check(
            STEP, "a second converge --dry-run reports zero stale", ok, res, evidence=_clip(res.out)
        )

    def _teardown(self) -> None:
        left: list[str] = []
        # The deletes are renet jobs, which only the current renet runs: a run that stopped before the upgrade left the symlink on the old build.
        if self.created_cfg:
            self._point_symlink(self.new_bin)
            self._clear_provision_cache()
        if self.created_grand:
            for tag in (self.tag_b, self.tag_a):
                deleted = self.crdc("repo", "delete", "%s:%s" % (self.parent, tag), "-y")
                if deleted.rc != 0:
                    left.append(
                        "U1 fork %s:%s not deleted (rc=%d)" % (self.parent, tag, deleted.rc)
                    )
            purge = self._purge([self.guids.get(self.tag_a, ""), self.guids.get(self.tag_b, "")])
            if purge:
                left.append(purge)
            gone = self.crdc("repo", "delete", self.parent, "--archive-config", "-y")
            if gone.rc != 0:
                left.append("U1 grand %s not deleted (rc=%d)" % (self.parent, gone.rc))
        revert = self.ctx.rdc(
            "machine", "setup", self.ctx.machine, refuse=False, timeout=1800, extra_env={}
        )
        if revert.rc != 0:
            left.append(
                "worker not reverted to the dev-config renet (machine setup rc=%d: %s)"
                % (revert.rc, _clip(revert.err[-400:] or revert.out[-400:]))
            )
        self._delete_config_files(left)
        self._tmp_cleanup()
        scrub = getattr(self.ctx, "scrub", None)
        self.ctx.sweep_leftovers.extend(scrub(x) if scrub else x for x in left)

    def _purge(self, guids: Sequence[str]) -> str:
        valid = [g for g in guids if lib.is_repo_guid(g)]
        if not valid:
            return ""
        res = self.ctx.rdc(
            "term",
            "connect",
            self.ctx.machine,
            "-c",
            lib.purge_license_state_script(valid),
            refuse=False,
            extra_env=self.cfg_env(),
        )
        return (
            ""
            if res.rc == 0
            else "U1 licence state (%s) not purged (rc=%d)" % (", ".join(valid), res.rc)
        )

    def _delete_config_files(self, left: list[str]) -> None:
        if not self.created_cfg:
            return
        cfg = self._config_path(self.cfg)
        for name in config_files(cfg, self.cfg):
            try:
                if name.exists():
                    name.unlink()
            except OSError as exc:
                left.append("U1 config file %s not removed (%s)" % (name.name, exc))

    def _tmp_cleanup(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


class OldLayoutBringUp:
    """Shared by U1 and U2: a grand and its forks whose daemons run on the pre-isolation (flat) layout, brought up without a CLI job.

    Since console 87455a94f every CLI machine command is a renet job and the pre-isolation renet predates the job flags, so the CLI cannot drive it. The CLI still owns what only it can do -- the grand and the forks are created and registered (guid, network id, credential) through it while the CURRENT renet is provisioned, and the forks are NOT started. Then the old binary replaces the worker's current renet in place (`install_current_renet_script`, the slot the CLI's own provision used to overwrite) and each fork is started by the old renet's `repository up`, invoked over ssh exactly as its `repository_up` builder composed it, credential on stdin. The daemons that come up are the old binary's, on the flat layout, as under the old `fork --up`.

    Once the old binary is installed, the caller's `renetPath` symlink ends on it with its provision cache cleared (a failure before the install leaves it on the current build), so a later CLI provision (a `repo sync upload`) verifies the old binary instead of replacing it, and the upgrade step's flip to the current build is a real binary change.
    """

    def __init__(
        self,
        ctx: Any,
        *,
        step: str,
        check: Any,
        crdc: Any,
        parent: str,
        tags: Sequence[str],
        config_path: pathlib.Path,
        point_symlink: Any,
        clear_provision_cache: Any,
        old_bin: pathlib.Path,
        new_bin: pathlib.Path,
        tmp: pathlib.Path,
    ) -> None:
        self.ctx = ctx
        self.step = step
        self.check = check
        self.crdc = crdc
        self.parent = parent
        self.tags = tuple(tags)
        self.config_path = config_path
        self.point_symlink = point_symlink
        self.clear_provision_cache = clear_provision_cache
        self.old_bin = old_bin
        self.new_bin = new_bin
        self.tmp = tmp
        self.created_grand = False
        self.net_ids: dict[str, int] = {}
        self.guids: dict[str, str] = {}
        self.records: dict[str, ForkRecord] = {}

    def ssh(self, command: str) -> list[str]:
        return vm_ssh.ssh_argv(self.ctx.ssh_user, self.ctx.ssh_key, self.ctx.worker_ip, command)

    def ref(self, tag: str) -> str:
        return "%s:%s" % (self.parent, tag)

    def run(self) -> bool:
        return self._create() and self._read_ids() and self._install_old() and self._start_old()

    def _create(self) -> bool:
        self.point_symlink(self.new_bin)
        created = self.crdc(
            "repo", "create", self.parent, "-m", self.ctx.machine, "--size", "2G", timeout=1800
        )
        if not self.check(
            "create grand %s (current renet)" % self.parent, created.rc == 0, created
        ):
            return False
        self.created_grand = True
        for tag in self.tags:
            res = self.crdc("repo", "fork", self.parent, "--tag", tag, timeout=1800)
            if not self.check(
                "fork %s, not started (current renet)" % self.ref(tag), res.rc == 0, res
            ):
                return False
        return True

    def _read_ids(self) -> bool:
        try:
            doc = json.loads(self.config_path.read_text())
        except (OSError, ValueError) as exc:
            return self.check(
                "the %s config parses" % self.step, False, evidence=type(exc).__name__
            )
        for tag in self.tags:
            rec = fork_record(doc, self.parent, tag)
            if rec is not None:
                self.records[tag] = rec
                self.net_ids[tag] = rec.network_id
                self.guids[tag] = rec.guid
        return self.check(
            "every %s fork has a guid, network id, credential and grand guid in the config"
            % self.step,
            all(t in self.records for t in self.tags),
            evidence="net_ids=%s" % self.net_ids,
        )

    def _install_old(self) -> bool:
        self.point_symlink(self.old_bin)
        self.clear_provision_cache()
        staged = staged_renet_path(self.ctx.run_id, self.step)
        sent = self.ctx.host_run(
            with_stdin_from(str(self.old_bin), self.ssh("cat > %s" % shlex.quote(staged))),
            env=self.ctx.environ,
            timeout=900,
        )
        if not self.check("upload the pre-isolation renet to the worker", sent.rc == 0, sent):
            # A partial upload is removed here: only the install script's trap would otherwise clean it, and it never runs.
            cleaned = self.ctx.host_run(
                self.ssh("rm -f %s" % shlex.quote(staged)), env=self.ctx.environ, timeout=60
            )
            self.check(
                "remove the partial upload %s from the worker" % staged, cleaned.rc == 0, cleaned
            )
            return False
        script = install_current_renet_script(staged)
        res = self.ctx.host_run(
            self.ssh("sh -c %s" % shlex.quote(script)), env=self.ctx.environ, timeout=300
        )
        want = file_sha256(self.old_bin)
        got = installed_sha(res.out)
        return self.check(
            "the pre-isolation renet is the worker's current renet",
            res.rc == 0 and bool(want) and got == want,
            res,
            evidence="installed=%s built=%s" % (got[:12], want[:12]),
        )

    def _start_old(self) -> bool:
        for tag in self.tags:
            rec = self.records[tag]
            cred_file = self.tmp / ("cred-%s" % tag)
            fd = os.open(cred_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as handle:
                handle.write(rec.credential + "\n")
            try:
                command = old_repo_up_command(
                    rec.guid, rec.network_id, self.ref(tag), rec.grand_guid
                )
                res = self.ctx.host_run(
                    with_stdin_from(str(cred_file), self.ssh(command)),
                    env=self.ctx.environ,
                    timeout=1800,
                )
            finally:
                cred_file.unlink(missing_ok=True)
            if not self.check(
                "%s up through the old renet's repository up (flat layout)" % self.ref(tag),
                res.rc == 0,
                res,
            ):
                return False
        return True


def config_files(path: pathlib.Path, name: str) -> tuple[pathlib.Path, ...]:
    """Every file a throwaway config leaves beside `path`: the config, its token, and the `.bak` copy the CLI writes on each save. The copy carries the same E2E key, repo credentials and ssh keys as the config, and a teardown that skipped it left one per run in ~/.config/rediacc (found 2026-10-30, 26 of them)."""
    return (path, path.with_name("api-token-%s.json" % name), path.with_name("%s.json.bak" % name))


def _data_list(raw: str) -> list[dict[str, Any]]:
    try:
        doc = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return []
    data = doc.get("data") if isinstance(doc, dict) else doc
    if isinstance(data, dict):
        data = data.get("vms") or data.get("repositories") or data.get("machines") or []
    return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []


def file_sha256(path: pathlib.Path) -> str:
    """The sha256 of a local file, "" when it cannot be read."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def parse_stamp(text: str) -> dict[str, Any] | None:
    """The runtime stamp object in `text`, or None. renet writes `net-<N>.json` pretty-printed over several lines (`{"epoch": 1, "renet_sha256": ..., "pid": ..., "started_at": ...}`, read on ops-worker 2026-10-24), so the object is taken from the first `{` to the last `}` rather than line by line."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        doc = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return doc if isinstance(doc, dict) else None


def stamp_is_current(stamp: dict[str, Any] | None, deployed_sha: str) -> bool:
    """True when the stamp carries an epoch of at least 1, a pid, and the sha256 of the renet just deployed: a daemon the converge pass restarted under the new binary wrote it."""
    if not stamp or not deployed_sha:
        return False
    epoch = stamp.get("epoch")
    if not isinstance(epoch, int) or epoch < 1:
        return False
    if not isinstance(stamp.get("pid"), int) or stamp.get("pid", 0) <= 0:
        return False
    return stamp.get("renet_sha256") == deployed_sha


def _clip(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "..."


__all__ = [
    "DATASTORE_PATH",
    "PRE_ISOLATION_COMMIT",
    "STEP",
    "build_old_renet_script",
    "config_name",
    "dry_run_reports_zero_stale",
    "file_sha256",
    "new_docker_pid_file",
    "new_docker_socket",
    "old_docker_pid_file",
    "old_docker_socket",
    "parse_stamp",
    "peer_entries",
    "run",
    "runtime_stamp_path",
    "runtime_view_script",
    "runtime_view_verdict",
    "stamp_is_current",
]
