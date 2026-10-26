"""Differential: `.ci/rediacc_ci/private/license_e2e.py` against the frozen output of its retired twin `.ci/scripts/private/license-e2e.sh`.

THE TWIN HAS BEEN DELETED. Every case compares the port with `goldens/twins/private.license-e2e.jsonl`, which holds the twin's OWN recorded bytes (the header carries the blob sha, so `git cat-file -p <sha>` still yields the program).

NOTHING REAL IS EVER TOUCHED. The battery needs `go`, passwordless `sudo`, a built renet and `/var/lib/rediacc`, so every external is a recording fake on a PATH rebuilt from scratch: `go` (records its argv, and "builds" a fake minter or a fake renet), `sudo` (records its argv, strips `-n`, maps `/var/lib/rediacc/...` into a scratch tree and execs the real `rm`/`mkdir`/`cp`/`chmod`), the minter (writes a JSON blob recording what it was asked to forge) and renet (a small licence model: signer against baked key, delegation cert, expiry tiers, machine grace, datastore identity, per-repo chain state). The fakes are a model of the licence rules, not of renet: they exist so the scenario table, the control binaries and the bookkeeping around them are driven end to end.

WHAT IS COMPARED, per case: the exit code, stdout, stderr, the CALL LOG (every go, sudo, mint and renet invocation, in order) and the STATE LEFT BEHIND (the scratch licence tree, the chain-state contents, the leftover scratch directories). The state matters because cleanup is half of what the script does.

THE HOST PRECONDITION. The twin tests `/var/lib/rediacc/license` and its `chain-state.json` on the REAL filesystem before anything else, so the recording host must have both (`REDIACC_CI_REGOLDEN=bash` fails loudly otherwise); every golden was taken with the store PRE-EXISTING and a chain state present. The port is pointed at a scratch tree that models the same state (`run(..., license_root=...)`). The other branch (no store yet) is covered by direct tests of `Battery.cleanup` below.

WHAT IS MASKED: the random scratch directory name (`license-e2e.XXXXXX`) as `license-e2e.WORK`, the fixture root as `<root>`, the test scratch as `<tmp>`, the scratch licence tree as `/var/lib/rediacc`, and bash's `<$0>: line <n>: ` prefix.

RULE T DELTAS (each has a test below that fails on the bash behaviour; the goldens for those cases were re-recorded from the port with `intentional`):
  1. a failed preflight no longer runs `sudo rm -rf /var/lib/rediacc/license`;
  2. `jq` is no longer required;
  3. a failed chain-state restore is reported.
"""

import hashlib
import itertools
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from typing import Any

import pytest

from rediacc_ci import paths
from rediacc_ci.private import license_e2e as port_module
from rediacc_ci.tests import differential as diff

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "private" / "license-e2e.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "private" / "license_e2e.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/private/license-e2e.sh")
TWIN_STR = str(TWIN_REL)
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/private/license_e2e.py")

_SERIAL = itertools.count()

HOST_LICENSE_ROOT = pathlib.Path("/var/lib/rediacc/license")

pytestmark = pytest.mark.skipif(
    os.geteuid() == 0, reason="as root the script runs without sudo, which the goldens do not hold"
)

