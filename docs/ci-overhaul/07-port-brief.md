# 07. The port brief

Handed verbatim to every box that MOVES code: bash to Python, one directory to another, a monolith to modules. It is the extra obligation on top of [07-master-checklist.md](07-master-checklist.md), which every box carries regardless.

A port is the most dangerous shape of change in this program, and not for the reason people expect. The behaviour usually survives. What does not survive is everything the file knew that was not behaviour, and its loss is invisible in every diff, every test and every gate.

---

## 1. The comments are the payload

`.claude`'s guards are 52 percent comment bytes. `command-scan.sh` records six separate rounds of bypass findings in prose. Several gates carry the exact run id and date of the incident that produced them. A port that keeps the behaviour and summarises the prose has destroyed the only copy of WHY the behaviour is that shape, and the next session then simplifies away the line the
comment was guarding.

**THE RULE** (08 section 5c). Every ported file records, in the differential artifact its twin already produces, the comment-byte count of the original and of the port. A port whose comment bytes fall below 90 percent of the original's is refused. Docstrings count; a module docstring is the natural home for a file-header block.

**WHY A RATIO AND NOT A DIFF.** The prose must be allowed to change. `set -euo pipefail` needs explaining in bash and says nothing in Python, and a comment about an argument-splitting bug is meaningless once the arguments are a list. Demanding identical text forces agents to carry dead prose, which teaches the next reader a wrong model just as surely as deleting it. The ratio
permits rewriting and refuses wholesale loss.

**WHAT THE RATIO CANNOT SEE**, stated so a green is not read as more than it is. An agent can satisfy it by padding with generic prose while dropping the one paragraph that names a dated incident. So the artifact ALSO lists every line of the original matching a date, a run id, a commit sha or an issue number, and the reviewer confirms each survives somewhere. That list is short,
mechanical to produce, and is the part worth a human's eye.

## 2. Fidelity is asserted against the origin, not described

- A moved body is asserted byte-for-byte against its source while both copies coexist. The
media extraction does this per module and it is the reason that port is checkable.
- A behavioural port carries a DIFFERENTIAL over a corpus of real inputs, not a unit test over
invented ones. The corpus is committed. `command-scan.sh` is ported against at least 320 captured strings for exactly this reason.
- A differential that passes on an empty corpus has proved nothing. Assert the corpus size is
non-zero and that at least one case in it exercises the failure path.

## 3. What a port must not quietly do

- **Do not descope.** Once a comprehensive change is approved, a piece that turns out hard does
not become a stub, a TODO or a follow-up issue. If something genuinely cannot be done, say which piece and why, out loud, in the report.
- **Do not add compatibility theater.** There is one operator and no external consumers. Fix
the root cause. No migration commands, no deprecation windows, no dual code paths preserving behaviour nobody depends on.
- **Do not leave a gate where the binder cannot see it** (08 section 5d). `scripts/gate-bind.ts`
enumerates with `git ls-files` over declared prefixes, so a gate outside them can carry a well-formed header and be silently unregistered, which is worse than unregistered because nothing reports the absence. Either widen the scan or move the file. Never leave a header that does nothing.
- **Do not conclude a header is broken before checking git can see the file.** `ls-files` reads
the INDEX, so a NEW file that is not yet in one is invisible for the same reason. Two headers appeared to do nothing on 2026-09-06 for exactly this.

## 4. Verifying a port that is not committed yet

This program keeps work uncommitted, and that collides with the class of gates that enumerate through `git ls-files`. They read the index, not the working tree, so a deletion that is real on disk but absent from the index makes them either crash or, worse, pass while still counting the file they were meant to notice. `check-shell-declared-commands.ts` crashed on six unstaged
deletions and only told the truth once the deletions were visible to an index.

The technique, which never touches the real index:

1. Copy `.git/index` to the scratchpad and point `GIT_INDEX_FILE` at the copy.
2. **VALIDATE THE COPY BEFORE USING IT.** Compare `git ls-files | wc -l` under the copy against
the same count under the real index, and refuse it if they differ by more than the paths you deliberately added. `cp` is not atomic against a concurrent writer, and a truncated copy does not announce itself. One taken mid-write held 12 entries instead of 4,720, and running `ci:quick` under it turned 45 gates red at once.
3. `git update-index --force-remove` each deleted path in the copy.
4. Run the affected gates with that variable set, then delete the copy.

Two cautions. Gates that build their own fixture trees must run WITHOUT the variable or it leaks into the fixture and they fail for the wrong reason. And a gate that reads the working tree rather than the index needs none of this, so establish which kind you have first.

