"""A shell subject a gate test reads and pulls single functions out of.

WHY IT IS SHARED, AND BETWEEN EXACTLY THESE CALLERS. Three gate tests -- `test_gate_installmethods_container_version.py`, `..._linuxpkg_idiom.py` and `..._manifest.py` -- each carried a byte-identical `source(gate)` and a byte-identical `extract_fn(gate, name)`, thirteen lines apiece, differing only in which `.sh` file `TARGET` names. `check:ci-shape-duplication` reported that pair
as four overlapping findings, the largest thirteen lines across three files, the moment the gate-test family entered its corpus.

Unlike an assertion message, there is nothing per-case in those thirteen lines: the refusal sentence is word-for-word the same in all three, because it says the same thing in all three ("renamed or removed, so these tests would check nothing"). That is the test this repo applies before folding anything -- a per-case CLAIM stays at its call site, a shared MECHANISM does not.

THE TARGET IS AN ARGUMENT, NOT A CONSTANT, for the reason `harness.watchdog_subject` gives for taking its path: a caller pointing at a fixture copy must get the same refusal, rather than silently checking the real file while believing it checked the copy.

WHAT IT DOES NOT DO. It does not parse shell. `shell_fn` matches an opening line
and a column-1 `}`, which is what `awk "/^name\\(\\) \\{/,/^\\}/"` does in the bash
twins these tests were ported from, and the subjects are formatted that way. A brace counter would be a second thing to be wrong about, and it would disagree
with the twin.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness


class Subject:
    """One shell file under test, read through the gate so a miss is LOUD."""

    def __init__(self, target: pathlib.Path) -> None:
        self.target = target

    def text(self, gate) -> str:
        """The subject's source. A missing subject is a refusal, not an empty string."""
        if not self.target.is_file():
            gate.log_fail("target not found: %s" % self.target)
        return self.target.read_text(encoding="utf-8")

    def shell_fn(self, gate, name: str) -> str:
        """The body of `name()` from the subject, or a LOUD refusal.

        Every extraction is checked for emptiness: a renamed or deleted function must make the caller REFUSE, not quietly test nothing.
        """
        body = harness.block_from(self.text(gate), "%s() {" % name)
        if not body:
            gate.log_fail(
                "%s() not found in %s -- renamed or removed, so these tests would check nothing"
                % (name, paths.relative_to_root(self.target))
            )
        return "\n".join(body)
