"""The renet test map has two readers, and they must give the same answer (agent/plans/PLAN-renet-change-test-triggers.md, M1-M3).

`scripts/gates/check-renet-test-map.ts` selects the `go test` packages a renet diff runs and writes the receipt; `.claude/hooks/stop/wl_renettests.py` selects the packages a pushed range requires, for `block_renet_untested_push` and the Stop hook's advisory. A rule changed on one side alone (the most-specific glob, the unmapped-Go-path fallback, the `always` set) would let the guard demand packages the gate never runs, or admit a push the gate did not test.

THE CORPUS is drawn from the REAL map, so it grows with it: a file under every entry's glob, every `whole` path, an unmapped package path, an unmapped `.go` file outside pkg/ and cmd/, docs, and the retired and outside globs, every `console` row's file on its own and beside a renet change, and the combinations. A case is a pair `(renet paths, console paths)`. Both readers answer each case; the answers must be equal, and the corpus must exercise every branch (some case selects nothing, some selects everything, some selects a subset), or the comparison proved nothing.
"""

from __future__ import annotations

import json
import os
import subprocess

import wl_renettests as wr

from rediacc_ci import paths

GATE = "scripts/gates/check-renet-test-map.ts"


def _corpus(test_map):
    cases = [
        ([e["glob"][:-3] + "/zz_parity.go"], [])
        for e in test_map["entries"]
        if e["glob"].endswith("/**")
    ]
    cases += [([w["glob"]], []) for w in test_map["whole"]]
    cases += [([r["glob"][:-3] + "/zz_parity.go"], []) for r in test_map["retired"]]
    cases += [([o["glob"][:-3] + "/zz_parity_test.go"], []) for o in test_map["outside"]]
    cases += [([], [c["glob"]]) for c in test_map["console"]]
    cases += [(["README.md"], [c["glob"]]) for c in test_map["console"]]
    cases += [(["pkg/license/x.go"], [c["glob"]]) for c in test_map["console"]]
    cases += [
        (["README.md"], []),
        ([], ["docs/x.md", "packages/shared/src/zz_unrelated.json"]),
        (["docs/x.md", "tests/e2e/test_x.py"], []),
        (["pkg/zz-unmapped-parity/x.go"], []),
        (["tools/zz.go"], []),
        (["pkg/license/x_test.go", "README.md"], []),
        (["pkg/infra/ceph/x.go", "pkg/infra/x.go"], []),
    ]
    return cases


def _ts_answers(cases):
    tsx = paths.from_root("node_modules", ".bin", "tsx")
    assert os.access(tsx, os.X_OK), (
        "tsx not installed at %s; run npm install && npm run install:natives" % tsx
    )
    program = (
        "import fs from 'node:fs';"
        "import { requiredFor } from './%s';"
        "const map = JSON.parse(fs.readFileSync('%s', 'utf-8'));"
        "const all = [...new Set(map.entries.flatMap((e) => e.packages))].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));"
        "const cases = JSON.parse(fs.readFileSync(0, 'utf-8'));"
        "process.stdout.write(JSON.stringify(cases.map((c) => { const r = requiredFor(map, c[0], all, c[1]); return { all: r.all, packages: r.packages }; })));"
    ) % (GATE, wr.MAP_REL)
    proc = subprocess.run(
        [os.fspath(tsx), "--eval", program],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        check=False,
        cwd=os.fspath(paths.from_root()),
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout)


def test_the_two_readers_agree_on_the_real_map():
    test_map = wr.load_map(paths.from_root())
    assert test_map is not None, "%s is missing or unreadable" % wr.MAP_REL
    assert len(test_map["entries"]) >= 20, (
        "only %d map entries; the map is not the renet tree" % len(test_map["entries"])
    )
    cases = _corpus(test_map)
    ts = _ts_answers(cases)
    assert len(ts) == len(cases)
    py = [
        {"all": r["all"], "packages": r["packages"]}
        for r in (wr.required_for(test_map, c[0], None, c[1]) for c in cases)
    ]
    diverged = [(c, t, p) for c, t, p in zip(cases, ts, py, strict=True) if t != p]
    assert not diverged, "the gate and wl_renettests disagree on %d case(s), first: %r" % (
        len(diverged),
        diverged[0],
    )
    # Anti-vacuity: the corpus exercised every branch, so equality is a claim about all of them.
    assert any(not p["packages"] for p in py), "no case selected nothing"
    assert any(p["all"] for p in py), "no case selected every package"
    assert any(p["packages"] and not p["all"] for p in py), "no case selected a subset"


def test_the_always_set_rides_every_mapped_selection():
    test_map = wr.load_map(paths.from_root())
    always = {a["package"] for a in test_map["always"]}
    assert always, (
        "the map names no always package; the i18n source scan would never run on a Go change"
    )
    picked = wr.required_for(test_map, ["pkg/license/x.go"])
    assert always <= set(picked["packages"])
    assert not wr.required_for(test_map, ["README.md"])["packages"]


def test_a_console_only_change_selects_the_packages_that_read_it():
    """Each console row's file selects exactly its packages (no always set), and a renet change beside it adds both."""
    test_map = wr.load_map(paths.from_root())
    assert test_map["console"], "the map names no console read; renet tests that read console files go unselected"
    for row in test_map["console"]:
        alone = wr.required_for(test_map, [], None, [row["glob"]])
        assert alone["packages"] == sorted(row["packages"]), row["glob"]
        assert not alone["all"]
    assert not wr.required_for(test_map, [], None, ["docs/x.md"])["packages"]


def test_every_console_row_names_a_file_that_exists_and_is_read_by_its_packages():
    """The liveness half the gate also checks on the real tree: a renamed console file would silently select nothing."""
    root = paths.from_root()
    test_map = wr.load_map(root)
    for row in test_map["console"]:
        assert (root / row["glob"]).exists(), "%s: no such console path" % row["glob"]
        needle = row["glob"].rsplit("/", 1)[-1]
        for pkg in row["packages"]:
            tests = sorted((root / wr.RENET / pkg).glob("*_test.go"))
            if not tests and not (root / wr.RENET / "go.mod").is_file():
                continue  # renet is not checked out: the gate, not this pin, owns the read check
            assert any(needle in t.read_text(encoding="utf-8") for t in tests), (
                "%s: no _test.go in %s names %s" % (row["glob"], pkg, needle)
            )
