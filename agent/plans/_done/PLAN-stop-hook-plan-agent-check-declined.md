# PLAN: plan-agent Stop check (section 4 of the stop-hook rulings campaign), DECLINED
Status: superseded -- declined by operator ruling on worklist #373907ed; boxes kept open as decided-not-done, never to be ticked
Ruling: #373907ed
First-Seen: 2026-09-17
Owner: d778be9d
Updated: 2026-09-24

## Why

Moved out unchanged on 2026-09-24 from `agent/plans/PLAN-stop-hook-rulings-campaign.md` section 4. The operator's recorded answer on worklist #373907ed (tick note, 2026-09-23T14:31Z) reads: "build sections 1 (three deletions), 2+3 (ruling record + suppression), and 5 (big_pieces census); section 4 (plan-agent Stop check, always=True) explicitly declined". The boxes below are that declined design, kept as the record of what was proposed. Re-opening them needs a new ruling, not a status edit.

## 4. The planning agent per context: a Stop check

**Verdict: a Stop check, armed by the existing PostCompact epoch. Not PostCompact alone. Not
a cron.** PostCompact cannot refuse anything -- `.claude/hooks/context/epoch-reset.py:14`: "PostCompact has no decision control ... Exit 0, always." A printed requirement is a document, and `.claude/hooks/stop/wl_checks.py:4488` already says a document an agent can skip is not a control. A cron cannot express "per context" at all.

- [ ] Arm: add `planagent_due` and `planagent_armed_at` to the existing `save_state` at
      `.claude/hooks/context/epoch-reset.py:26`.
- [ ] Enforce: a new `plan-agent` Stop check, `always=True`.
- [ ] Disarm on UNFAKEABLE evidence: an index row written by
      `wl_report.handle_subagent_stop` (`.claude/hooks/stop/wl_report.py:646`, type recorded
      at `.claude/hooks/stop/wl_report.py:585`, index at `.claude/hooks/stop/wl_report.py:154`)
      with `session == me8`, `at >= planagent_armed_at`, and a planning `type`. The session
      does not write that row; the harness does.
- [ ] Two anti-nag rules, both required: never fire on the FIRST stop of an epoch, and never
      fire when the session has done no write work in the epoch.
- [ ] CONTROL in `.claude/hooks/stop/worklist-cases/25-first-touch.sh`: armed + write work +
      two stops blocks; a planning index row after the arm silences it; the SAME row stamped
      BEFORE the arm still blocks; armed with no write work is silent.