# The shared body of every fake. A wrapper script sets ROLE, PARAMS and CFG_PATH, then execs this file's text.
FAKES = r"""
import json, os, pathlib, sys

CFG = json.load(open(CFG_PATH))
SCRATCH = CFG["scratch"]
LIC = SCRATCH + "/var/lib/rediacc/license"
ATTR = "Licensed to: license-e2e@rediacc.invalid"
TAIL = {"create": "--password-stdin is required", "up": "no password or keyfile provided"}


def log(*parts):
    with open(CFG["log"], "a", encoding="utf-8") as fh:
        fh.write("\t".join(str(p) for p in parts) + "\n")


def counter(name):
    path = pathlib.Path(CFG["state_dir"]) / name
    n = int(path.read_text()) if path.exists() else 0
    path.write_text(str(n + 1))
    return n


def write_wrapper(out, role, params):
    pathlib.Path(out).write_text(
        "#!/usr/bin/env python3\nROLE = %r\nPARAMS = %r\nCFG_PATH = %r\nexec(open(%r).read())\n"
        % (role, params, CFG_PATH, FAKES_PATH)
    )
    os.chmod(out, 0o755)


def back(arg):
    return arg.replace(SCRATCH + "/var/lib/rediacc", "/var/lib/rediacc")


args = sys.argv[1:]

if ROLE == "go":
    log("go", os.path.relpath(os.getcwd(), CFG["tree"]), *args)
    if args[:2] == ["env", "GOARCH"]:
        print(CFG.get("goarch", "amd64"))
        sys.exit(CFG.get("goarch_rc", 0))
    if args[:1] == ["build"]:
        out = args[args.index("-o") + 1]
        kind = "mint" if os.getcwd().endswith("license-mint") else "renet"
        if kind in CFG.get("build_fail", {}):
            sys.stderr.write("go build: %s failed\n" % kind)
            sys.exit(CFG["build_fail"][kind])
        if kind == "mint":
            write_wrapper(out, "mint", {})
        else:
            n = counter("renet-builds")
            label = "nolicense" if "-tags" in args else ("enforcing" if n == 0 else "wrong-key")
            pub = args[args.index("-ldflags") + 1].split("=", 1)[1]
            write_wrapper(out, "renet", {"label": label, "pub": pub})
        sys.exit(0)
    sys.exit(2)

if ROLE == "sudo":
    shown = [back(a) for a in args]
    log("sudo", *shown)
    cmd = args[1:] if args[:1] == ["-n"] else args
    if CFG.get("no_sudo") and cmd[:1] == ["true"]:
        sys.exit(1)
    fail = CFG.get("sudo_fail")
    if fail and cmd and cmd[0] == fail["cmd"] and fail["contains"] in " ".join(back(a) for a in cmd):
        sys.exit(fail["rc"])
    mapped = [SCRATCH + a if a.startswith("/var/lib/rediacc") else a for a in cmd]
    os.execvp(mapped[0], mapped)

if ROLE == "mint":
    log("mint", *args)
    if args == ["-gen-key"]:
        if CFG.get("gen_fail"):
            sys.exit(4)
        n = counter("gen")
        print(json.dumps({"public": "PUB-%d" % (n + 1), "private": "PRIV-%d" % (n + 1)}))
        sys.exit(0)
    opts, i = {}, 0
    while i < len(args):
        if args[i] in ("-delegate", "-chain-hash"):
            opts[args[i]] = True
            i += 1
        else:
            opts[args[i]] = args[i + 1]
            i += 2
    priv = opts["-master-key"]
    repo = opts["-repo"]
    if CFG.get("mint_fail_repo") == repo:
        sys.exit(3)
    keyid = "KID-" + priv
    blob = {
        "repo": repo,
        "signer_pub": opts.get("-forge-signer", priv).replace("PRIV", "PUB"),
        "master_pub": priv.replace("PRIV", "PUB"),
        "opts": opts,
    }
    outdir = pathlib.Path(opts["-out-dir"])
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / (opts.get("-key-id", keyid) + ".json")).write_text(json.dumps(blob))
    print(json.dumps({"publicKeyId": keyid}))
    sys.exit(0)

if ROLE == "renet":
    label, baked = PARAMS["label"], PARAMS["pub"]
    log("renet", label, *args)
    bug = CFG.get("bug", {}).get(label)

    def opt(name):
        return args[args.index(name) + 1] if name in args else None

    def load(dirpath):
        p = pathlib.Path(dirpath)
        files = sorted(p.glob("*.json")) if p.is_dir() else []
        return json.loads(files[0].read_text()) if files else None

    def reason(blob, op, ds_id=None):
        o = blob["opts"]
        if blob["signer_pub"] != baked and bug != "accept-forged":
            return "invalid_signature"
        if "-delegate" in o and "-cert-signer" in o:
            if o["-cert-signer"].replace("PRIV", "PUB") != blob["master_pub"]:
                return "cert_invalid"
        if op != "up":
            if o.get("-cert-valid-until", "").startswith("-"):
                return "cert_expired"
            if o.get("-hard-expires", "").startswith("-"):
                return "expired"
        if "-machine" in o and int(o.get("-issued-at", "0h").rstrip("h")) <= -960:
            return "machine_mismatch"
        if op == "status":
            if "-datastore-id" in o and o["-datastore-id"] != ds_id:
                return "identity_mismatch"
            if o.get("-storage-fingerprint") == "dir:1:2:3":
                return "identity_mismatch"
        return None

    if args[:2] in (["repository", "create"], ["repository", "up"]):
        op = args[1]
        if label == "nolicense" and bug != "enforce":
            sys.stderr.write(TAIL[op] + "\n")
            sys.exit(1)
        blob = load(LIC + "/repos/" + opt("--name"))
        why = "missing" if blob is None else reason(blob, op)
        if why:
            sys.stderr.write(json.dumps({"code": "LICENSE_REQUIRED", "reason": why}, separators=(",", ":")) + "\n")
            sys.exit(10)
        sys.stderr.write(ATTR + "\n" + TAIL[op] + "\n")
        sys.exit(1)

    if args[:2] == ["backup", "restore"]:
        blob = load(LIC + "/repos/" + opt("--repo"))
        if blob is None:
            sys.stderr.write(json.dumps({"code": "LICENSE_REQUIRED", "reason": "missing"}, separators=(",", ":")) + "\n")
            sys.exit(10)
        if (blob.get("opts") or {}).get("-grand-guid") != opt("--lineage"):
            print("repository %s belongs to lineage %s" % (opt("--repo"), (blob.get("opts") or {}).get("-grand-guid", "(none)")))
            sys.stderr.write("restore refused\n")
            sys.exit(1)
        sys.exit(1)

    if args[:2] == ["repository", "license-status"]:
        ds = opt("--datastore")
        guid = sorted(os.listdir(ds + "/repositories"))[0]
        desc = ds + "/.rediacc/datastore.json"
        ds_id = json.load(open(desc))["datastoreId"] if os.path.exists(desc) else None
        if label == "nolicense" and bug != "enforce":
            status = "valid"
        else:
            where = LIC + ("/datastores/%s/repos/%s" % (ds_id, guid) if ds_id else "/repos/" + guid)
            blob = load(where)
            status = "missing" if blob is None else reason(blob, "status", ds_id)
            if blob is not None and not status:
                o = blob["opts"]
                status = "valid"
                if "-chain-hash" in o:
                    state_path = pathlib.Path(LIC + "/chain-state.json")
                    state = json.loads(state_path.read_text()) if state_path.exists() else {}
                    seq = int(o.get("-sequence", 1))
                    if seq < state.get(guid, 0):
                        status = "sequence_regression"
                    else:
                        state[guid] = seq
                        state_path.write_text(json.dumps(state, sort_keys=True))
        print(json.dumps([{"repositoryGuid": guid, "status": status}]))
        sys.exit(0)
    sys.exit(2)
"""

