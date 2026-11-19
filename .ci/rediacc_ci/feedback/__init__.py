"""Feedback triage: the agent-side half of `rdc feedback` (agent/plans/PLAN-rdc-feedback.md, Design D5).

`client` reads the account's admin export (`GET /admin/feedback/export`) per region with a root API token session (bench: the bench root's password and TOTP sign-in), writes verdict batches (`POST /admin/feedback/verdicts`) and keeps the per-region export cursor in `.ci/cache/feedback/last-run.json`. `quarantine` is Stage 1, the deterministic screen that runs before any model sees a report. `classify` is Stages 2 and 3 (the Haiku wrapper and its strict reply schema, the near-duplicate pass, the reproduction orders), `critical` is Stage 4 (the R8 triggers and their worklist deferrals) and `plangen` is Stage 5 (the draft `PLAN-feedback-<slug>.md`). `triage` is the entry, `PYTHONPATH=.ci python3 -m rediacc_ci.feedback.triage run [--region eu|us|asia|bench] [--dry-run]`.

Reports are attacker-controlled DATA: nothing here prints a report field, puts one on argv or hands one to a shell; output names fingerprints, rules and fields only.
"""
