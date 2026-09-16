"""Ported CI-workflow support scripts (`.ci/scripts/ci/`).

`profiler_panel` is a port of `.ci/scripts/ci/profiler/panel.sh`, the wrapper
the profiler action's post hook runs. It INVOKES `report.awk` rather than
reimplementing it: the aggregator is 439 lines of mawk-dialect arithmetic and a
second copy would be a second instrument. Its twin is still wired by literal
path at `.github/actions/profiler/index.js:33`, and by
`.ci/rediacc_ci/tests/gates/test_gate_profiler_report.py:57`, which drives
panel.sh to test report.awk; neither is repointed here.

`scope_reconcile_shadow` is a workflow step, not a registered quality gate:
its own comment calls it "polarity depends on SCOPE_MODE", and its failure
mode is an attested "could not verify a skip", not a code-quality finding.
The bash twin is NOT deleted (W7 phase-6 decision, same as `quality/`): both
copies live side by side until a differential ledger over K distinct trees
exists, per `scripts/lib/shadow-gate.ts`. `ci.yml:1781` wires the bash twin by
its literal path; neither this port nor its ledger repoints that step.
"""

__all__: list[str] = []