NEEDED = (
    "bash",
    "sh",
    "python3",
    "env",
    "uname",
    "dirname",
    "basename",
    "cat",
    "grep",
    "sed",
    "head",
    "tr",
    "rm",
    "mkdir",
    "cp",
    "chmod",
    "touch",
    "mktemp",
    "ls",
    "true",
    "jq",
)

# Collapses the random suffix of the scratch directory, whichever length the implementation draws.
WORK_RE = re.compile(r"license-e2e\.[A-Za-z0-9_]+")
SHELL_PREFIX = re.compile(r"^[^\n]*?: line \d+: ", re.MULTILINE)


# Cleanup's `rm -rf "<repos>/license-e2e"-* ...`: the twin lets BASH expand the glob against the host's REAL `/var/lib/rediacc/license/repos`, where nothing matches, so it passes the literal pattern; the port expands it against the scratch tree the fakes write into, where the battery's own directories are. In real use both see one filesystem, so the expansion is collapsed to the pattern on both sides.
CLEANUP_GLOB = re.compile(
    r"(sudo\t-n\trm\t-rf\t)(?:/var/lib/rediacc/license/repos/license-e2e-[\w*-]+\t)+"
    r"(?=/var/lib/rediacc/license/repos/1ce1ce2e-0000-0000-0000-000000000001)"
)


def _mask(text: str, root: pathlib.Path, tmp: pathlib.Path) -> str:
    text = CLEANUP_GLOB.sub(r"\1/var/lib/rediacc/license/repos/license-e2e-*\t", text)
    text = text.replace(str(tmp / "scratch" / "var" / "lib" / "rediacc"), "/var/lib/rediacc")
    text = SHELL_PREFIX.sub("<shell>: ", text)
    text = text.replace(str(root), "<root>").replace(str(tmp), "<tmp>")
    return WORK_RE.sub("license-e2e.WORK", text)


def _recording() -> bool:
    """True only while the twin's bytes are being recorded (`REDIACC_CI_REGOLDEN=bash`)."""
    return diff.regolden_mode(TWIN_STR) == "bash"


CHAIN_STATE_BODY = '{"pre-existing": 1}'


def _fixture(tmp_path: pathlib.Path, cfg: dict) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of the subjects, plus the fakes' state."""
    base = tmp_path.resolve()
    root = base / "tree"
    (root / ".ci" / "scripts" / "private" / "license-mint").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "private").mkdir(parents=True)
    (root / ".ci" / "config").mkdir(parents=True)
    if _recording():
        shutil.copy2(TWIN, root / TWIN_REL)
    for name in ("well-known.env", "well-known.generated.sh"):
        shutil.copy2(ROOT / ".ci" / "config" / name, root / ".ci" / "config" / name)
    shutil.copy2(PORT, root / PORT_REL)
    if not cfg.get("no_assets"):
        (root / "private" / "renet" / "pkg" / "embed" / "assets" / "amd64" / "base").mkdir(
            parents=True
        )

    # The scratch licence tree the fakes (and the port) see as `/var/lib/rediacc`: the PRE-EXISTING store, with a chain state.
    lic = base / "scratch" / "var" / "lib" / "rediacc" / "license"
    lic.mkdir(parents=True)
    (lic / "chain-state.json").write_text(CHAIN_STATE_BODY)
    (base / "tmp").mkdir()
    (base / "fakestate").mkdir()
    (base / "elsewhere").mkdir()

    full = {
        "tree": str(root),
        "scratch": str(base / "scratch"),
        "log": str(base / "calls.log"),
        "state_dir": str(base / "fakestate"),
        **cfg,
    }
    (base / "fakes.json").write_text(json.dumps(full))
    (base / "fakes.py").write_text(FAKES)
    return root


def _binder(tmp_path: pathlib.Path, *, tools: tuple[str, ...] = NEEDED, go: bool = True) -> str:
    """The COMPLETE PATH for one case: named real tools plus the recording `go` and `sudo`."""
    base = tmp_path.resolve()
    binder = base / "bin"
    binder.mkdir(exist_ok=True)
    for tool in tools:
        target = shutil.which(tool)
        if target is not None and not (binder / tool).exists():
            (binder / tool).symlink_to(target)
    names = ["sudo", "go"] if go else ["sudo"]
    for name in names:
        (binder / name).write_text(
            "#!/usr/bin/env python3\nROLE = %r\nPARAMS = {}\nCFG_PATH = %r\nFAKES_PATH = %r\n"
            "exec(open(FAKES_PATH).read())\n"
            % (name, str(base / "fakes.json"), str(base / "fakes.py"))
        )
        (binder / name).chmod(0o755)
    assert shutil.which("bash", path=str(binder))
    assert shutil.which("python3", path=str(binder))
    return str(binder)


