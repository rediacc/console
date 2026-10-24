"""U2 of agent/plans/PLAN-converge-preflight-and-repo-recovery.md (box D1): a converge pass skips a repo whose services the Docker gate would refuse, instead of restarting it into a wiped runtime.

`vm_check.py` registers this module once, through `EXTRA_RENET_STEPS`, as the `U2` step of the renet phase, after U1. The step builds the pre-isolation renet (the way U1 does), brings a grand and two forks up on it, gives one fork a compose service the gate refuses (a bind of the machine proxy root plus `cap_add: MKNOD`) and the other a clean service (the control), then runs `rdc machine setup` with the current renet, whose converge pass is the code under test. Two forks of one throwaway grand are the isolation unit; nothing here touches the run's own forks.

THE ROWS. U2.1 the refused fork is `skipped (gate_refused)` in the setup summary; U2.2 converge-last.json names it `skipped` with reason `gate_refused` and a non-empty denial list, and the control fork `converged`; U2.3 the refused fork's containers are still running with the very ids they had before the setup; U2.4 the control fork's daemon is on the per-network layout again; U2.5 `rdc repo up` on the refused fork fails and leaves its container ids unchanged (the P5 refusal before `CleanDockerRuntimeState`).

The CLI-free pieces (compose bodies, the id probe, and the parsers of the summary and of converge-last.json) are pure functions so `tests/test_drills_converge_preflight.py` pins them without a machine. The parsers read the fields P1, P3 and P4 produce (`results[].status`, `results[].reason`, a denial list, `summary.would_converge/converged/skipped`) and ignore any other field.
"""

from __future__ import annotations

import json
import pathlib
import re
import shlex
import shutil
import uuid
from typing import Any

from rediacc_ci.drills import lib, upgrade_converge, vm_ssh
from rediacc_ci.well_known import DATASTORE_PATH

STEP_ID = "U2"

MOUNTS = DATASTORE_PATH + "/mounts"
# The directory every repo dockerd sandbox sees read-only, which a repo bind of its own is refused by the gate (plan D1, context section).
PROXY_ROOT = "/opt/rediacc/proxy"
IMAGE = "busybox:1.36"
COMPOSE_FILE = "docker-compose.yml"
REASON_GATE_REFUSED = "gate_refused"
STATUS_SKIPPED = "skipped"
STATUS_CONVERGED = "converged"
ID_PREFIX = "CID:"


def config_name(run_id: str) -> str:
    """The throwaway config name for this run, e.g. `u2-10240427-94d613`."""
    return "u2-%s" % run_id


def refused_compose(service: str) -> str:
    """A service the gate refuses twice over: a bind of the proxy root and the MKNOD capability."""
    return (
        "services:\n"
        "  %(svc)s:\n"
        "    image: %(image)s\n"
        '    command: ["sleep", "86400"]\n'
        "    cap_add:\n"
        "      - MKNOD\n"
        "    volumes:\n"
        "      - %(root)s:%(root)s\n"
    ) % {"svc": service, "image": IMAGE, "root": PROXY_ROOT}


def control_compose(service: str) -> str:
    """A clean one-service compose file: nothing the gate refuses."""
    return 'services:\n  %s:\n    image: %s\n    command: ["sleep", "86400"]\n' % (service, IMAGE)


def container_ids_script(network_id: int | str) -> str:
    """Root on the worker: one `CID:<full id>` line per running container of the repo's daemon, read from the per-network socket when it exists and from the flat one otherwise (a skipped repo keeps the daemon it had); `NOSOCK` when neither answers."""
    new = shlex.quote(upgrade_converge.new_docker_socket(network_id))
    old = shlex.quote(upgrade_converge.old_docker_socket(network_id))
    return (
        'for s in %(new)s %(old)s; do if test -S "$s"; then '
        "docker -H unix://$s ps -q --no-trunc | sed 's/^/%(p)s/'; echo SOCK=$s; exit 0; fi; done; "
        "echo NOSOCK; exit 3"
    ) % {"new": new, "old": old, "p": ID_PREFIX}


def parse_container_ids(text: str) -> list[str] | None:
    """The sorted container ids `container_ids_script` printed, or None when no daemon socket answered."""
    if "NOSOCK" in text and "SOCK=" not in text.replace("NOSOCK", ""):
        return None
    if "SOCK=" not in text:
        return None
    return sorted(
        re.findall(r"^%s([0-9a-f]{12,64})\s*$" % re.escape(ID_PREFIX), text, re.MULTILINE)
    )


