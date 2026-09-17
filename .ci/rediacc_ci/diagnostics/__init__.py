"""Ported best-effort diagnostics tools (not quality gates).

Everything here runs AFTER something else has already failed, to recover evidence the failure's own output never reached. None of it asserts anything and none of it may fail the job it runs in -- a diagnostics collector that turns a real failure into a confusing collector failure would replace the thing the operator came to read. `quality/` is for CI CHECKS that can and should fail
a run; this subpackage is deliberately not that.

Named `diagnostics/` rather than `test/` (which would mirror the bash source directory, `.ci/scripts/test/`) to avoid reading as the pytest `tests/`
package one directory over. The bash twins are NOT deleted (W7 phase-5
decision, same as every other subpackage here): both copies live side by side until a differential ledger over K distinct trees exists.
"""

__all__: list[str] = []
