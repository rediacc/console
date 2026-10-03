# PLAN: program state lives in the repo, out-of-repo paths are derived, and a dead checklist owner is asked about
Status: approved
Depends-On: no-dep -- the checklist parser, /handoff and wl_core.projects_dir all exist today
Owner: d778be9d
Updated: 2026-10-03
Priority: P1 -- the operator packaged it as the next PR after #592 (/ask 2026-10-03)
Concurrency: exclusive -- it rewrites /handoff and the checklist adjudication every session's stop reads
Owns: .claude/commands/handoff.md, .claude/commands/pr-babysit.md, .claude/agents/pr-babysitter.md, .claude/hooks/stop/wl_checklist.py, agent/programs/*/CHECKLIST.md, agent/programs/*/README.md, agent/programs/*/state/**

Operator rulings, 2026-10-03 (/ask): "it reveals that it's dangerous to keep such things outside of repo. investigate why that happened. Then come with options"; picked "Program state into the repo" and "Derive the projects dir"; packaging "Next PR, its own plan". Earlier the same day: a checklist owner "should be aware if the other session is alive or not. the ownership transfer should be asked to the user if the other session(s) are gone/dead".

## Problem

The www-simplification handoff (`Status: done`, `Owner: e6500e92`) reports drift on every clean stop of every session in this tree. Its only failing deliverable, d7, is `~/.claude/projects/-home-muhammed-monorepo-console/programs/www-simplification/MANIFEST.md`, a file on the machine the repo left. The owner has no transcript and no worklist events here, so nothing can ever settle it, and nobody is asked.

## Root causes

R1. **/handoff puts program state outside git.** `.claude/commands/handoff.md:30`, `:41` and `:73` seed MANIFEST.md, `reports/` and `checkpoints/` under `~/.claude/projects/-home-muhammed-monorepo-console/programs/<slug>/` and list the MANIFEST as a deliverable by that absolute `~` path. Three tracked checklists followed it: www-simplification d7, www-round5 d9 (`-home-muhammed-console`), clarity-round6 d9 (`-home-developer-console`). The slug in the command is the OLD machine's, so the instruction was wrong on this machine from the day the repo moved.

R2. **The checker accepts it.** `wl_checklist.verify_files` (`.claude/hooks/stop/wl_checklist.py:183`) expands `~` and accepts absolute paths, so such a deliverable verifies on exactly one machine. (Refusing that shape outright was offered and not picked; this plan removes the instruction that produced it instead.)

R3. **Other out-of-repo paths are hard-coded to the old machine.** `.claude/agents/pr-babysitter.md:168` and `.claude/commands/pr-babysit.md:70` name `~/.claude/projects/-home-muhammed-monorepo-console/reports/...`. The code already derives the right directory (`wl_core.projects_dir`, `.claude/hooks/stop/wl_core.py:286`; `wl_roundlog.roundlog_path`); only the prose is stale.

R4. **A foreign checklist's owner is never asked about.** `_adjudicate`'s `done` branch (`wl_checklist.py`, the `status == "done"` arm) emits `cl-foreign` with no liveness check at all; the `producing` and wave arms call `_adopt_hint`, which reads `wl_store.owner_age_hours` and treats an owner with no transcript here as alive. An owner that left nothing on this machine is therefore reported forever and the operator is never asked to transfer it.

## Design

D1. **Program state is `agent/programs/<slug>/state/`.** /handoff seeds `state/MANIFEST.md`, `state/reports/` and `state/checkpoints/` there (committed like any program file) and lists the deliverable as `file:agent/programs/<slug>/state/MANIFEST.md`. The execution-guide wording that names the state dir follows.

D2. **The three existing checklists are repointed.** clarity-round6's local state (`~/.claude/projects/-home-developer-console/programs/clarity-round6/`: MANIFEST.md, 13 reports, checkpoints, about 1 MB) is copied into `agent/programs/clarity-round6/state/`. www-simplification and www-round5 have no state on this machine: their deliverable points at a new `state/MANIFEST.md` that records where the original lived and that it did not survive the move, so the checklist tells the truth rather than staying red.

D3. **Paths that stay outside are derived, never typed.** pr-babysitter.md and pr-babysit.md name `<projects-dir>/reports/...` and define `<projects-dir>` once as what `wl_core.projects_dir` returns for the checkout (with the one-line command that prints it).

D4. **A checklist owner that is not live is a question for the operator, once.** Every foreign-owner arm of `_adjudicate` reads `wl_store.session_liveness` (live/idle/remote/unknown). `live` keeps today's advisory. Anything else raises `cl-owner:<slug>`, telling the session to ask the operator with AskUserQuestion (adopt: Owner becomes this session; supersede: Status superseded; leave) and to record the answer by ticking a worklist item carrying `cl-owner:<slug>`. A ticked item silences it, the same store-backed evidence the `pr:<n>/threads` box uses.

## Tasks

- [ ] PS1 /handoff seeds state in-repo (D1). Files: .claude/commands/handoff.md. Acceptance: `grep -c '~/.claude/projects' .claude/commands/handoff.md` prints 0 and `npm run check:ci-prose-style` exits 0.
- [ ] PS2 Repoint the three checklists and copy clarity-round6's state (D2). Files: agent/programs/{www-simplification,www-round5,clarity-round6}/{CHECKLIST.md,README.md,state/**}. Acceptance: `wl_checklist._deliverable_rows` reports no missing deliverable for any of the three.
- [ ] PS3 Derive the projects dir in the prose (D3). Files: .claude/agents/pr-babysitter.md, .claude/commands/pr-babysit.md. Acceptance: `git grep -n 'home-muhammed' -- .claude/agents .claude/commands` prints nothing.
- [ ] PS4 Ask about a non-live checklist owner (D4). Files: .claude/hooks/stop/wl_checklist.py, .claude/hooks/stop/worklist_messages.py, the ladder and stand-down keep-lists if the key needs them. Acceptance: the tests below.
- [ ] PS5 Tests. A fixture checklist owned by a session with no artifacts raises `cl-owner:<slug>`; the same owner with a fresh `.lastevent` stays an advisory (CONTROL); a ticked `cl-owner:<slug>` item silences it; a mutation that skips the liveness read fails the first case. Acceptance: pytest on the new cases plus the stop-hook suite at rc 0.