def parse_converge_report(text: str) -> dict[str, Any] | None:
    """The converge report in `text`, unwrapping the CLI's `{"success", "data"}` envelope, or None when `text` holds no object. converge-last.json is a bare report; `--json` output is enveloped."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        doc = json.loads(text[start : end + 1])
    except ValueError:
        return None
    if isinstance(doc, dict) and isinstance(doc.get("data"), dict):
        doc = doc["data"]
    return doc if isinstance(doc, dict) else None


def report_results(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The per-repo result objects of a report, `[]` when there are none."""
    results = (report or {}).get("results")
    return [r for r in results if isinstance(r, dict)] if isinstance(results, list) else []


def result_for(report: dict[str, Any] | None, guid: str, name: str = "") -> dict[str, Any] | None:
    """The result of the repo with `guid` (or, failing that, `name`), or None."""
    for entry in report_results(report):
        if guid and entry.get("guid") == guid:
            return entry
        if name and entry.get("name") == name:
            return entry
    return None


def result_denials(entry: dict[str, Any] | None) -> list[str]:
    """The denial list of a result as strings. An element may be a plain message or an object (`service`, `field`, `tier`, `message`); either reads as one line."""
    raw = (entry or {}).get("denials")
    if not isinstance(raw, list):
        return []
    lines: list[str] = []
    for item in raw:
        if isinstance(item, str):
            lines.append(item)
        elif isinstance(item, dict):
            parts = [str(item[k]) for k in ("service", "field", "tier", "message") if item.get(k)]
            lines.append(" ".join(parts) or json.dumps(item, sort_keys=True))
    return [x for x in lines if x]


def is_gate_refused(entry: dict[str, Any] | None) -> bool:
    """True for a result that is `skipped` with reason `gate_refused` and names at least one denial."""
    return (
        bool(entry)
        and (entry or {}).get("status") == STATUS_SKIPPED
        and (entry or {}).get("reason") == REASON_GATE_REFUSED
        and bool(result_denials(entry))
    )


def is_converged(entry: dict[str, Any] | None) -> bool:
    """True for a result whose status is `converged`."""
    return bool(entry) and (entry or {}).get("status") == STATUS_CONVERGED


def summary_counts(report: dict[str, Any] | None) -> dict[str, int]:
    """The integer counts of the report's summary (`total`, `would_converge`, `converged`, `skipped`, `failed`, `pending`), missing or non-integer ones left out."""
    summary = (report or {}).get("summary")
    if not isinstance(summary, dict):
        return {}
    return {k: v for k, v in summary.items() if isinstance(v, int) and not isinstance(v, bool)}


def summary_skips_refused(text: str, *names: str) -> bool:
    """True when a line of the CLI's setup summary reads `skipped (gate_refused)` and names one of `names` (the fork's name, tag or guid). The line shape is the P4 renderer's; only the two facts are matched."""
    wanted = [n for n in names if n]
    for line in text.splitlines():
        low = line.lower()
        if STATUS_SKIPPED in low and REASON_GATE_REFUSED in low and any(n in line for n in wanted):
            return True
    return False


def ids_unchanged(before: list[str] | None, after: list[str] | None) -> bool:
    """True when both id lists exist, are non-empty and equal (the containers were neither restarted nor recreated)."""
    return bool(before) and before == after


# --------------------------------------------------------------------------- live


def run(ctx: Any) -> None:
    """The live U2 step. Records U2 rows on `ctx`; cleans up its forks, grand and config, and appends any leftover to `ctx.sweep_leftovers`."""
    _LiveU2(ctx).execute()


