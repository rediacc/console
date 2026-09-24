"""The pre-commit probe and the CI gate must answer the same question the same way.

WHAT IS BEING PINNED. `scripts/gates/check-shape-duplication.ts` scans the whole corpus and reports every shape that reached N copies. `.claude/rediacc_hooks/guards/warn_staged_shape_duplication.py` asks a narrower question on the commit path -- does THIS staged file reach N copies -- and answers it from a cached index plus a bundle of the gate's own code. The bundling is what
keeps the NORMALISATION single-sourced; what it cannot keep honest is the CACHE. A `near` index built with a different selection rule, a coalescing step that merged differently, or a staged file counted as a copy of itself would each produce an answer the gate never gives, and nothing else in the tree would say so.

SO THE TEST IS A PAIR OF CALLABLES OVER A SHARED CORPUS, the form `test_sibling_agreement.py` argues for at length: both sides are recomputed on every run, so a stale entry cannot go quiet and a renamed function fails loudly rather than hiding in an allowlist. For a sample of real corpus files, the probe's findings with that file staged must equal the gate's own findings that
mention it, compared as `file:line` sets.

SEEDING IS OFF ON BOTH SIDES (`--no-seed`, and `noSeed` in the probe request), which is what makes the comparison say anything at all. Under the committed seed the standing backlog is silent by design, so both sides would answer "nothing" for every file in the sample and the test would pass without ever comparing two findings. With the seed off the corpus reports its real
180-odd spans, and the sample is drawn so that some of them are in it.

BOTH PROFILES, since agent/plans/PLAN-stop-hook-refactor-enforcement.md Commit 3 (its risk 5). The `advisory` profile scans four other families with their own helper set and their own cache, and the Stop hook's wide tier reads that cache; without a second case the advisory probe could drift from the advisory scan with nothing noticing, which is the exact defect this test exists for. Every test below runs once per profile.

THE PLANTED CONTROL IS NOT DECORATION. A two-file entry in the cached index, given a fabricated third file, makes the probe report a finding the gate does not. If that does not fail the comparison, the comparison is not comparing anything.
"""

import json
import os
import subprocess

import pytest

from rediacc_ci import paths

ROOT = paths.repo_root()
GATE = paths.from_root("scripts", "gates", "check-shape-duplication.ts")

# Eight files, half of them drawn from the gate's own findings. The halves buy different things: a file WITH findings proves the probe reproduces them, and a file without proves it does not invent any. A sample of only the first kind would pass for a probe that reported every shape it saw.
SAMPLE_WITH_FINDINGS = 4
SAMPLE_WITHOUT = 4


def _run(argv, **kwargs):
    return subprocess.run(argv, capture_output=True, text=True, check=False, **kwargs)


# `None` is the default profile, run with the argv this test has always used, so the gate case stays byte-identical to before the advisory case existed.
PROFILES = (None, "advisory")


@pytest.fixture(scope="module", params=PROFILES, ids=lambda p: p or "gate")
def world(request, tmp_path_factory):
    """ONE gate run per profile: the index, the bundle and the unseeded findings all come out of it.

    The cache goes to a temporary directory through `SHAPE_PROBE_CACHE`, so this never overwrites the checkout's own cache -- which a live session's commit path is reading at the same moment.
    """
    cache = tmp_path_factory.mktemp("shape-index")
    env = dict(os.environ, SHAPE_PROBE_CACHE=str(cache))
    argv = ["npx", "tsx", str(GATE), "--emit-index", "--no-seed", "--json"]
    if request.param:
        argv += ["--profile", request.param]
    proc = _run(argv, cwd=str(ROOT), env=env)
    line = ""
    for row in proc.stdout.splitlines():
        if row.startswith("{"):
            line = row
    assert line, "the gate printed no JSON verdict (rc=%d):\n%s" % (proc.returncode, proc.stderr)
    index_path = cache / "index.json"
    assert index_path.is_file(), "the gate wrote no index: %s" % proc.stderr
    index = json.loads(index_path.read_text(encoding="utf-8"))
    # THE PROFILE REACHED THE COUNTER, or the advisory case is the gate case run twice and proves nothing about the advisory scan. Read off the index the run itself wrote, not off the argv this fixture built.
    wide = any(p.startswith(".claude/hooks/stop/") for p in index.get("pathspecs", []))
    assert wide == (request.param == "advisory"), "profile %r produced an index over %s" % (
        request.param,
        index.get("pathspecs"),
    )
    return {
        "cache": cache,
        "index_path": index_path,
        "index": index,
        "findings": json.loads(line)["findings"],
    }


