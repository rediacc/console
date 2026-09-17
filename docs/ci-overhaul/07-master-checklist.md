# 07. The master checklist

One checklist, for every box in every one of the twelve workstreams. It is short on purpose: these are the questions that have actually caught damage in this program, not a general theory of good practice.

**It contains no phase list and no status column, and that is deliberate.** The phase list lives in the plan; a second copy here would be a hand-maintained artifact that goes stale, which is the exact defect [07-tooling-decisions.md](07-tooling-decisions.md) T-5 exists to abolish. Status is answered by running something, never by reading a tick somebody typed. Where a row below can
be answered by a command, the command is given and the command is the answer.

---

## Before the box starts

- [ ] **Record `git rev-parse HEAD`.** Other sessions commit to this checkout while you work.
      08 section 4 measures it: three release-signing commits and a rebase landed between one
      baseline measurement and the branch taken from it. The tree you measured is not
      necessarily the tree you are editing.
- [ ] **Read the file before assuming what it does.** Several boxes in this program found the
      artifact already built, already different from its description, or already fixed by a
      peer. A brief is a hypothesis about the tree.
- [ ] **Confirm your file ownership is disjoint from the other live writer.** At most two
      writing agents, with the exact file set stated in each prompt.

## While the box runs

- [ ] **Run the real thing, and read stdout and stderr SEPARATELY.** Output, exit-code and
      error-path defects are invisible to code reading and to mocked tests. A wrapper that
      swallows output, or progress text landing on the wrong stream, shows up only in the raw
      bytes.
- [ ] **Every control fires in BOTH directions.** A gate that has never been observed failing
      is a gate nobody has evidence for. Plant the defect, watch it go red, restore it, watch it
      go green, and assert the restore.
- [ ] **Exit 0 with zero PASS lines is a failure.** A check with nothing to check reports
      success it never earned. Refuse instead: name what it scanned and how many subjects it
      found, and fail when that is zero.
- [ ] **A floor is set-based or corpus-derived, never a hand-typed count** (08 section 6). If
      you are about to type a number into a check, ask what that check would say after half its
      subjects vanish.
- [ ] **A generated artifact ships its checker in the SAME change** (invariant 1). An emitter
      whose regeneration nobody verifies drifts from its source and is believed for weeks;
      rediacc/console#549 is the failure class.
- [ ] **Prose cites files and symbols, not line numbers** (T-8).
- [ ] **No em dashes in any authored text, in any language.**

## Before calling it done

- [ ] **Spot-check the artifact, not the report.** Including your own report from earlier in
      the session, and including every sub-agent's. Agent reports are accurate about intent and
      quietly wrong about placement.
- [ ] **Name the gates you ran and the ones you skipped.** Before calling a failure
      pre-existing or environmental, show that none of its findings are in files you touched.
- [ ] **Sweep the class, not the instance.** Before calling a bug fixed, grep for its siblings.
      One bad call site usually has several. Say what the sweep covered and what it found, even
      when the answer is nothing.
- [ ] **`npx tsx scripts/gen-docs.ts`** is green, or the drift is explained. Any box that
      changed the gate registry, the hook wiring, a `BLOCKER:` mechanism or the `.ci` tree has
      moved a derived region.
- [ ] **`npx tsx scripts/gen-docs.ts --diff-snapshot`** reports no DROPPED rows, or the drop is
      named row by row and justified. Additions are normal growth. Missing rows are the thing
      this program is most likely to do to itself.

      Worked example, the first time it fired for real (2026-09-06). It reported
      `DROPPED ci-tree: .ci/docker/tts`. That was a legitimate move in flight, not a loss: W10
      phase 3 had deleted `.ci/docker/tts/` on disk and created `.ci/media/tts/`, and because
      the providers enumerate from the git INDEX, the deletion was already invisible while the
      destination was not yet visible. Both halves resolve the moment the move reaches an
      index. **This is the shape most DROPPED rows will have, and it is also exactly the shape
      a real loss has**, which is why the row must be traced to a destination rather than waved
      off. `--list` names the same paths under "in the index, absent from the worktree", which
      is the fastest way to tell a half-applied move from a deletion.
- [ ] **The worklist item is ticked with evidence**, and the evidence is a command and its
      output rather than a claim.
- [ ] **Registration changes are reported to the root driver as exact before and after text**,
      not landed by hand. `package.json`, `scripts/ci-runner/manifest.ts` and
      `.github/workflows/ci-quality.yml` have one writer for the whole program, and a `--write`
      on 2026-09-05 silently deleted four hand-added steps.

## When the box found something it was not looking for

- [ ] **A workaround is a bug report.** If you routed around a command that printed nothing, a
      flag that misbehaved, or an error that explained nothing, say so with the exact command
      and the exact output.
- [ ] **The finding is fixed in the session that found it**, inline when it is small and local,
      through a written plan and a writer sub-agent when it is not. Filing an issue does not
      close a finding.
- [ ] **If the fix is in another writer's files, do not edit them.** Write the exact before and
      after text into the driver's proposal file and say so loudly in the report. A correction
      nobody can apply is not a correction.

---

## The four ways a green has lied in this program

Kept here because each one was found by asking what the instrument would print if it had not worked, and none of them was found by reading the code.

1. **The check that cannot fail.** `--list` returned 0 unconditionally, so a provider that
scanned the tree and found nothing printed `gates 0` and exited clean. Fixed by refusing a vacuous provider.
2. **The comparison that only inspects survivors.** `--diff-snapshot` looped over the LIVE
providers, so a provider deleted from the code was never compared to its record at all. Fixed by comparing over the union.
3. **The count that cannot see a swap.** A floor of 300 passes over 388 rows that lost 88, and
count-equality passes when 88 are swapped for 88 others. Fixed by recording membership.
4. **The instrument broken by its own workaround.** A `.git/index` copy taken while another
session was writing came out with 12 entries instead of 4,720, and running `ci:quick` under it turned 45 gates red at once. That has the shape of a tree-wide regression and is not one. Validate the copy against the real index before using it (08 section 5b).
