"""Port of `.ci/scripts/test/gates/test-dead-bash.sh`, retired in W7 P5.

Subject: `scripts/gates/check-dead-bash.ts`, the detector for unreferenced shell scripts and uncalled shell functions.

PROVABLE BOTH WAYS OR NOT AT ALL. The detector must fire on planted dead code AND must stay silent on the two discovery mechanisms that make a naive version useless -- glob expansion and dynamic dispatch. A naive detector reports 54 orphan files in this repo, about 85% of them false, and a gate that noisy is a gate that gets suppressed.

THE REAL-TREE HALF LIVES IN `check:ci-dead-bash`, NOT HERE, and the twin records why (changed 2026-09-06): it used to open with a full-repository scan that `check:ci-dead-bash` already performs as its own first-class manifest gate, so the real-tree scan executed TWICE per `npm run ci` -- measured at 246s and 239s
for the two long-lived processes. What replaced it is
`test_real_tree_scan_is_delegated`, which asserts the delegate still EXISTS and is still scheduled. Deleting that assertion is how the coverage would actually be lost, so it fails this gate rather than being left to a comment.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. Two of its cases read the real `package.json` and the real `scripts/ci-runner/manifest.ts` -- the lock records `reads: ["tree:repo"]` for `gate-test:dead-bash` -- and `real_tree_admission` in `test_twin_parity.py` refuses a twin in that set that does not declare `REAL_TREE_TWIN`. Nothing here WRITES a tracked file: every fixture lives
under a temp dir reached through `DEAD_BASH_ROOT`, because the working tree routinely holds other sessions' uncommitted work.

`delegation_verdict` IS A PURE FUNCTION TAKING BOTH REGISTRIES AS ARGUMENTS, and that is the same seam the twin cut for the same reason: the control below drives the IDENTICAL code path against four doctored registries rather than against a lookalike reimplementation of it. A control that re-derives the answer proves only that the control agrees with itself.
"""

import json
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

# Two cases read the real package.json and manifest.ts. See the docstring.
REAL_TREE_TWIN = True

ROOT = paths.repo_root()
GATE = ROOT / "scripts" / "gates" / "check-dead-bash.ts"

DELEGATE_KEY = "check:ci-dead-bash"
DELEGATE_LEAF = "scripts/gates/check-dead-bash.ts"

DEFAULT_PACKAGE_JSON = ROOT / "package.json"
DEFAULT_MANIFEST = ROOT / "scripts" / "ci-runner" / "manifest.ts"


def delegation_verdict(
    package_json: pathlib.Path | None = None, manifest: pathlib.Path | None = None
) -> str | None:
    """None when the real-tree scan is still registered, else the reason it is not.

    A clause-by-clause transcription of the twin's shell function, in its order. Each clause names a DIFFERENT way the delegate can vanish, and the control asserts each one is caught FOR ITS OWN REASON: a control that fires for the wrong reason keeps firing after the defect it names is fixed.
    """
    pkg = DEFAULT_PACKAGE_JSON if package_json is None else package_json
    man = DEFAULT_MANIFEST if manifest is None else manifest

    lines = [
        line
        for line in pkg.read_text(encoding="utf-8").splitlines()
        if '"%s":' % DELEGATE_KEY in line
    ]
    if not lines:
        return 'package.json has no "%s" script, so the real-tree scan runs NOWHERE' % DELEGATE_KEY
    line = "\n".join(lines)
    if DELEGATE_LEAF not in line:
        return '"%s" no longer runs %s; it runs:%s' % (DELEGATE_KEY, DELEGATE_LEAF, line)
    # A fixture-rooted invocation is not the real-tree scan. `DEAD_BASH_ROOT` is exactly how this file points the gate at a temp tree, so a delegate that sets it would be scanning a fixture while looking like full coverage.
    if "DEAD_BASH_ROOT" in line:
        return '"%s" sets DEAD_BASH_ROOT, so it scans a fixture and not the real tree:%s' % (
            DELEGATE_KEY,
            line,
        )

    entry = manifest_entry(man, DELEGATE_KEY)
    if entry is None:
        return (
            "scripts/ci-runner/manifest.ts has no entry with id '%s', so the npm key "
            "exists but nothing schedules it" % DELEGATE_KEY
        )
    if "gate: true" not in entry:
        return (
            "manifest entry '%s' is not gate: true, so a full run never selects it" % DELEGATE_KEY
        )
    if DELEGATE_LEAF not in entry:
        return "manifest entry '%s' no longer declares %s among its leaves" % (
            DELEGATE_KEY,
            DELEGATE_LEAF,
        )
    return None