Corollary for reviewers: a green gate run over unstaged deletions is not evidence until you know which side of that line the gate sits on.

## 5. The record the port leaves behind

Every port box ends with, in its report and not only in the diff:

- the comment-byte ratio, both raw numbers;
- the dated-and-cited-line list, and where each one now lives;
- the differential artifact path and the corpus size;
- the exact registration text for any file with a single writer, quoted before and after;
- the `--diff-snapshot` verdict, with any DROPPED row named and justified;
- every finding walked past, with the exact command and the exact output.


## 6. The test split, as it stands

A port moves a test file from one runner to another, and the thing that goes wrong is not that the file breaks: it is that the file stops being RUN and nothing says so. The three mechanisms in this tree reach a test file in three incompatible ways, and only one of them is a registration:

- `.ci/scripts/test/gates/*.sh` is named by `leaves` in the registry, one entry per file;
- `.ci/rediacc_ci/tests/**` and `.claude/rediacc_hooks/tests/**` are COLLECTED by pytest
from `testpaths` in `pyproject.toml`, and a correctly wired file there is named nowhere;
- everything under `.claude/hooks` is reached because some other script mentions it by name.

The third is the residue, and the table below prints it ONE ROW PER FILE rather than as a count. A count cannot see one file leaving as another arrives, which is the composition trap this program has already been caught by once. Non-empty is legal here: 13 files run under `.claude/hooks/test-hooks.sh` and the W5 hooks port is what will move them. Silence would not be legal, which
is why they are rows and not a sentence.

`check:ci-test-file-orphans` is what makes the residue safe to render at all: it proves every one of these files is reached by SOMETHING, so an `(unregistered)` row here means "not driven by the registry", never "not run". This table does not re-derive that claim and must not be read as making it.

**One thing the table cannot show, because it is an absence.** `docs/ci-overhaul/08-driver-contract.md` arbitrated three pytest roots and named `.ci/tests/gates` as one of them. That directory holds zero tracked files and appears in NEITHER `testpaths` nor the orphan gate's `SEARCH_DIRS`, so it is not a row below: it was never implemented. Measured 2026-09-09.

<!-- >>> gen-docs: test-split -->
<!-- Roots are read from check_test_file_orphans.py's SEARCH_DIRS and pyproject.toml's -->
<!-- testpaths, so a root that stops being declared stops being counted the same day. -->
<!-- Nested roots are attributed to the LONGEST match, so the rows are disjoint. -->

Scans: every tracked `test-*` / `test_*` file under the roots named by `.ci/scripts/quality/check_test_file_orphans.py` and `pyproject.toml`.

| Root or file | Declared by | Test files | Registry | pytest |
|---|---|---|---|---|
| `.ci/rediacc_ci/tests` | orphan gate + pytest | 289 | 0 | 289 |
| `.ci/rediacc_ci/tests/gates` | pytest testpaths | 156 | 10 | 146 |
| `.ci/scripts/test/gates` | orphan gate | 12 | 12 | 0 |
| `.claude/hooks` | orphan gate | 11 | 0 | 0 |
| `.claude/rediacc_hooks/tests` | orphan gate + pytest | 39 | 0 | 39 |
| (unregistered) `.claude/hooks/context/test-context-bands.py` | - | 1 | 0 | 0 |
| (unregistered) `.claude/hooks/stop/test-adhoc-watch.py` | - | 1 | 0 | 0 |
| (unregistered) `.claude/hooks/stop/test-always-tier.py` | - | 1 | 0 | 0 |
| (unregistered) `.claude/hooks/stop/test-completion-evidence.py` | - | 1 | 0 | 0 |
| (unregistered) `.claude/hooks/stop/test-judge-schema.py` | - | 1 | 0 | 0 |
| (unregistered) `.claude/hooks/stop/test-plan-status-parse.py` | - | 1 | 0 | 0 |
| (unregistered) `.claude/hooks/stop/test-planfile.py` | - | 1 | 0 | 0 |
| (unregistered) `.claude/hooks/stop/test-planindex.py` | - | 1 | 0 | 0 |
| (unregistered) `.claude/hooks/stop/test-planrec.py` | - | 1 | 0 | 0 |
| (unregistered) `.claude/hooks/stop/test-reggate-ledger.py` | - | 1 | 0 | 0 |
| (unregistered) `.claude/hooks/stop/test-teammate-idle.py` | - | 1 | 0 | 0 |

16 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->
