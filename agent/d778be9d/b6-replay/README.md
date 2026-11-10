# B6 reviewer replay (PLAN-experience-feedback B6)

The harnesses behind the replay quoted under box B6. `b6_pick.py` chose the 20 commits (`b6_cands.json`); `b6_replay*.py` run the current reviewer prompt, `b6_oldctl*.py` the prompt at `d45d4a121f~1`, loaded from a `/tmp/oldroot` copy of `.claude/hooks/stop/` (the old module derives its root from its own path); `b6_score*.py` match findings as same file and line within 8. Each script runs from the repo root and writes its output JSON to `/tmp`.
