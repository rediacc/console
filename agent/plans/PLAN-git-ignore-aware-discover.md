# PLAN: make discover() git-tracked-only so a local machine's untracked files cannot contaminate a committed baseline
Status: compacted
First-Seen: 2026-09-20
Owner: d778be9d
Full-Text-Blob: 665806c8207762ab129e4425a19794d7359cef65
Record-Sig: 07726f99

## Why
discover() in prose-style.py enumerated the gate's corpus with a raw os.walk, capturing untracked and gitignored files on the developer's machine. Since --write-baseline freezes this corpus into .ci/config/prose-style-baseline.json (a committed, shrink-only artifact), CI then had to satisfy findings on files that never appeared in fresh checkouts, reds that could not drain. The
incident surfaced in commit 944aa6210, which froze six ignored files from .claude/hooks/context/state and required a per-directory exclude workaround; the class repeats on any other untracked or ignored file.

## Outcome
discover() now derives its corpus from git ls-files, rejecting non-checkouts outright. Corpus shrinks by four paths (2499 → 2495 files), all untracked or ignored. The committed baseline is unmodified (no rewrite required). All eight new tests (T1–T8, including T6 amended to use git-initialized fixture) confirmed to go red and green as expected, and the three new selftest controls
confirmed both directions. Verification block ran: 2495 files, 3542 baselined unchanged, baseline file untouched by git status.

## Lessons
- A committed artifact that describes its own corpus must derive that corpus from git, not a filesystem walk — the tree a checkout holds is never the tree a machine holds.
- Untracked-but-not-ignored contamination is the harder half: exclude_dirs workarounds catch gitignored paths on one machine only, missing brand-new files never git-added, which is why all three sibling baseline gates use git, not filesystem walks.
- os.walk's order is filesystem-dependent: two runs on two machines disagree for no reason a reader can act on, so discover() must return sorted output even when drawing from git.
- Explicit targets bypass discover() — a file named on the command line is scanned regardless of git status, because creation-time untracked files are correct. The broad-corpus-vs-named distinction is structural.

## Boxes
- [x] Add gitx to the rediacc_ci import at .ci/rediacc_ci/quality/prose_style.py:81; add import tempfile.
    (record) sig=9bcdb969 done=5affddc0c
- [x] Replace .ci/rediacc_ci/quality/prose_style.py:696-723 with tracked_files(), under_excluded_dir() and the git-driven discover() (section 4b).
    (record) sig=269de465 done=5affddc0c
- [x] Wrap the discover() call at .ci/rediacc_ci/quality/prose_style.py:962 in try/except RuleError -> log.error + return 1 (section 4c).
    (record) sig=e91547d1 done=5affddc0c
- [x] Same wrap at .ci/rediacc_ci/quality/prose_style.py:1164 in run_reflow (section 4d).
    (record) sig=b6dda857 done=5affddc0c
- [x] Delete ".claude/hooks/context/state" from exclude_dirs, .ci/config/prose-style-rules.json:85; optionally add the exclude_why paragraph (section 4e).
    (record) sig=bee9dcb8 done=5affddc0c
- [x] Add the six --selftest controls (section 6c).
    (record) sig=d6222669 done=5affddc0c
- [x] Add _repo() and tests T1-T5, T7, T8 to .ci/rediacc_ci/tests/test_quality_prose_style.py; amend T6 (test_zero_files_is_a_failure) to git-init its fixture.
    (record) sig=c170ccd9 done=5affddc0c
- [x] Prove the new tests can go red by temporarily restoring the os.walk body, then restore the fix (section 6d).
    (record) sig=700ea983 done=5affddc0c
- [x] Run the verification block (section 7). Confirm 2499 -> 2495 file(s), 3542 baselined unchanged, baseline file untouched by git status.
    (record) sig=48c5e37f done=5affddc0c
- [x] Commit referencing worklist item #779ae9c1 and 944aa6210 -- this is the real fix that commit deferred.
    (record) sig=eed39eb9 done=5affddc0c

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T16:40:32Z
Boxes: 10 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: .ci/rediacc_ci/quality/prose_style.py, .ci/config/prose-style-rules.json, .ci/rediacc_ci/paths.py, .ci/rediacc_ci/quality/plant_proofs.py, .ci/rediacc_ci/quality/python_env_registry.py, .ci/scripts/quality/check_language_policy.py, .ci/rediacc_ci/gitx.py, .ci/rediacc_ci/quality/dead_python.py, .ci/rediacc_ci/tests/test_gitx.py, .ci/rediacc_ci/quality/editorconfig.py, .ci/rediacc_ci/quality/ci_scans_tracked_paths.py
Gates: none
Why-Source: model
Read-History: `git show 665806c8207762ab129e4425a19794d7359cef65` recovers the text; `git log --find-object=665806c8207762ab129e4425a19794d7359cef65 --all` names the commit

## History
- 2026-09-20T16:40:32Z compacted by d778be9d from `done` (record-sig 07726f99)
