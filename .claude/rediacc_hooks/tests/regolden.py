#!/usr/bin/env python3
"""Freeze or refresh a hook golden from the current port (PLAN-retire-bash-oracles A1/A2/A3).

    regolden.py <stem|guards|shellscan|post-bash|all> --reason "<why>"

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
import tempfile
import time

_HERE = pathlib.Path(__file__).resolve()
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

from rediacc_hooks import guards  # noqa: E402
from rediacc_hooks.tests import goldenio  # noqa: E402
from rediacc_hooks.tests import test_guards_differential as gd  # noqa: E402
from rediacc_hooks.tests import test_post_bash_differential as pd  # noqa: E402
from rediacc_hooks.tests import test_shellscan_differential as sd  # noqa: E402


def _record_guard(stem, reason):
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
        for i, (_stem, label, payload, _env, extra, stubs) in enumerate(cases):
            rc, out, err = one(i)
            key = gd.golden_case_key(label, payload, extra, stubs)
            answers[key] = (rc, goldenio.normalize(out, work), goldenio.normalize(err, work))
    silent, records, changed = goldenio.diff_and_mark(answers, old_silent, old_records, reason)
    header = {
        "bash_version": goldenio.bash_version_line(),
        "case_count": len(cases),
        "source": "port",
    }
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
    if is_changed:
        row["intentional"] = reason
        changed.append(key)
    records[key] = row


def _record_shellscan(reason):
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
    path = goldenio.golden_path("shellscan")
    goldenio.write_golden(path, header, set(), records)
    return path, len(sd.CASES) + len(sd.JSON_CASES), changed


def _record_post_bash(reason):
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
        if is_changed:
            encoded["intentional"] = reason
            changed.append(key)
        records[key] = encoded
    header = {
        "bash_version": goldenio.bash_version_line(),
        "case_count": len(pd.CASES),
        "source": "port",
    }
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
    args = parser.parse_args(argv)

    for kind, name in _targets(args.target):
        started = time.monotonic()
        if kind == "guard":
            path, n, changed = _record_guard(name, args.reason)
            label = name
        elif kind == "shellscan":
            path, n, changed = _record_shellscan(args.reason)
            label = "shellscan"
        else:
            path, n, changed = _record_post_bash(args.reason)
            label = "post-bash"
        elapsed = time.monotonic() - started
        print(
            "%s: %d case(s) -> %s (%d changed, %.1fs)"
            % (label, n, path.relative_to(gd.ROOT), len(changed), elapsed)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
