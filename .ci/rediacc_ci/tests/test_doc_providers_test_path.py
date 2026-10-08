"""`isTestPath` in `scripts/lib/doc-providers.ts`, the heuristic that ranks a test namer after every program in the json-inventory row.

The function is not exported (`lint:unused` refuses an export nothing imports), so the regex literals are read out of its body and run here; they use only syntax Python's `re` shares. Review findings fe97b255.1 (a program named `test-*.ts` was ranked as a test) and fe97b255.2 (no unit test over the `tests/`, `__tests__`, `.test.` and `.spec.` branches).
"""

import re

from rediacc_ci import paths

SOURCE = (paths.repo_root() / "scripts/lib/doc-providers.ts").read_text(encoding="utf-8")


def _patterns() -> list[re.Pattern[str]]:
    body = re.search(r"const isTestPath = \(f: string\): boolean =>\n(.*?);\n", SOURCE, re.DOTALL)
    assert body, "isTestPath definition not found in doc-providers.ts"
    literals = re.findall(r"^\s*/(.+)/\.test\(f\)", body.group(1), re.MULTILINE)
    assert len(literals) >= 3, (
        "expected at least the directory, basename and .test/.spec branches, got %r" % literals
    )
    return [re.compile(lit.replace("\\/", "/")) for lit in literals]


def is_test_path(path: str) -> bool:
    return any(p.search(path) for p in _patterns())


def test_tests_are_test_paths():
    for path in [
        ".ci/rediacc_ci/tests/gates/test_gate_docs_gen.py",
        "packages/cli/tests/unit/x.ts",
        "packages/cli/src/__tests__/x.ts",
        "scripts/lib/foo.test.ts",
        "scripts/lib/foo.spec.mjs",
        ".ci/rediacc_ci/deploy/test_d1_migrations.py",
        ".claude/hooks/stop/test-planrec.py",
        "packages/www/scripts/test-tutorial-player-release-gate.js",
        ".ci/breakpoint/scripts/test-breakpoint-lifecycle.sh",
        "test/foo.ts",
    ]:
        assert is_test_path(path), path


def test_programs_named_test_are_not_test_paths():
    for path in [
        "packages/shared/src/config/test-credentials.ts",
        "packages/shared/src/config/test-prefixes.ts",
        "scripts/lib/test-runner.ts",
        "scripts/lib/suppression-liveness.ts",
        "scripts/gates/check-pr-condition-ledger.ts",
        "scripts/lib/contest/x.ts",
        "scripts/lib/latest.ts",
    ]:
        assert not is_test_path(path), path