LAUNCHER = """\
import importlib.util, sys
spec = importlib.util.spec_from_file_location("license_e2e_copy", %(copy)r)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sys.exit(module.run(sys.argv[1:], license_root=%(lic)r))
"""


def _run(
    subject: pathlib.PurePosixPath,
    root: pathlib.Path,
    tmp_path: pathlib.Path,
    binder: str,
    *,
    argv: tuple[str, ...] = (),
    env_extra: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Drive one subject from a NEUTRAL cwd and collect every observable."""
    base = tmp_path.resolve()
    env = {
        "PATH": binder,
        "HOME": str(base),
        "TMPDIR": str(base / "tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(ROOT / ".ci"),
    }
    env.update(env_extra or {})
    if subject.suffix == ".sh":
        cmd = ["bash", str(root / subject), *argv]
    else:
        lic = base / "scratch" / "var" / "lib" / "rediacc" / "license"
        launcher = base / "launcher.py"
        launcher.write_text(LAUNCHER % {"copy": str(root / subject), "lic": str(lic)})
        cmd = [sys.executable, str(launcher), *argv]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        errors="backslashreplace",
        env=env,
        cwd=str(base / "elsewhere"),
        check=False,
        timeout=600,
    )
    log_path = base / "calls.log"
    calls = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
    lic = base / "scratch" / "var" / "lib" / "rediacc" / "license"
    # The `repos/license-e2e-*` directories are left out for the reason `CLEANUP_GLOB` gives: whether they survive depends on which filesystem the glob was expanded against, which is a property of the harness. `test_cleanup_*` below covers their removal directly.
    tree = sorted(
        "%s%s" % (p.relative_to(lic), "/" if p.is_dir() else "")
        for p in lic.rglob("*")
        if not str(p.relative_to(lic)).startswith("repos/" + port_module.REPO_PREFIX + "-")
    )
    chain = (lic / "chain-state.json").read_text() if (lic / "chain-state.json").exists() else None
    state = {
        "tree": tree,
        "chain": chain,
        "leftover": sorted(p.name for p in (base / "tmp").iterdir()),
    }
    return {
        "exit": proc.returncode,
        "stdout": _mask(proc.stdout, root, base),
        "stderr": _mask(proc.stderr, root, base),
        "calls": [_mask(line, root, base) for line in calls],
        "state": _mask(json.dumps(state, indent=1), root, base),
    }


def _case_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path


def _answer(
    tmp_path: pathlib.Path,
    name: str,
    cfg: dict,
    *,
    subject: pathlib.PurePosixPath = PORT_REL,
    binder_kw: dict | None = None,
    run_kw: dict | None = None,
) -> dict[str, Any]:
    """One subject over its own fixture. The twin's answer is recorded while recording and read from the golden otherwise."""
    run_kw = run_kw or {}

    def drive(which: pathlib.PurePosixPath) -> dict[str, Any]:
        # Each driven subject gets its OWN fixture directory: the twin and the port must not see each other's leftovers.
        sub = tmp_path / ("%s-%d" % (which.name, next(_SERIAL)))
        sub.mkdir()
        root = _fixture(sub, cfg)
        binder = _binder(sub, **(binder_kw or {}))
        return _run(which, root, sub, binder, **run_kw)

    if subject == PORT_REL:
        return drive(PORT_REL)

    seen: dict[str, dict[str, Any]] = {}

    def record(which: pathlib.PurePosixPath):
        def go() -> tuple[int, str, str]:
            if _recording() and not (
                HOST_LICENSE_ROOT.is_dir() and (HOST_LICENSE_ROOT / "chain-state.json").is_file()
            ):
                raise AssertionError(
                    "recording needs a pre-existing %s with a chain-state.json on this host"
                    % HOST_LICENSE_ROOT
                )
            out = drive(which)
            seen["out"] = out
            return out["exit"], out["stdout"], out["stderr"]

        return go

    rc, out, err, frozen = diff.twin_run(
        TWIN_STR,
        [name],
        record(TWIN_REL),
        port=record(PORT_REL),
        extras={
            "calls": lambda: "\n".join(seen["out"]["calls"]),
            "state": lambda: seen["out"]["state"],
        },
    )
    return {
        "exit": rc,
        "stdout": out,
        "stderr": err,
        "calls": [line for line in frozen["calls"].split("\n") if line],
        "state": frozen["state"],
    }


# name -> (fakes cfg, binder kwargs, run kwargs)
CASES: dict[str, tuple[dict, dict, dict]] = {
    "happy-path-both-controls-fail": ({}, {}, {}),
    "arguments-are-ignored": ({}, {}, {"argv": ("--unexpected", "x")}),
    "caller-supplied-master-key": (
        {},
        {},
        {"env_extra": {"LICENSE_E2E_MASTER_PUB": "PUB-M", "LICENSE_E2E_MASTER_PRIV": "PRIV-M"}},
    ),
    "only-one-half-of-the-supplied-key-is-ignored": (
        {},
        {},
        {"env_extra": {"LICENSE_E2E_MASTER_PUB": "PUB-M"}},
    ),
    "enforcing-binary-accepts-a-forged-license": ({"bug": {"enforcing": "accept-forged"}}, {}, {}),
    "nolicense-control-fails-at-the-wrong-scenario": ({"bug": {"nolicense": "enforce"}}, {}, {}),
    "wrong-key-control-fails-at-the-wrong-scenario": (
        {"bug": {"wrong-key": "accept-forged"}},
        {},
        {},
    ),
    "a-fixture-install-failing-inside-the-battery-is-ignored": (
        {"sudo_fail": {"cmd": "cp", "contains": "0000-000000000001", "rc": 5}},
        {},
        {},
    ),
    "a-fixture-install-failing-before-the-battery-is-fatal": (
        {"sudo_fail": {"cmd": "cp", "contains": "license-e2e-delegated", "rc": 5}},
        {},
        {},
    ),
    "go-is-not-installed": ({}, {"go": False}, {}),
    "embedded-assets-are-missing": ({"no_assets": True}, {}, {}),
    "passwordless-sudo-is-unavailable": ({"no_sudo": True}, {}, {}),
    "jq-is-not-installed": ({}, {"tools": tuple(t for t in NEEDED if t != "jq")}, {}),
    "license-mint-fails-to-build": ({"build_fail": {"mint": 2}}, {}, {}),
    "key-generation-fails": ({"gen_fail": True}, {}, {}),
    "the-enforcing-renet-fails-to-build": ({"build_fail": {"renet": 3}}, {}, {}),
}

WIPE_CALL = "sudo\t-n\trm\t-rf\t/var/lib/rediacc/license"
# The three preflight failures after which the twin ran its EXIT trap with `LICENSE_ROOT_PREEXISTED` still 0 (Rule T 1). The golden keeps the twin's answer, wipe included; the port is compared against that answer minus the wipe, and against the untouched store.
PREFLIGHT_CASES = (
    "go-is-not-installed",
    "embedded-assets-are-missing",
    "passwordless-sudo-is-unavailable",
)
UNTOUCHED_STATE = json.dumps(
    {"tree": ["chain-state.json"], "chain": CHAIN_STATE_BODY, "leftover": []}, indent=1
)
WIPED_STATE = json.dumps({"tree": [], "chain": None, "leftover": []}, indent=1)

FIELDS = ("exit", "stdout", "stderr", "calls", "state")


def _compare(name: str, got: dict, want: dict) -> None:
    for field in FIELDS:
        assert got[field] == want[field], "%s: %s diverged:\n twin: %r\n port: %r" % (
            name,
            field,
            want[field],
            got[field],
        )


@pytest.mark.parametrize("name", [n for n in CASES if n != "jq-is-not-installed"])
def test_port_matches_the_twins_recorded_output(tmp_path, name):
    cfg, binder_kw, run_kw = CASES[name]
    want = _answer(tmp_path, name, cfg, subject=TWIN_REL, binder_kw=binder_kw, run_kw=run_kw)
    if name in PREFLIGHT_CASES:
        assert WIPE_CALL in want["calls"], "the recorded twin no longer shows the store wipe"
        assert want["state"] == WIPED_STATE, want["state"]
        want = dict(want, calls=[c for c in want["calls"] if c != WIPE_CALL], state=UNTOUCHED_STATE)
    got = _answer(tmp_path, name, cfg, binder_kw=binder_kw, run_kw=run_kw)
    _compare(name, got, want)


def _port(tmp_path: pathlib.Path, cfg: dict | None = None, **kw) -> dict[str, Any]:
    return _answer(tmp_path, "direct", cfg or {}, **kw)


def test_the_fakes_are_actually_reached(tmp_path):
    """ANTI-VACUITY. Every comparison above is worthless if the battery never reached a binary. The call log must show the minter built, three renets built (enforcing, nolicense, wrong-key) and the scenario table driven against each."""
    out = _port(tmp_path)
    assert out["exit"] == 0, out["stderr"]
    calls = out["calls"]
    builds = [c for c in calls if c.startswith("go\t") and "\tbuild\t" in c]
    assert len(builds) == 4, builds
    assert builds[0].split("\t")[1] == ".ci/scripts/private/license-mint"
    assert all(b.split("\t")[1] == "private/renet" for b in builds[1:])
    assert "-tags\tnolicense" in builds[2]
    by_label = dict.fromkeys(("enforcing", "nolicense", "wrong-key"), 0)
    for call in calls:
        if call.startswith("renet\t"):
            by_label[call.split("\t")[1]] += 1
    assert all(n >= 20 for n in by_label.values()), by_label
    assert "Enforcing binary passed every scenario" in out["stderr"]
    assert "Control OK: nolicense fails the battery at S1" in out["stderr"]
    assert "Control OK: wrong-key fails the battery at S2" in out["stderr"]
    assert out["stderr"].rstrip().endswith("both controls failed as required")
    assert out["stdout"] == "", "the battery writes nothing to stdout"


def test_a_control_that_passes_the_battery_fails_the_run(monkeypatch, capsys):
    """THE CONTROL ON THE CONTROLS, called directly. A battery whose broken binaries still pass it cannot detect a broken build, and must say so. It cannot be driven end to end: the enforcing run leaves the fork scope's licence installed, so S8b fails on EVERY later run and a control never passes whole (finding reported with this port)."""
    battery = port_module.Battery(license_root="/nonexistent", geteuid=0)
    monkeypatch.setattr(battery, "run_battery", lambda _binary, _label: True)
    assert battery.expect_control_failure("renet", "wrong-key", "S2") is False
    assert "CONTROL FAILED: the wrong-key binary passed the battery" in capsys.readouterr().err


def test_a_control_that_fails_for_the_wrong_reason_fails_the_run(tmp_path):
    """A control must fail at the scenario that detects ITS defect class: a nolicense build that fails elsewhere but passes S1 proves nothing about stubs."""
    out = _port(tmp_path, {"bug": {"nolicense": "enforce"}})
    assert out["exit"] == 1
    assert "failed the battery, but S1 passed" in out["stderr"]


def test_the_scenario_table_is_complete(tmp_path):
    """Every scenario id the plan lists is asserted by the enforcing run, in order."""
    out = _port(tmp_path)
    passes = re.findall(r"\[enforcing\] (S\w+) PASS", out["stderr"])
    assert passes == [
        "S1",
        "S2",
        "S3",
        "S4",
        "S4b",
        "S5a",
        "S5b",
        "S5c",
        "S5d",
        "S6a",
        "S6b",
        "S8a",
        "S8b",
        "S8c",
        "S8d",
        "S8e",
        "S9a",
        "S9b",
        "S9c",
        "S9d",
        "S10a",
        "S10b",
        "S7",
        "S7b",
        "S11a",
        "S11b",
    ]


# --------------------------------------------------------------------------- Rule T 1: a failed preflight must not wipe the licence store


def test_a_failed_preflight_leaves_the_license_store_alone(tmp_path):
    """RULE T 1. The twin installed its EXIT trap before `preflight` while `LICENSE_ROOT_PREEXISTED` still held 0, so ANY preflight failure ran `sudo rm -rf /var/lib/rediacc/license`. The recorded twin shows the wipe and an emptied store; the port calls no `rm` and leaves the store, chain state included, as it found it."""
    for name in PREFLIGHT_CASES:
        cfg, binder_kw, run_kw = CASES[name]
        twin = _answer(tmp_path, name, cfg, subject=TWIN_REL, binder_kw=binder_kw, run_kw=run_kw)
        assert WIPE_CALL in twin["calls"], name
        assert twin["state"] == WIPED_STATE, name
        got = _answer(tmp_path, name, cfg, binder_kw=binder_kw, run_kw=run_kw)
        assert got["exit"] == 1 == twin["exit"], name
        assert not [c for c in got["calls"] if "\trm\t" in c], got["calls"]
        assert got["state"] == UNTOUCHED_STATE, got["state"]


def test_the_first_preflight_failure_is_reported_for_each_missing_thing(tmp_path):
    """The preflight reports EVERY missing requirement before it stops, not the first."""
    cfg = {"no_assets": True, "no_sudo": True}
    out = _port(tmp_path, cfg, binder_kw={"go": False})
    assert out["exit"] == 1
    for fragment in ("go is required", "embedded assets missing", "passwordless sudo is required"):
        assert fragment in out["stderr"], out["stderr"]


# --------------------------------------------------------------------------- Rule T 2: no jq


def test_jq_is_not_required(tmp_path):
    """RULE T 2. The twin refused to start without `jq` (and then wiped the store, see above). The port parses JSON itself, so a PATH without it runs the whole battery exactly as a PATH with it does."""
    tools = tuple(t for t in NEEDED if t != "jq")
    twin = _answer(
        tmp_path, "jq-is-not-installed", {}, subject=TWIN_REL, binder_kw={"tools": tools}
    )
    assert twin["exit"] == 1, "the recorded twin no longer fails without jq"
    assert "jq is required but not on PATH" in twin["stderr"]
    without = _port(tmp_path, binder_kw={"tools": tools})
    assert without["exit"] == 0, without["stderr"]
    assert "jq is required" not in without["stderr"]
    # Same battery, same bytes: only the scratch tree differs, so a second port run with jq is the baseline.
    sibling = tmp_path / "with-jq"
    sibling.mkdir()
    with_jq = _port(sibling)
    _compare("jq-is-not-installed", without, with_jq)


def test_jq_raw_reads_like_jq():
    assert port_module.jq_raw([{"status": "valid"}], 0, "status") == "valid"
    assert port_module.jq_raw([], 0, "status") == "null"
    assert port_module.jq_raw([{"other": 1}], 0, "status") == "null"
    assert port_module.jq_raw({"public": "p"}, "public") == "p"
    assert port_module.jq_raw([{"status": 3}], 0, "status") == "3"
    with pytest.raises(ValueError, match="cannot index"):
        port_module.jq_raw({"a": 1}, 0)


# --------------------------------------------------------------------------- Cleanup, both branches, called directly


def _battery(
    tmp_path: pathlib.Path, *, preexisted: bool, chain_backup: bool
) -> port_module.Battery:
    lic = tmp_path / "lic"
    lic.mkdir()
    battery = port_module.Battery(license_root=str(lic), geteuid=0)
    battery.work = str(tmp_path / "work")
    os.makedirs(battery.work)
    battery.preexisted = preexisted
    for sub in (
        "repos/license-e2e-valid",
        "repos/license-e2e-expired",
        "repos/other-real-repo",
        "repos/" + port_module.CHAIN_GUID,
        "datastores/" + port_module.PARENT_DS_ID,
        "datastores/real-ds",
    ):
        (lic / sub).mkdir(parents=True)
    (lic / "chain-state.json").write_text("mutated")
    if chain_backup:
        backup = tmp_path / "work" / "chain-state.backup.json"
        backup.write_text("original")
        battery.chain_backup = str(backup)
    return battery


def test_cleanup_removes_only_its_own_fixtures_when_the_store_preexisted(tmp_path):
    battery = _battery(tmp_path, preexisted=True, chain_backup=True)
    battery.cleanup()
    lic = tmp_path / "lic"
    assert (lic / "repos" / "other-real-repo").is_dir(), "a real repo licence was removed"
    assert (lic / "datastores" / "real-ds").is_dir()
    assert not (lic / "repos" / "license-e2e-valid").exists()
    assert not (lic / "repos" / port_module.CHAIN_GUID).exists()
    assert not (lic / "datastores" / port_module.PARENT_DS_ID).exists()
    assert (lic / "chain-state.json").read_text() == "original", "the chain state was not restored"
    assert not os.path.exists(battery.work), (
        "the scratch directory (and its enforcing binary) survived"
    )


def test_cleanup_deletes_a_chain_state_the_run_created(tmp_path):
    battery = _battery(tmp_path, preexisted=True, chain_backup=False)
    battery.cleanup()
    assert not (tmp_path / "lic" / "chain-state.json").exists()


def test_a_failed_chain_state_backup_never_deletes_the_operators_chain_state(tmp_path):
    """Review 797d99c0.1: the copy fails, so there is no backup file; cleanup must leave the real chain state, not take the run-created branch and `rm` it."""
    battery = _battery(tmp_path, preexisted=True, chain_backup=False)
    (tmp_path / "lic" / "chain-state.json").write_text("operator")
    battery.chain_state = str(tmp_path / "lic" / "chain-state.json")
    battery.sudo = ["false"]
    with pytest.raises(port_module._AbortError):
        battery._back_up_chain_state()
    battery.sudo = []
    battery.cleanup()
    assert (tmp_path / "lic" / "chain-state.json").read_text() == "operator"


def test_cleanup_removes_the_whole_store_only_when_the_run_created_it(tmp_path):
    battery = _battery(tmp_path, preexisted=False, chain_backup=False)
    battery.cleanup()
    assert not (tmp_path / "lic").exists()


def test_a_failed_chain_state_restore_is_reported(tmp_path, capsys):
    """RULE T 3. The twin's cleanup ran under `set +e` and discarded every status, so a restore that failed said nothing and left the operator's chain state replaced."""
    battery = _battery(tmp_path, preexisted=True, chain_backup=True)
    battery.sudo = ["false"]
    battery.cleanup()
    assert "could not restore" in capsys.readouterr().err


def test_cleanup_is_not_registered_before_the_store_is_probed(tmp_path, monkeypatch):
    """RULE T 1, at the source: a preflight that raises must reach no `rm` at all."""
    called: list[list[str]] = []
    monkeypatch.setattr(port_module, "_exec", lambda cmd, **_kw: called.append(list(cmd)))
    battery = port_module.Battery(license_root=str(tmp_path / "lic"), geteuid=0)
    monkeypatch.setattr(
        battery, "preflight", lambda: (_ for _ in ()).throw(port_module._AbortError(1))
    )
    assert battery.run() == 1
    assert not [c for c in called if "rm" in c], called


def test_a_failed_chain_state_backup_inside_the_battery_records_no_backup(tmp_path):
    """Inside the battery `_sudo` returns the failing status instead of raising, so the backup must not be recorded as taken."""
    battery = _battery(tmp_path, preexisted=True, chain_backup=False)
    (tmp_path / "lic" / "chain-state.json").write_text("operator")
    battery.chain_state = str(tmp_path / "lic" / "chain-state.json")
    battery.sudo = ["false"]
    battery.errexit = False
    battery._back_up_chain_state()
    assert battery.chain_backup == ""
    assert battery.chain_unbacked is True
    battery.sudo = []
    battery.cleanup()
    assert (tmp_path / "lic" / "chain-state.json").read_text() == "operator"


def test_a_battery_holding_the_store_makes_a_second_run_fail_after_the_bound(
    tmp_path, monkeypatch, capsys
):
    """Two runs on one license store never interleave (review 7e7a1ef7.1): while another process holds the store's lock, run() waits at most LOCK_WAIT_S and returns 1 without starting its battery."""
    started: list[bool] = []

    def fake_run(_self: object) -> int:
        started.append(True)
        return 0

    root = str(tmp_path / "store")
    key = hashlib.sha256(os.path.realpath(root).encode()).hexdigest()[:16]
    lock = f"/tmp/rediacc-license-e2e-{key}.lock"
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"import fcntl,os,time;fd=os.open({lock!r},os.O_RDONLY|os.O_CREAT,0o644);fcntl.flock(fd,fcntl.LOCK_EX);print('held',flush=True);time.sleep(60)",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "held"
        monkeypatch.setattr(port_module, "LOCK_WAIT_S", 1)
        monkeypatch.setattr(port_module.Battery, "run", fake_run)
        t0 = time.monotonic()
        assert port_module.run([], license_root=root) == 1
        assert time.monotonic() - t0 >= 1
        assert started == []
        assert root in capsys.readouterr().err
    finally:
        holder.kill()
        holder.wait()
        if holder.stdout is not None:
            holder.stdout.close()
        os.unlink(lock)
    try:
        assert port_module.run([], license_root=root) == 0
        assert started == [True]
        # A scratch store's lock file is removed on exit, so a run leaves nothing in /tmp.
        assert not os.path.lexists(lock)
    finally:
        pathlib.Path(lock).unlink(missing_ok=True)


def test_a_symlink_at_the_lock_path_fails_the_run_with_its_reason(tmp_path, monkeypatch, capsys):
    """O_NOFOLLOW refuses a planted symlink at the lock path, and run() returns 1 naming it instead of raising (review 41af1678.1)."""
    root = str(tmp_path / "store")
    key = hashlib.sha256(os.path.realpath(root).encode()).hexdigest()[:16]
    lock = f"/tmp/rediacc-license-e2e-{key}.lock"
    os.symlink(tmp_path / "elsewhere", lock)
    started: list[bool] = []

    def fake_run(_self: object) -> int:
        started.append(True)
        return 0

    monkeypatch.setattr(port_module.Battery, "run", fake_run)
    try:
        assert port_module.run([], license_root=root) == 1
    finally:
        os.unlink(lock)
    assert started == []
    assert lock in capsys.readouterr().err


def test_the_real_store_is_recognised_through_a_trailing_slash_or_a_symlink(tmp_path, monkeypatch):
    """A non-canonical spelling of the real store is the real store, so its fixed lock file is never unlinked (review 768f6e50.1); a different directory is a scratch store."""
    real = tmp_path / "license"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    monkeypatch.setattr(port_module, "LICENSE_ROOT", str(real))
    assert not port_module.is_scratch_store(str(real) + "/")
    assert not port_module.is_scratch_store(str(link))
    assert port_module.is_scratch_store(str(tmp_path / "other"))


def test_a_lock_taken_on_an_unlinked_inode_is_retried_on_the_live_file(tmp_path, monkeypatch):
    """A waiter that wins the flock on an inode a previous holder already unlinked must reopen and lock the file now at the lock path, not run beside the newcomer (review 768f6e50.1/.2): the first stat reports a different inode, the run reopens, and the battery runs once."""
    root = str(tmp_path / "store")
    key = hashlib.sha256(os.path.realpath(root).encode()).hexdigest()[:16]
    lock = f"/tmp/rediacc-license-e2e-{key}.lock"
    started: list[bool] = []
    opens: list[str] = []
    real_open = os.open
    real_stat = os.stat
    stats = {"n": 0}

    def counting_open(path, *args, **kwargs):
        if path == lock:
            opens.append(path)
        return real_open(path, *args, **kwargs)

    def first_stat_mismatches(path, *args, **kwargs):
        result = real_stat(path, *args, **kwargs)
        if path == lock:
            stats["n"] += 1
            if stats["n"] == 1:
                return os.stat_result((result.st_mode, result.st_ino + 1, *tuple(result)[2:]))
        return result

    def fake_run(_self: object) -> int:
        started.append(True)
        return 0

    monkeypatch.setattr(port_module.os, "open", counting_open)
    monkeypatch.setattr(port_module.os, "stat", first_stat_mismatches)
    monkeypatch.setattr(port_module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(port_module.Battery, "run", fake_run)
    try:
        assert port_module.run([], license_root=root) == 0
        assert started == [True]
        assert len(opens) == 2
        assert not os.path.lexists(lock)
    finally:
        pathlib.Path(lock).unlink(missing_ok=True)


def test_a_stat_that_keeps_failing_ends_at_the_deadline(tmp_path, monkeypatch, capsys):
    """When the lock path cannot be stat'ed after a successful lock, the run waits and fails at LOCK_WAIT_S with its reason instead of looping (review 768f6e50.3)."""
    root = str(tmp_path / "store")
    key = hashlib.sha256(os.path.realpath(root).encode()).hexdigest()[:16]
    lock = f"/tmp/rediacc-license-e2e-{key}.lock"
    real_stat = os.stat
    clock = {"t": 0.0}

    def failing_stat(path, *args, **kwargs):
        if path == lock:
            raise FileNotFoundError(path)
        return real_stat(path, *args, **kwargs)

    def advance(_s: float) -> None:
        clock["t"] += 1.0

    monkeypatch.setattr(port_module.os, "stat", failing_stat)
    monkeypatch.setattr(port_module.time, "sleep", advance)
    monkeypatch.setattr(port_module.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(port_module, "LOCK_WAIT_S", 3)
    monkeypatch.setattr(port_module.Battery, "run", lambda _self: 0)
    try:
        assert port_module.run([], license_root=root) == 1
        assert root in capsys.readouterr().err
    finally:
        pathlib.Path(lock).unlink(missing_ok=True)