def manifest_entry(manifest: pathlib.Path, key: str) -> str | None:
    """The manifest block for `key`, bounded by its own two-space closing brace.

    BOUNDED BY THE BRACE and not by a fixed line count, which is the twin's awk program: a `grep -A <n>` window either misses a reordered field or bleeds into the NEXT entry and reads its `gate: true` as this one's.
    """
    needle = "id: '%s'," % key
    out: list[str] = []
    inside = False
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if needle in line:
            inside = True
        if inside:
            out.append(line)
            if line == "  },":
                break
    return "\n".join(out) if out else None


def make_fixture(root: pathlib.Path) -> None:
    """One referenced script and one referencing caller, so the tree is healthy before each case bends exactly one thing."""
    for sub in (".ci/scripts/lib", ".ci/policy", "scripts"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / ".ci/scripts/lib/helpers.sh").write_text(
        '#!/bin/bash\nlive_helper() {\n    echo "used"\n}\n', encoding="utf-8"
    )
    (root / "run.sh").write_text(
        "#!/bin/bash\nsource .ci/scripts/lib/helpers.sh\nlive_helper\n"
        "bash .ci/scripts/lib/helpers.sh\n",
        encoding="utf-8",
    )
    # run.sh needs an inbound reference of its own, or it is legitimately an orphan and every case below inherits that finding. In the real repo the docs name it; here a README plays that role.
    (root / "README.md").write_text("Run the entrypoint with `./run.sh`.\n", encoding="utf-8")


def run_gate(root: pathlib.Path) -> harness.RunResult:
    """Drive the real detector against a fixture root."""
    npx = harness.require_tool(
        "npx",
        "install node (the lane's setup-workspace step provides it); tsx is resolved through npx",
    )
    return harness.run(
        [npx, "tsx", str(GATE)], cwd=ROOT, env={"DEAD_BASH_ROOT": str(root)}, timeout=600
    )


def allowlist(root: pathlib.Path, body: str) -> None:
    (root / ".ci/policy/.dead-bash-allowlist").write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------


def test_real_tree_scan_is_delegated(gate):
    """The real-tree direction, asserted to still be SOMEBODY's job."""
    why = delegation_verdict()
    if why:
        gate.log_fail("the real-tree scan is no longer covered: %s" % why)
    gate.log_pass("the real-tree scan is delegated to a registered check:ci-dead-bash gate")


def test_delegation_assertion_fires(gate):
    """CONTROL, in the file's own both-ways style.

    An assertion that cannot fail is worth what no assertion is worth, and "the delegate quietly vanished" looks exactly like "the delegate ran and passed". Four planted defects, each of which must be caught, and each of which must be caught FOR ITS OWN REASON.
    """
    pkg_text = DEFAULT_PACKAGE_JSON.read_text(encoding="utf-8")
    man_text = DEFAULT_MANIFEST.read_text(encoding="utf-8")
    with harness.temp_dir() as t:
        missing = t / "pkg-missing.json"
        missing.write_text(
            "\n".join(line for line in pkg_text.splitlines() if '"%s":' % DELEGATE_KEY not in line),
            encoding="utf-8",
        )
        # EVERY PLANT IS PROVEN TO HAVE LANDED. A substitution that quietly matched nothing leaves the control running against unmutated source, which is a green that proves nothing.
        gate.assert_eq(
            missing.read_text(encoding="utf-8") == pkg_text, False, "the key-removal plant landed"
        )

        repointed = t / "pkg-repointed.json"
        old_script = '"%s": "tsx %s"' % (DELEGATE_KEY, DELEGATE_LEAF)
        if old_script not in pkg_text:
            gate.log_fail(
                "PLANT COULD NOT LAND: package.json no longer spells the delegate as %r, so "
                "the repointing control would run against unmutated source" % old_script
            )
        repointed.write_text(
            pkg_text.replace(
                old_script, '"%s": "tsx scripts/check-something-else.ts"' % DELEGATE_KEY
            ),
            encoding="utf-8",
        )

        noentry = t / "manifest-noentry.ts"
        noentry.write_text(
            man_text.replace("id: '%s'," % DELEGATE_KEY, "id: '%s-renamed'," % DELEGATE_KEY),
            encoding="utf-8",
        )
        gate.assert_eq(
            noentry.read_text(encoding="utf-8") == man_text, False, "the id-rename plant landed"
        )

        gatefalse = t / "manifest-gatefalse.ts"
        gatefalse.write_text(_flip_gate_false(gate, man_text), encoding="utf-8")

        why = delegation_verdict(package_json=missing)
        gate.assert_contains(
            str(why), "runs NOWHERE", "a package.json with the key REMOVED must fail, and name it"
        )
        why = delegation_verdict(package_json=repointed)
        gate.assert_contains(
            str(why), "no longer runs", "a key repointed at another script must fail, and say so"
        )
        why = delegation_verdict(manifest=noentry)
        gate.assert_contains(
            str(why),
            "no entry with id",
            "an unregistered key must fail: an npm key nothing schedules is not coverage",
        )
        why = delegation_verdict(manifest=gatefalse)
        gate.assert_contains(
            str(why), "not gate: true", "a gate: false entry must fail: a full run never selects it"
        )
    gate.log_pass("the delegation check fires on all four ways the real-tree scan can go uncovered")


