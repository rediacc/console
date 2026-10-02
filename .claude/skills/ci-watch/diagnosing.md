# Diagnosing a red, beyond the tracer


**"It passed earlier" is NOT a classifier.** That shortcut lived here and was wrong: on 2026-09-01 a gate green on five earlier runs of the same branch went red five times and was a real mid-branch regression. Four re-runs bought that lesson.

1. **Download the artifact first.** Where a gate uploads one, its `summary.json` names
the failure mode in one command. Code-reading only guesses.
2. **Find the last green at STEP level**, not run level -- a cancelled run hides passing
steps, so the run list places the boundary wrong.
3. **Read the window, including when it is empty:**

       git log --oneline <last-green>..HEAD       # what could have done it
       git log --oneline -- <the file that broke> # has it broken before, and why

Only docs in the window is affirmative evidence for an environmental cause.
4. **Reproduce with `CI=true` set.** That alone changes subprocess output (TRAPS.md, "a
gate that fails ONLY in CI may be matching bytes that CI coloured"), so "it passes locally" is not evidence against a real bug.