def gate_sets(findings, target):
    """The gate's findings mentioning `target`, as a set of file-tuples."""
    return {
        tuple(f["files"])
        for f in findings
        if any(loc.rsplit(":", 1)[0] == target for loc in f["files"])
    }


def probe(world, target, index_path=None):
    """The probe's answer with `target` staged, read through the bundle the gate just built."""
    request = {
        "root": str(ROOT),
        "index": str(index_path or world["index_path"]),
        "files": {target: (ROOT / target).read_text(encoding="utf-8")},
        "noSeed": True,
    }
    proc = _run(
        ["node", str(world["cache"] / "probe.mjs"), "--probe"],
        cwd=str(ROOT),
        input=json.dumps(request),
    )
    assert proc.returncode == 0, "the probe failed on %s: %s" % (target, proc.stderr)
    answer = json.loads(proc.stdout)
    assert "error" not in answer, answer
    return {tuple(f["files"]) for f in answer["findings"]}


def spread(rows, count):
    """Evenly spaced rather than random or first-N: a deterministic slice across the sorted corpus, so a rerun compares the same files and a family clustered at one end cannot own the whole sample."""
    if not rows:
        return []
    step = max(1, len(rows) // count)
    return rows[::step][:count]


def sample(world):
    """Files the comparison is run over: some that have findings, some that do not."""
    corpus = sorted(set(world["index"]["corpus"]) - set(world["index"]["opted_out"]))
    with_findings = sorted({loc.rsplit(":", 1)[0] for f in world["findings"] for loc in f["files"]})
    without = [f for f in corpus if f not in set(with_findings)]
    return spread(with_findings, SAMPLE_WITH_FINDINGS), spread(without, SAMPLE_WITHOUT)


def test_the_sample_is_not_vacuous(world):
    """A comparison of two empty sets, eight times over, is not a comparison.

    This is the arm that would have caught the seeded version of this test: with the committed seed in force every file in the corpus answers "no findings" on both sides, and the agreement assertions below would all pass while comparing nothing.
    """
    hit, miss = sample(world)
    assert len(hit) == SAMPLE_WITH_FINDINGS, (
        "only %d corpus file(s) carry an unseeded finding, so the sample cannot be drawn; "
        "the gate reported %d finding(s) in total" % (len(hit), len(world["findings"]))
    )
    assert len(miss) == SAMPLE_WITHOUT
    assert sum(len(gate_sets(world["findings"], f)) for f in hit) >= SAMPLE_WITH_FINDINGS


def test_probe_agrees_with_the_gate(world):
    """For each sampled file, both sides name the same spans, as `file:line` sets."""
    hit, miss = sample(world)
    disagreements = []
    for target in hit + miss:
        want = gate_sets(world["findings"], target)
        got = probe(world, target)
        if got != want:
            disagreements.append(
                "%s\n    gate  %s\n    probe %s" % (target, sorted(want), sorted(got))
            )
    assert not disagreements, (
        "the cached probe and the whole-corpus gate disagree about these files, so the "
        "commit-path advisory is answering a different question:\n%s" % "\n".join(disagreements)
    )


def test_the_comparison_can_fail(world, tmp_path):
    """A planted two-file entry must break the agreement.

    The plant is the smallest lie the index can tell: one shape the sampled file really carries, credited to a file that does not exist. The probe then counts N copies where the gate counts N-1, and the comparison has to notice. A green that has never been shown to be able to go red is not evidence.
    """
    hit, _miss = sample(world)
    target = hit[0]
    index = json.loads(world["index_path"].read_text(encoding="utf-8"))
    near = index["near"]
    # A shape the target really carries, so the plant reaches the probe's tally at all; the entry is then given a file nothing else names, which is one copy the gate never sees.
    carried = [h for h, locs in near.items() if any(loc.startswith(target + ":") for loc in locs)]
    assert carried, "the index credits %s with no shape at all, so nothing can be planted" % target
    for h in carried:
        near[h] = sorted({*near[h], "planted/not-a-real-file.ts:1"})
    planted = tmp_path / "planted.json"
    planted.write_text(json.dumps(index), encoding="utf-8")

    want = gate_sets(world["findings"], target)
    got = probe(world, target, index_path=planted)
    assert got != want, (
        "the probe answered identically with a fabricated copy planted in its index, so "
        "test_probe_agrees_with_the_gate cannot fail and proves nothing"
    )
