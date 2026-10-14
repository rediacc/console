#!/usr/bin/env python3
"""Freeze or refresh a hook golden from the current port (PLAN-retire-bash-oracles A1/A2/A3).

    regolden.py <stem|guards|shellscan|post-bash|all> --reason "<why>" [--out-dir <dir>]

`--out-dir` writes each golden into that directory instead of over the committed one (still diffing against the committed one), so a recording can be compared without touching the tree.

THE SUMMARY COUNTS EVERY REWRITTEN LINE (queued item #c2a39bea). `N changed` is the records whose value moved under a key both sides hold; `L line(s) rewritten` is the diff a reviewer sees, moved, added and dropped keys included. A run that rewrote lines while no record changed value used to print "0 changed" and look like a no-op.

REFUSES WITHOUT A REASON, unconditionally: `--reason` is a required argument, not a flag that only bites when something changed. The reason is stamped as `intentional: <reason>` on every record whose value differs from what the existing golden already said; a first-time recording changes nothing relative to a golden that did not exist, so it writes no markers at all, and re-running this with no port change reproduces the byte-identical file (the diff review IS the proof that nothing moved).

ONE SOURCE NOW: THE CURRENT PYTHON PORT. Before PLAN-retire-bash-oracles A3 this
script also had `--source bash`, which ran the real oracle -- `.claude/oracles/`'s tracked file for a guard, `command-scan.sh` for shellscan, the two `post-bash/*.sh` twins -- and froze what it said; that was the only legitimate way to create a FIRST golden, because A1's whole point was an independent check. A3 deleted the oracle tree once every golden it could produce was
frozen and proven to match, so there is no second implementation left to freeze from: every regolden from here on is a Rule-T re-recording of the port's own, now-authoritative answer, stamped `intentional` exactly as a Rule-T fix always was.

ONE SCRIPT FOR ALL THREE DIFFERENTIALS, because a guard's rc/out/err, shellscan's ~28 named fields and post-bash's rc/out/err/body/calls all reduce to the same question: does this key's answer match what the golden already said, and if not, was a reason given. `goldenio.diff_and_mark` answers that once for the rc/out/err shape (guards); shellscan and post-bash compare their own wider dict directly, for the same reason and against the same old-file read.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

_HERE = pathlib.Path(__file__).resolve()

# PYTEST LIVES IN THE BOOTSTRAP'S TOOL VENV, not on the system python3 this script is launched with, and the differentials it imports need it. Re-exec under that venv's interpreter instead of dying with ModuleNotFoundError (2026-10-08, hit by three writers).
if importlib.util.find_spec("pytest") is None:
    _VENV_PY = _HERE.parents[3] / ".ci/cache/toolchain/uv-tools/pytest/bin/python"
    # A venv's `python` is a symlink to the base interpreter, so the binary cannot tell them apart; sys.prefix can.
    if (
        os.access(_VENV_PY, os.X_OK)
        and pathlib.Path(sys.prefix).resolve() != _VENV_PY.parents[1].resolve()
    ):
        raise SystemExit(
            subprocess.run([str(_VENV_PY), str(_HERE), *sys.argv[1:]], check=False).returncode
        )
    if os.access(_VENV_PY, os.X_OK):
        raise SystemExit(
            "regolden: pytest is not importable inside %s itself (the venv exists but is incomplete).\n  fix: bash .ci/bootstrap.sh"
            % _VENV_PY
        )
    raise SystemExit(
        "regolden: pytest is not importable and %s is missing.\n  fix: bash .ci/bootstrap.sh"
        % _VENV_PY
    )
# The canonical `.claude` hop, rediacc_hooks/syspath.py, loaded BY PATH: run as a script, only this file's own directory is on sys.path, so `rediacc_hooks` is not importable by name until the hop is made.
_SYSPATH = importlib.util.spec_from_file_location(
    "rediacc_hooks_syspath", _HERE.parents[1] / "syspath.py"
)
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: .claude/rediacc_hooks/syspath.py is missing" % __file__)
_syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(_syspath)
_syspath.on_sys_path(_HERE.parents[2])

# ALWAYS THE FULL CROSS PRODUCT for a guard recording, never the default 40-of-378 sample. A golden built from the sample would have no record for the other 338 payloads any default-mode differential run might legitimately ask about once `cross_sample`'s deterministic hash picks a different 40 for a guard whose corpus grew; recording the full pool once makes every later default-mode lookup a strict subset lookup. Must be set BEFORE `test_guards_differential` is imported: its `CASES`/`POOL` are built at import time from this flag.
os.environ["REDIACC_GUARD_DIFF_FULL"] = "1"

guards = importlib.import_module("rediacc_hooks.guards")
goldenio = importlib.import_module("rediacc_hooks.tests.goldenio")
gd = importlib.import_module("rediacc_hooks.tests.test_guards_differential")
pd = importlib.import_module("rediacc_hooks.tests.test_post_bash_differential")
sd = importlib.import_module("rediacc_hooks.tests.test_shellscan_differential")


def _write_path(path, out_dir):
    """Where a recording lands: the committed golden, or the same file name under `--out-dir`."""
    return path if out_dir is None else out_dir / path.name


def _record_guard(stem, reason, out_dir=None):
    cases = [c for c in gd.CASES if c[0] == stem]
    if not cases:
        raise SystemExit("no cases found for guard %s" % stem)
    path = goldenio.golden_path(stem)
    _old_header, old_silent, old_records = goldenio.read_golden(path)
    with tempfile.TemporaryDirectory(prefix="regolden-guard-") as td:
        work = pathlib.Path(td)

        def one(i):
            _stem, _label, payload, _env, extra, stubs = cases[i]
            fields = gd.python_fields(stem, payload, extra, stubs, work)
            return fields["rc"], fields["out"], fields["err"]

        answers = {}
        carried = []
        for i, (_stem, label, payload, env_label, extra, stubs) in enumerate(cases):
            key = gd.golden_case_key(label, payload, extra, stubs)
            # A CASE THE DIFFERENTIAL NEVER COMPARES (`gd.GOLDEN_UNSTABLE_ENVS`: its answer quotes a live PID minted per run) keeps the row it already has. Re-recording it rewrote the PID on every regolden, a "change" in a record nothing reads, which the line count below now reports instead of hiding.
            if (stem, env_label) in gd.GOLDEN_UNSTABLE_ENVS and (
                key in old_records or key in old_silent
            ):
                carried.append(key)
                continue
            rc, out, err = one(i)
            answers[key] = (rc, goldenio.normalize(out, work), goldenio.normalize(err, work))
    silent, records, changed = goldenio.diff_and_mark(answers, old_silent, old_records, reason)
    for key in carried:
        if key in old_silent:
            silent.add(key)
        else:
            records[key] = old_records[key]
    header = {
        "bash_version": goldenio.bash_version_line(),
        "case_count": len(cases),
        "source": "port",
    }
    path = _write_path(path, out_dir)
    goldenio.write_golden(path, header, silent, records)
    return path, len(cases), changed


def _merge_shellscan_record(key, fields, old_records, reason, records, changed):
    old = None
    if key in old_records:
        old = {
            k: goldenio.decode_field(v) for k, v in old_records[key].items() if k != "intentional"
        }
    is_changed = old is not None and old != fields
    row = {k: goldenio.encode_field(v) for k, v in fields.items()}
    # An unchanged record keeps the marker an earlier run wrote (#84358ce1, see goldenio.carried_marker).
    marker = reason if is_changed else goldenio.carried_marker(key, old_records)
    if marker is not None:
        row["intentional"] = marker
    if is_changed:
        changed.append(key)
    records[key] = row


def _record_shellscan(reason, out_dir=None):
    _old_header, _old_silent, old_records = goldenio.read_golden(goldenio.golden_path("shellscan"))
    records: dict[str, dict] = {}
    changed: list[str] = []
    for label, cmd in sd.CASES:
        fields = sd.python_fields(cmd)
        key = sd.cmd_key(label, cmd)
        _merge_shellscan_record(key, fields, old_records, reason, records, changed)
    for label, payload in sd.JSON_CASES:
        fields = sd.python_init_fields(payload)
        key = sd.json_key(label, payload)
        _merge_shellscan_record(key, fields, old_records, reason, records, changed)
    header = {
        "bash_version": goldenio.bash_version_line(),
        "case_count": len(sd.CASES) + len(sd.JSON_CASES),
        "source": "port",
    }
    path = _write_path(goldenio.golden_path("shellscan"), out_dir)
    goldenio.write_golden(path, header, set(), records)
    return path, len(sd.CASES) + len(sd.JSON_CASES), changed


def _record_post_bash(reason, out_dir=None):
    path = goldenio.golden_path("post-bash")
    _old_header, _old_silent, old_records = goldenio.read_golden(path)
    records: dict[str, dict] = {}
    changed: list[str] = []
    for subject, label, payload_doc, table in pd.CASES:
        payload = json.dumps(payload_doc)
        with tempfile.TemporaryDirectory(prefix="regolden-postbash-") as td:
            answer = pd._answer(subject, payload, table, pathlib.Path(td))
        key = pd.golden_key(subject, label, payload_doc, table)
        encoded = pd._encode_answer(answer)
        old = old_records.get(key)
        is_changed = False
        if old is not None:
            old_decoded = pd._decode_answer({k: v for k, v in old.items() if k != "intentional"})
            is_changed = old_decoded != answer
        marker = reason if is_changed else goldenio.carried_marker(key, old_records)
        if marker is not None:
            encoded["intentional"] = marker
        if is_changed:
            changed.append(key)
        records[key] = encoded
    header = {
        "bash_version": goldenio.bash_version_line(),
        "case_count": len(pd.CASES),
        "source": "port",
    }
    path = _write_path(path, out_dir)
    goldenio.write_golden(path, header, set(), records)
    return path, len(pd.CASES), changed


def _targets(name):
    if name in ("all", "guards"):
        out = [
            ("guard", stem)
            for stem in guards.stems()
            if not guards.has_own_suite(guards.load(stem))
        ]
        if name == "all":
            out += [("shellscan", None), ("post-bash", None)]
        return out
    if name == "shellscan":
        return [("shellscan", None)]
    if name == "post-bash":
        return [("post-bash", None)]
    if name not in guards.stems():
        raise SystemExit(
            "unknown target %r: expected a guard stem, 'guards', 'shellscan', 'post-bash' or "
            "'all'" % name
        )
    if guards.has_own_suite(guards.load(name)):
        raise SystemExit("%s declares OWN_SUITE = True: there is no golden to regolden" % name)
    return [("guard", name)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", help="a guard stem, 'guards', 'shellscan', 'post-bash', or 'all'")
    parser.add_argument(
        "--reason", required=True, help="why this recording ran; stamped on every changed record"
    )
    parser.add_argument(
        "--out-dir",
        type=pathlib.Path,
        help="write the goldens here instead of over the committed ones (diffed against the committed ones)",
    )
    args = parser.parse_args(argv)
    out_dir = args.out_dir.resolve() if args.out_dir else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)

    for kind, name in _targets(args.target):
        started = time.monotonic()
        committed = goldenio.golden_path(name if kind == "guard" else kind)
        before = committed.read_text(encoding="utf-8") if committed.is_file() else ""
        if kind == "guard":
            path, n, changed = _record_guard(name, args.reason, out_dir)
            label = name
        elif kind == "shellscan":
            path, n, changed = _record_shellscan(args.reason, out_dir)
            label = "shellscan"
        else:
            path, n, changed = _record_post_bash(args.reason, out_dir)
            label = "post-bash"
        lines = goldenio.rewritten_lines(before, path.read_text(encoding="utf-8"))
        elapsed = time.monotonic() - started
        shown = path.relative_to(gd.ROOT) if path.is_relative_to(gd.ROOT) else path
        print(
            "%s: %d case(s) -> %s (%d changed, %d line(s) rewritten, %.1fs)"
            % (label, n, shown, len(changed), lines, elapsed)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