def _flip_gate_false(gate, source: str) -> str:
    """`gate: true` -> `gate: false` inside the delegate's entry ONLY.

    Bounded by the entry's own closing brace for the same reason `manifest_entry` is: an unbounded replace would flip a neighbouring gate and the control would then be measuring the wrong entry.
    """
    out: list[str] = []
    inside = False
    done = False
    for line in source.splitlines():
        if "id: '%s'," % DELEGATE_KEY in line:
            inside = True
        emitted = line
        if inside and not done and "gate: true," in line:
            emitted = line.replace("gate: true,", "gate: false,")
            done = True
        if line == "  },":
            inside = False
        out.append(emitted)
    if not done:
        gate.log_fail(
            "PLANT COULD NOT LAND: no `gate: true,` inside the '%s' entry, so the "
            "gate-false control would run against unmutated source" % DELEGATE_KEY
        )
    return "\n".join(out) + "\n"


def test_fires_on_unused_function(gate):
    with harness.temp_dir() as t:
        make_fixture(t)
        with (t / ".ci/scripts/lib/helpers.sh").open("a", encoding="utf-8") as fh:
            fh.write("orphan_fn() {\n    echo dead\n}\n")
        result = run_gate(t)
        gate.assert_exit(1, result, "an uncalled function must fail the gate")
        gate.assert_contains(result.combined, "orphan_fn", "names the dead function")
        gate.assert_contains(result.combined, "helpers.sh:", "cites file:line")
    gate.log_pass("fires on an unused shell function")


def test_no_false_positive_on_cross_file_call(gate):
    with harness.temp_dir() as t:
        make_fixture(t)
        result = run_gate(t)
        gate.assert_exit(0, result, "a function called from another file is not dead")
        gate.assert_not_contains(result.combined, "live_helper", "cross-file call is recognised")
    gate.log_pass("does not condemn a function called from another file")


def test_fires_on_orphan_file(gate):
    with harness.temp_dir() as t:
        make_fixture(t)
        (t / "scripts/orphan-script.sh").write_text(
            "#!/bin/bash\necho nobody-calls-me\n", encoding="utf-8"
        )
        result = run_gate(t)
        gate.assert_exit(1, result, "an unreferenced script must fail the gate")
        gate.assert_contains(result.combined, "orphan-script.sh", "names the orphan file")
    gate.log_pass("fires on an orphaned shell script")


def test_glob_root_exempts_a_directory(gate):
    with harness.temp_dir() as t:
        make_fixture(t)
        (t / "scripts/globbed").mkdir(parents=True, exist_ok=True)
        (t / "scripts/globbed/test-thing.sh").write_text(
            "#!/bin/bash\necho found-by-glob\n", encoding="utf-8"
        )
        allowlist(
            t,
            "# BLOCKER: expanded as a glob by a runner that never names these files "
            "individually\nglob:scripts/globbed/\n",
        )
        result = run_gate(t)
        gate.assert_exit(0, result, "a glob-discovered file must not be reported")
        gate.assert_not_contains(
            result.combined, "test-thing.sh", "glob root exempts the directory"
        )
    gate.log_pass("glob: root exempts glob-discovered scripts")