class _LiveU2:
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.cfg = config_name(ctx.run_id)
        self.parent = "u2base-%s" % ctx.run_id[-6:]
        self.tag_r = "u2r"
        self.tag_c = "u2c"
        self.svc_r = "u2-refused-%s" % ctx.run_id[-6:]
        self.svc_c = "u2-control-%s" % ctx.run_id[-6:]
        self.tmp = pathlib.Path(ctx.work) / ("u2-%s" % ctx.run_id)
        self.old_bin = self.tmp / "renet-old"
        self.new_bin = self.tmp / "renet-new"
        self.symlink = self.tmp / "renet"
        self.src_old = self.tmp / "src-old"
        self.created_cfg = False
        self.created_grand = False
        self.net_ids: dict[str, int] = {}
        self.guids: dict[str, str] = {}
        self.before_ids: dict[str, list[str] | None] = {}

    # -- helpers ---------------------------------------------------------------

    def check(self, desc: str, ok: bool, res: Any = None, evidence: str = "") -> bool:
        return self.ctx.check(STEP_ID, desc, ok, res, evidence)

    def ref(self, tag: str) -> str:
        return "%s:%s" % (self.parent, tag)

    def cfg_env(self) -> dict[str, str]:
        """Select the throwaway config; RDC_DEV is cleared so `./rdc.sh` does not re-select the dev config over it."""
        return {"REDIACC_CONFIG": self.cfg, "RDC_DEV": ""}

    def crdc(self, *args: str, timeout: float | None = None, refuse: bool = False) -> Any:
        return self.ctx.rdc(*args, timeout=timeout, refuse=refuse, extra_env=self.cfg_env())

    def root(self, command: str, timeout: float = 60.0) -> Any:
        argv = vm_ssh.ssh_argv(
            self.ctx.ssh_user,
            self.ctx.ssh_key,
            self.ctx.worker_ip,
            "sudo sh -c %s" % shlex.quote(command),
        )
        return self.ctx.host_run(argv, env=self.ctx.environ, timeout=timeout)

    def container_ids(self, tag: str) -> list[str] | None:
        nid = self.net_ids.get(tag)
        if not nid:
            return None
        res = self.root(container_ids_script(nid))
        return parse_container_ids(res.out + res.err)

    def mount(self, tag: str) -> str:
        return "%s/%s" % (MOUNTS, self.guids.get(tag, "<unknown>"))

    def config_path(self, name: str) -> pathlib.Path:
        base = pathlib.Path.home() / ".config" / "rediacc"
        return base / ("%s.json" % name)

    def point_symlink(self, target: pathlib.Path) -> None:
        if self.symlink.is_symlink() or self.symlink.exists():
            self.symlink.unlink()
        self.symlink.symlink_to(target)

    # -- the run ---------------------------------------------------------------

    def execute(self) -> None:
        try:
            if not (self._build_renets() and self._make_config() and self._bring_up_old()):
                return
            if not self._deploy_services():
                return
            if not self._setup_with_branch_renet():
                return
            self._assert_after_setup()
            self._assert_repo_up_refused()
        finally:
            self._teardown()

    def _build_renets(self) -> bool:
        self.tmp.mkdir(parents=True, exist_ok=True)
        resolved = self.ctx.host_run(
            ["git", "-C", "private/renet", "rev-parse", upgrade_converge.PRE_ISOLATION_COMMIT],
            env=self.ctx.environ,
            timeout=60,
        )
        if not self.check(
            "resolve the pre-isolation commit",
            resolved.rc == 0 and bool(resolved.out.strip()),
            resolved,
        ):
            return False
        sha = resolved.out.strip()
        script = upgrade_converge.build_old_renet_script(str(self.src_old), str(self.old_bin), sha)
        built = self.ctx.host_run(["bash", "-c", script], env=self.ctx.environ, timeout=1800)
        if not self.check("build the pre-isolation renet (%s)" % sha[:12], built.rc == 0, built):
            return False
        copied = self.ctx.host_run(
            ["cp", str(self.ctx.renet_bin), str(self.new_bin)], env=self.ctx.environ, timeout=120
        )
        return self.check("stage the current renet build", copied.rc == 0, copied)

    def _make_config(self) -> bool:
        """A copy of the dev config this run seeded, with `renetPath` on a symlink that starts at the OLD binary and a fresh identity."""
        self.point_symlink(self.old_bin)
        dev_json = self.config_path("dev")
        if not dev_json.exists():
            self.check(
                "the dev config exists to seed the U2 config from",
                False,
                evidence="no %s" % dev_json,
            )
            return False
        doc = json.loads(dev_json.read_text())
        doc["renetPath"] = str(self.symlink)
        doc["id"] = str(uuid.uuid4())
        target = self.config_path(self.cfg)
        target.write_text(json.dumps(doc, indent=2) + "\n")
        target.chmod(0o600)
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
        return self.check(
            "U2 config %s created with renetPath -> old renet" % self.cfg,
            target.exists(),
            evidence="renetPath=%s" % self.symlink,
        )

    def _bring_up_old(self) -> bool:
        created = self.crdc(
            "repo", "create", self.parent, "-m", self.ctx.machine, "--size", "2G", timeout=1800
        )
        if not self.check(
            "create grand %s under old renet" % self.parent, created.rc == 0, created
        ):
            return False
        self.created_grand = True
        for tag in (self.tag_r, self.tag_c):
            res = self.crdc("repo", "fork", self.parent, "--tag", tag, "--up", timeout=1800)
            if not self.check("fork %s --up (old renet)" % self.ref(tag), res.rc == 0, res):
                return False
        listed = self.crdc("repo", "list", "-m", self.ctx.machine, "-o", "json")
        for entry in _data_list(listed.out) if listed.rc == 0 else []:
            for tag in (self.tag_r, self.tag_c):
                if entry.get("name") == self.ref(tag):
                    nid = entry.get("networkId", entry.get("network_id"))
                    if nid is not None:
                        self.net_ids[tag] = int(nid)
                    self.guids[tag] = str(entry.get("guid", ""))
        return self.check(
            "both U2 forks have a network id and guid",
            all(self.net_ids.get(t) and self.guids.get(t) for t in (self.tag_r, self.tag_c)),
            evidence="net_ids=%s" % self.net_ids,
        )

    def _deploy_services(self) -> bool:
        """The old renet has no gate, so both compose files come up; the refused one is what the new gate would refuse."""
        for tag, body in (
            (self.tag_r, refused_compose(self.svc_r)),
            (self.tag_c, control_compose(self.svc_c)),
        ):
            up = self.tmp / ("up-" + tag)
            up.mkdir(parents=True, exist_ok=True)
            (up / COMPOSE_FILE).write_text(body)
            sent = self.crdc(
                "repo", "sync", "upload", self.ref(tag), "--local", str(up) + "/", timeout=900
            )
            if not self.check("%s: compose file uploaded" % self.ref(tag), sent.rc == 0, sent):
                return False
            started = self.crdc(
                "term",
                "connect",
                self.ref(tag),
                "-c",
                "cd %s && renet compose -- up -d" % shlex.quote(self.mount(tag)),
                timeout=900,
            )
            if not self.check(
                "%s: renet compose -- up -d (old renet)" % self.ref(tag), started.rc == 0, started
            ):
                return False
            self.before_ids[tag] = self.container_ids(tag)
        return self.check(
            "both forks run a container before the upgrade",
            all(self.before_ids.get(t) for t in (self.tag_r, self.tag_c)),
            evidence="ids=%s" % {t: len(v or []) for t, v in self.before_ids.items()},
        )

    def _setup_with_branch_renet(self) -> bool:
        """Point the symlink at the current renet and run `rdc machine setup`: the provision upload, then the converge pass whose preflight is under test. The summary is read from the setup's own output."""
        self.point_symlink(self.new_bin)
        self._clear_provision_cache()
        setup = self.crdc("machine", "setup", self.ctx.machine, timeout=1800)
        if not self.check("rdc machine setup uploads the current renet", setup.rc == 0, setup):
            return False
        text = setup.out + "\n" + setup.err
        # A missing summary line is a FAIL row, but the later rows still read the machine's facts.
        self.check(
            "U2.1 the setup summary lists the refused fork as skipped (gate_refused)",
            summary_skips_refused(text, self.ref(self.tag_r), self.tag_r, self.guids[self.tag_r]),
            setup,
            evidence=_clip(text),
        )
        return True

    def _clear_provision_cache(self) -> None:
        path = self.config_path(self.cfg)
        try:
            doc = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        state = doc.get("state")
        if isinstance(state, dict) and "renetProvision" in state:
            state.pop("renetProvision", None)
            path.write_text(json.dumps(doc, indent=2) + "\n")

    def _assert_after_setup(self) -> None:
        last = self.root(
            "cat %s/converge-last.json" % shlex.quote(upgrade_converge.RUNTIME_STATE_DIR)
        )
        report = parse_converge_report(last.out) if last.rc == 0 else None
        refused = result_for(report, self.guids[self.tag_r], self.ref(self.tag_r))
        control = result_for(report, self.guids[self.tag_c], self.ref(self.tag_c))
        self.check(
            "U2.2 converge-last.json: refused fork skipped with reason gate_refused and its denials",
            is_gate_refused(refused),
            last,
            evidence="entry=%s counts=%s" % (_clip(json.dumps(refused)), summary_counts(report)),
        )
        self.check(
            "U2.2 converge-last.json: the control fork converged",
            is_converged(control),
            last,
            evidence="entry=%s" % _clip(json.dumps(control)),
        )
        after = self.container_ids(self.tag_r)
        self.check(
            "U2.3 the refused fork's containers still run with unchanged ids",
            ids_unchanged(self.before_ids.get(self.tag_r), after),
            evidence="before=%s after=%s" % (self.before_ids.get(self.tag_r), after),
        )
        nid = self.net_ids[self.tag_c]
        sock = self.root(
            "test -S %s && echo NEWSOCK" % shlex.quote(upgrade_converge.new_docker_socket(nid))
        )
        self.check(
            "U2.4 the control fork's daemon serves the per-network socket (net-%s)" % nid,
            "NEWSOCK" in sock.out,
            sock,
        )

    def _assert_repo_up_refused(self) -> None:
        """P5: `repo up` on the refused fork fails with the denial list before it touches a container."""
        before = self.container_ids(self.tag_r)
        res = self.crdc("repo", "up", self.ref(self.tag_r), timeout=900)
        after = self.container_ids(self.tag_r)
        self.check(
            "U2.5 repo up on the refused fork fails and leaves its container ids unchanged",
            res.rc != 0 and ids_unchanged(before, after),
            res,
            evidence="rc=%d before=%s after=%s" % (res.rc, before, after),
        )

    def _teardown(self) -> None:
        left: list[str] = []
        if self.created_grand:
            for tag in (self.tag_c, self.tag_r):
                # The refused fork's service is down first so the delete cannot meet a running gate-refused container.
                self.crdc(
                    "term",
                    "connect",
                    self.ref(tag),
                    "-c",
                    "cd %s && renet compose -- down" % shlex.quote(self.mount(tag)),
                )
                self.crdc("repo", "delete", self.ref(tag), "-y")
            valid = [g for g in self.guids.values() if lib.is_repo_guid(g)]
            if valid:
                purge = self.ctx.rdc(
                    "term",
                    "connect",
                    self.ctx.machine,
                    "-c",
                    lib.purge_license_state_script(valid),
                    refuse=False,
                    extra_env=self.cfg_env(),
                )
                if purge.rc != 0:
                    left.append(
                        "U2 licence state (%s) not purged (rc=%d)" % (", ".join(valid), purge.rc)
                    )
            gone = self.crdc("repo", "delete", self.parent, "--archive-config", "-y")
            if gone.rc != 0:
                left.append("U2 grand %s not deleted (rc=%d)" % (self.parent, gone.rc))
        revert = self.ctx.rdc(
            "machine", "setup", self.ctx.machine, refuse=False, timeout=1800, extra_env={}
        )
        if revert.rc != 0:
            left.append(
                "worker not reverted to the dev-config renet (machine setup rc=%d)" % revert.rc
            )
        if self.created_cfg:
            token = self.config_path(self.cfg).with_name("api-token-%s.json" % self.cfg)
            for name in (self.config_path(self.cfg), token):
                try:
                    if name.exists():
                        name.unlink()
                except OSError as exc:
                    left.append("U2 config file %s not removed (%s)" % (name.name, exc))
        shutil.rmtree(self.tmp, ignore_errors=True)
        scrub = getattr(self.ctx, "scrub", None)
        self.ctx.sweep_leftovers.extend(scrub(x) if scrub else x for x in left)


def _data_list(raw: str) -> list[dict[str, Any]]:
    try:
        doc = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return []
    data = doc.get("data") if isinstance(doc, dict) else doc
    if isinstance(data, dict):
        data = data.get("vms") or data.get("repositories") or data.get("machines") or []
    return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []


def _clip(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "..."


# The registration entry vm_check's EXTRA_RENET_STEPS takes: (step id, the steps `--only` drags in, the live function). U2 builds its own grand and forks, so it needs only the infra chain.
STEP = (STEP_ID, (), run)

__all__ = [
    "STEP",
    "STEP_ID",
    "config_name",
    "container_ids_script",
    "control_compose",
    "ids_unchanged",
    "is_converged",
    "is_gate_refused",
    "parse_container_ids",
    "parse_converge_report",
    "refused_compose",
    "report_results",
    "result_denials",
    "result_for",
    "run",
    "summary_counts",
    "summary_skips_refused",
]