def test_dispatch_prefix_exempts_functions(gate):
    with harness.temp_dir() as t:
        make_fixture(t)
        with (t / ".ci/scripts/lib/helpers.sh").open("a", encoding="utf-8") as fh:
            fh.write("phase_alpha() {\n    echo dispatched\n}\n")
        allowlist(
            t,
            '# BLOCKER: assembled at runtime as "phase_$name" so no static call site can '
            "exist for these\ndispatch:phase_\n",
        )
        result = run_gate(t)
        gate.assert_exit(0, result, "a dynamically dispatched function must not be reported")
        gate.assert_not_contains(
            result.combined, "phase_alpha", "dispatch prefix exempts the function"
        )
    gate.log_pass("dispatch: prefix exempts dynamically dispatched functions")


def test_manual_entry_exempts_a_file(gate):
    with harness.temp_dir() as t:
        make_fixture(t)
        (t / "scripts/manual-tool.sh").write_text(
            "#!/bin/bash\necho operator-runs-this\n", encoding="utf-8"
        )
        allowlist(
            t,
            "# BLOCKER: run directly by the operator when a manual reconciliation is "
            "needed, never from CI\nmanual:scripts/manual-tool.sh\n",
        )
        result = run_gate(t)
        gate.assert_exit(0, result, "an allowlisted manual entrypoint must not be reported")
        gate.assert_not_contains(
            result.combined, "manual-tool.sh:", "manual entry exempts the script"
        )
    gate.log_pass("manual: entry exempts an operator-invoked script")


def test_rejects_low_effort_blocker(gate):
    with harness.temp_dir() as t:
        make_fixture(t)
        allowlist(t, "# BLOCKER: tbd\nglob:scripts/\n")
        result = run_gate(t)
        gate.assert_exit(1, result, "a low-effort BLOCKER must be rejected")
        gate.assert_contains(
            result.combined, "BLOCKER validation failed", "shared validator rejects it"
        )
    gate.log_pass("low-effort BLOCKER on the allowlist is rejected")


def test_rejects_unknown_entry_kind(gate):
    with harness.temp_dir() as t:
        make_fixture(t)
        allowlist(
            t,
            "# BLOCKER: an entry with no recognised prefix must be refused rather than "
            "silently ignored\nscripts/whatever.sh\n",
        )
        result = run_gate(t)
        gate.assert_exit(1, result, "an entry with no kind prefix must fail")
        gate.assert_contains(result.combined, "must start with", "explains the required prefixes")
    gate.log_pass("entry without glob:/dispatch:/manual: prefix is rejected")


def test_empty_tree_is_vacuous(gate):
    """ANTI-VACUITY, driven through the real detector: a scan that saw no input must REFUSE rather than report the cleanest run in its history."""
    with harness.temp_dir() as t:
        result = run_gate(t)
        gate.assert_exit(1, result, "a tree with no shell files must fail, not pass vacuously")
        gate.assert_contains(result.combined, "ZERO shell files", "says the gate is blind")
    gate.log_pass("empty tree fails as vacuous")


def test_the_delegate_key_resolves_to_a_real_npm_script(gate):
    """ADDED BY THE PORT. `delegation_verdict` reads package.json as TEXT, exactly as the twin's grep does, which is what keeps the two sides comparable. Text is not JSON, though: a key inside a comment-like string, or a duplicated `scripts` block, would satisfy the grep and not the runtime. This reads the same file through a JSON parser and requires the two answers to agree.

    A manifest id is NOT an npm script, and this repo has paid for that confusion: `npm run --silent <id-that-is-not-a-key>` exits 1 with zero bytes on both streams, which is indistinguishable from a gate failing for a real reason.
    """
    data = json.loads(DEFAULT_PACKAGE_JSON.read_text(encoding="utf-8"))
    scripts = data.get("scripts") or {}
    if DELEGATE_KEY not in scripts:
        gate.log_fail(
            "package.json's parsed `scripts` object has no %r key, though the text scan "
            "found one. The real-tree scan is not runnable." % DELEGATE_KEY
        )
    gate.assert_contains(
        scripts[DELEGATE_KEY], DELEGATE_LEAF, "the parsed value must still run the detector"
    )
    gate.log_pass(
        "the delegate resolves as a real npm script (%r -> %r)"
        % (DELEGATE_KEY, scripts[DELEGATE_KEY])
    )
