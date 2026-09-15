# PLAN: object-citation fragility in agent/ plans

Status: done

## Status

Done, 2026-09-14. Started as a design-only handoff (written from an isolated
worktree clone by a session with no write access, specifically so the shared
tree, `0914-1` mid-push at the time, would not be touched) and executed the
same day once the tree reached a quiet point. Every task below landed and was
individually verified against the real `check:ci-plan-citations` gate, not
just against this document.

## Tasks

- [x] Repoint the 8 already-fragile commit-identity citations. Done: 6 repointed with diff-content verified identical to the original (not just subject-matched), 2 correctly left as-is with an inline note instead of a false repoint (the first only reachable via a stale non-`origin/main` remote; the second part of an exact historical pointer-value mapping where substituting a same-subject commit would record the wrong value). One of the 8 turned out to be a file-content claim, not a commit-identity one, and was repointed to its tree id instead. The three tokens, quoted outside prose because they are deliberately unresolvable:

  ```
  b1d40b6d4
  feb82612aedfe94292cd20210349703fc541ce91
  6a04dcbad9
  ```

- [x] Handle the 9 coincidental hex tokens in class (c). Done via the systemic fix this plan recommended rather than 9 individual fences: `UUID_TAIL_RE` exemption landed in `check_plan_citations.py` (constant + `citations()` filter + 2 new selftest controls), verified against 2 real corpus sites directly. The 3 non-UUID-shaped tokens (fingerprint/report-id labeled) are not currently red and were left untouched.
- [x] Add a `tree` resolution kind. Done: `wl_planrec.resolve` (+`RESOLVE_KINDS`) and `check_plan_citations.py`'s `unresolved()`, verified live against `444e9c09092a80bbb7defa6eea122e0de28a89eb` (now resolves as `tree`; `blob`/`commit` correctly still refuse it).
- [x] Add inline notes at the dead-on-purpose / cross-repo citations. Done for all 4 plus the 2 stale "see git log" pointers below, plus 2 more found while doing this work (`c05edbba`, `f020473e`) that needed the same treatment.
- [x] Repoint or note the 2 stale "see git log" pointers in `agent/PLAN-stop-report-queue.md:8`. Done (noted, truncated below the citation threshold).
- [x] Leave the 62 healthy commit-identity citations and 53 `Full-Text-Blob:` citations untouched. Done — none were touched.

## Corrections to the working assumptions this plan started from

Read `.ci/scripts/quality/check_plan_citations.py` and
`.claude/hooks/stop/wl_planrec.py` at `0914-1`'s tip (`af08c2888`) before
anything else, because the brief this plan was commissioned from got several
details of the actual gate wrong. Both scripts self-test their own claims
(`--selftest`, 24/24 PASS at that commit), so these corrections are load-bearing,
not pedantic:

- **Scope is `agent/PLAN-*.md` and `agent/INDEX.md` ONLY.** `in_scope()`'s own
  selftest asserts `docs/agent-reference/TRAPS.md` is NOT in scope, and neither
  is `agent/<session>/STATE.md` (per-session, read-only to everyone but its
  owner) nor generated `agent/pr/*` / `agent/worklist/*`. The brief's mention of
  "a few `agent/f4da5c2e/*.md`/`docs/agent-reference/TRAPS.md` files" citing
  objects under this gate is not how the gate is scoped today. Those files can
  and do carry stale hex tokens, but `check:ci-plan-citations` cannot see them
  and was deliberately built that way (ownership: only a session that can edit
  the file should be told to fix it). Widening scope is explicitly flagged in
  the gate's own docstring as "a separate decision with a much larger blast
  radius" — out of scope for this plan.
- **Four citation kinds, not five, and no "blob"/"commit"/"trap" kinds at the
  extractor level.** `check_plan_citations.citations()` extracts `fileline`,
  `plan`, `gate`, `object`. `object` is the union: `unresolved()` accepts a
  token if `R.resolve(root, "blob", tok)` OR `R.resolve(root, "commit", tok)`
  succeeds — "demanding one would flag the other" (source comment). There is no
  separate blob-kind or commit-kind citation in the corpus; there is one hex
  token that the gate is happy to see resolve either way. `wl_planrec.resolve`
  itself had seven kinds (`blob, commit, ancestor, fileline, gate, plan, trap`)
  before this plan's tree-kind addition landed, now eight
  but the citations gate only ever calls it with five of them; `ancestor` and
  `trap` are used elsewhere (stop-hook claim verification, `check-trap-registry`).
- **The fingerprint example from the brief is already fixed.** (The token is
  quoted in the fence at the end of this section; it is not a git object.)
  It is registered in `scripts/data/shape-duplication-seed.json` (checked; the
  entry is there, dated 2026-09-08), so `citations()`'s `shape_fingerprints()`
  check already excludes it before it ever becomes an "object" candidate. It
  does not appear in the current object-citation corpus. This is not a live
  problem; it is the working example of the fix this plan recommends
  generalizing (see Recommendation 3).
- **`resolve(root, "commit", token)` is existence-only, not
  reachability-checked**, per its own docstring (`git rev-parse --verify --quiet
  <token>^{commit}` — nothing about ancestry). That is the exact
  reachability-vs-existence gap `b816445a1` ("a control that could only pass
  where the fix was unnecessary") and `af08c2888` ("the reachability oracle
  that called 53 healthy blobs dead") already document from this session's own
  mistakes today. It matters here because a *local* clone can carry orphaned
  objects (dangling commits from an earlier `git filter-branch`/rebase on this
  very branch, per the "trailer rewrite" commits fenced below) that still
  answer "yes" to `rev-parse --verify` while a genuinely fresh clone (what CI
  and every new contributor actually get) would not have the object at all.
  Section 4 below gives the correct oracle for "would this survive a rebase or
  a fresh clone", and it is **not** `resolve()`'s own commit-kind check.

## 1. Measurement

Corpus at `0914-1`@`af08c2888`, `agent/PLAN-*.md` + `agent/INDEX.md`:

| | count |
|---|---:|
| in-scope files | **86** |
| total citations (all kinds) | **3,094** |
| — `fileline` | 1,511 |
| — `gate` | 790 |
| — `plan` | 450 |
| — **`object`** | **343** (citation *sites*; **149 distinct tokens**) |

Of the 149 distinct object tokens, resolved with the gate's own
`R.resolve(root, "blob"|"commit", token)`:

| resolution | distinct tokens |
|---|---:|
| resolves as **blob only** | 53 |
| resolves as **commit only** | 70 |
| resolves as **both** | 0 |
| resolves as **neither** (dead today) | 26 |

Reachability, using the `c5b727b2e` oracle (`git rev-list --objects af08c2888`,
prefix-matched — this is what a fresh clone/CI checkout actually contains,
unlike `merge-base --is-ancestor`, which the same commit found throws exit 128
on every blob and would have misreported ~53 healthy citations as dead):

| | distinct tokens |
|---|---:|
| reachable from HEAD (survives a fresh clone) | 116 |
| **not** reachable | 33 |

The 33 unreachable split as:
- 25 of the 26 "resolves as neither" tokens (truly dead; the 26th,
  `444e9c09092a80bbb7defa6eea122e0de28a89eb` in
  `agent/PLAN-git-history-media-rewrite.md:174/321`, **is** reachable — it's a
  real git **tree** object, a kind `resolve()` never tries; see Recommendation 4).
- **8 tokens that currently PASS `resolve()` (gate is silent on them today)
  but are NOT in the fresh-clone reachable set** — i.e., they exist only as
  leftover loose objects in a long-lived local clone (this branch's own
  `filter-branch`/trailer rewrite earlier today almost certainly produced
  several of these) and would already be dead the next time anyone re-clones
  this branch or runs `git gc --prune`:

  ```
  8b7840ed4   commit  agent/PLAN-fix-ci-contention-aware-timeouts.md:225
  b1d40b6d4   commit  agent/PLAN-fix-tutorial-player-debug-hook-attachment.md:58,64
  6a04dcbad9ce56f92daff2c93a78f8d5f4cac2fa  commit  agent/PLAN-git-history-media-rewrite.md:210
  09b0b7716   commit  agent/PLAN-git-history-media-rewrite.md:301
  feb82612aedfe94292cd20210349703fc541ce91  commit  agent/PLAN-git-history-media-rewrite.md:321
  f90baf1d3   commit  agent/PLAN-secret-namespace-migration.md:80
  cb27c2b19   commit  agent/PLAN-secret-namespace-migration.md:80
  082f7aa94   commit  agent/PLAN-www-bundle-determinism.md:11
  ```

  These are the sharpest evidence for this whole plan's premise: they are
  *already* fragile, not merely "fragile after a future rebase".

## 2. Classification scheme

Applied to the 149 distinct object tokens, by reading each site's surrounding
prose (not just its resolution status):

**(a) File-content claim — mechanically safe as a blob id, or already is one.**
Signal: a structural `Full-Text-Blob: <sha>` field (the plan-compaction
metadata `wl_planfid.py` writes at the top of every compacted plan — this is
already a blob id, by construction, and needs no change), or prose immediately
adjacent to `git hash-object`, `git cat-file -p`, or an explicit `blob:` label.
**This is almost the entire 53-token "blob only" bucket** — a spot check
confirms nearly every one is the `Full-Text-Blob:` field, not a narrative
citation. No action needed; this is the target state, already achieved, for
this sub-class.

**(b) Commit-identity claim — NOT safely convertible to a blob; needs prose
judgment, not mechanical substitution.**
Signal phrases found directly adjacent to the token in this corpus (each
verified against a real site, not hypothesized): `committed (as|in|unformatted
in)`, `HEAD stayed`, `measured at` / `measured on the tree at`, `landed (as|at)`,
`confirmed via` followed by `git show <sha>:path`, `ancestor of HEAD`, `blame
to … ancestor of HEAD`, `whose subject is`, a bare `git log <sha>`, `repoint(ed)`,
a `commits <sha>, <sha>` list, `Landing: console commit <sha>, "feat(...)"`, or a
sha immediately followed by its commit subject in quotes. A random sample of 8
commit-only tokens came back **8/8 genuine commit-identity claims** — this
corpus is heavily forensic/investigative in style (the plan files document
*what actually happened*, not just *what the code says*), so this is the
dominant shape for anything that isn't the `Full-Text-Blob:` field.
Sub-cases:
  - **Healthy and reachable today (62 of the 70 commit-only tokens):** leave as
    a commit sha. Converting to a blob id would be actively wrong — it would
    silently change the claim from "commit X happened / HEAD was at X" to "file
    Y had this content", which is a different, weaker fact. Accept the
    rebase-fragility; it's inherent to the claim being made, not a defect.
  - **Already fragile (the 8 tokens above):** repoint using exactly the method
    `c5b727b2e` proved out today — map by commit subject against current
    history (`git log --oneline --all --grep=<subject-fragment>` or `git log -S`
    on the file the plan describes), verify the new sha is in the
    `git rev-list --objects HEAD` reachable set, then edit the citation. Do
    **not** convert these to blobs either, for the same reason as above.
  - **Deliberately dead-on-purpose.** Three in
    `agent/PLAN-git-history-media-rewrite.md:61-62`, listed as "media-only"
    pre-rewrite commits, plus three more (one of them at 2 sites):

    ```
    374943470  c05edbbab  f020473e2
    cefa43ca7  b389ac305  b685cd590
    ```

    These are quoted inside a fence because this document ENUMERATES dead
    tokens as its subject, and `check:ci-plan-citations` resolves any bare
    9-character object token on a prose line -- so naming them in prose makes
    the plan about unresolvable citations fail for containing unresolvable
    citations. A fence is the gate's own documented escape; shortening them to
    8 characters would also pass, but only by exploiting a blind spot the gate
    names out loud rather than by declaring intent. these document commits that a rewrite this repo already ran
    intentionally discarded, or are stale "see git log" pointers nobody has
    revisited. Precedent already exists in this same file family
    (`614d912a7`'s commit message: "given at 8 characters … with a note at each
    site saying why"). Apply the same pattern: leave the sha, add a one-line
    note explaining it predates a known rewrite and is not expected to resolve.
    (`374943470` is actually all-digits and was never counted as an object
    citation at all — the gate exempts all-digit tokens by design — it's listed
    here only because it's the third member of the same prose list as the two
    that were counted.)
  - **Cross-repository reference (1 token),** in
    `agent/PLAN-git-history-media-rewrite.md:321`, explicitly documented in the
    same paragraph as a commit sha from a *different, retired* repository:

    ```
    f43ccb790f3d893f07f0b4faa382bee10a3976cd
    ```

    (`/home/muhammed/monorepo`, "last commit 2026-01-29"). It will never resolve
    in this repo's object store by design, same as the gate's own documented
    "SUBMODULE gitlink" exemption. Needs an inline note, not a fix.

**(c) Not really a citation — a coincidental hex-shaped token.**
Signal: the token is the trailing hex group of a canonical UUID
(`nnnnnnnn-nnnn-nnnn-nnnn-NNNNNNNNNNNN`, whose final 12-hex segment is *always*
pure hex and therefore *always* matches `HEXTOK_RE` once it's ≥9 chars — this is
a systemic, recurring source, not a one-off), or the word immediately before it
is `fingerprint`, `fp`, `(report …)`, or it sits inside a scratchpad/session
temp path. Found in this corpus (9 distinct tokens, all in the "resolves as
neither" / dead bucket, none fenced):

```
b4b800aaeb21      UUID tail   agent/PLAN-env-to-bitwarden-v2.md:401 (Stripe secret uuid)
b4b900b6b67b      UUID tail   agent/PLAN-secret-namespace-migration.md:160
b36f00b0f86a      UUID tail   agent/PLAN-secret-namespace-migration.md:219,1290
b09500f699e1      UUID tail   agent/PLAN-secret-namespace-migration.md:1282
fb37f1ae16f8b7c0  "Fingerprint …" agent/PLAN-secret-namespace-migration.md:247
ee936479b32d3162  "fp …"      agent/PLAN-secret-namespace-migration.md:251
fa51e4a18d553c30e1633288e9733d04  bare hash near "Rediacc OÜ"  :291,414
a6f698562e73      session-id tail in a /tmp/claude-.../scratchpad path
                                  agent/PLAN-promote-mutation-runner.md:27
fc3f4a0f5447      "(report fc3f4a0f5447)" — a wl_report.py report id
                                  agent/PLAN-subagent-idle-detection.md:111,112
```
```
a56ee58a0  a6f76f074
aea2bc733552
```

These are exactly the shape the fingerprint token above was: a hex-shaped
token that is not a git object at all, coincidentally satisfying the regex. Its own
fix (add it to `scripts/data/shape-duplication-seed.json`) is the *wrong
mechanism* for these — that seed is specifically for `check:ci-shape-duplication`
fingerprints — but the same idea (a small, explicit, reviewed allowlist rather
than prose surgery) is the right shape of fix. See Recommendation 3.

## 3. Recommendations per class

1. **(a) blob-form / `Full-Text-Blob:` (53 tokens):** No change. This is
   already the target state the gate's own error message is steering everyone
   toward. Do not touch.

2. **(b) commit-identity (70 tokens):**
   - 62 healthy + reachable: no change, accept the fragility as inherent to the
     claim.
   - 8 already-fragile (listed above): repoint now, using the subject-search +
     `git rev-list --objects HEAD` verification method from `c5b727b2e`. This
     is the highest-priority actionable bucket — these are silently wrong
     *today*, not hypothetically wrong after a future rebase.
   - 3 dead-on-purpose (media rewrite) + 1 cross-repo: add a one-line inline
     note at each site (pattern already established at `614d912a7`), do not
     "fix" them — fixing would either be impossible (cross-repo) or would
     erase the historical claim the sentence is making (pre-rewrite commits).
   - 2 stale "see git log" pointers in
     `agent/PLAN-stop-report-queue.md:8` --

     ```
     b389ac305  b685cd590
     ```

     -- low-priority repoint or note; this
     line is describing already-implemented, already-superseded work per its
     own text ("Everything below is the plan as written at design time and is
     superseded by this line"), so a note may be cheaper than a repoint.
   - **Never** convert any of these to a blob id. That is the core correction
     this plan makes to the gate's own error-message advice: the advice is
     right for class (a)/(c) and actively wrong for class (b), because a blob
     names file content, not a commit event, and rewording every such sentence
     to make a content-claim instead of a commit-claim would be lossy rewriting
     of the historical record, at 70-site scale, for no safety gained on the 62
     that are healthy.

3. **(c) coincidental hex (9 tokens):**
   - Cheapest per-site fix: wrap each in a fenced code block (the gate already
     skips fenced lines for judgment purposes) or leave as-is since none of
     these 9 are currently red (they're pre-existing corpus debt, not on an
     added line the gate is watching).
   - Better, systemic fix, worth proposing to whoever owns `check_plan_citations.py`:
     extend `citations()`'s token filter with the same shape of exemption it
     already has for all-digit tokens — skip a hex run when it is the trailing
     group of a canonical UUID (`\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-([0-9a-f]{12})\b`)
     immediately adjacent to the match. This is a **gate change**, not a prose
     change, and it prevents every *future* UUID citation in this corpus
     (Stripe secrets, DB ids, JWT claims are common in these plans) from
     needing a one-off fence or a shape-duplication-seed entry. Flag as a
     separate, reviewable change — do not bundle it into a prose-editing pass.

4. **Resolver gap, not a citation problem:** `444e9c09092a80bbb7defa6eea122e0de28a89eb`
   is a real git **tree** object, correctly cited, but `resolve()`'s `object`
   path only ever tries `blob` and `commit`. Recommend adding a `tree` attempt
   to the same `unresolved()` branch check_plan_citations.py already has
   (`R.resolve(root, "blob", tok) or R.resolve(root, "commit", tok)` →
   `... or R.resolve(root, "tree", tok)`, and a matching `"tree"` branch in
   `wl_planrec.resolve` using `git cat-file -t token == "tree"`). This is a
   one-line addition to a shared resolver, not a per-file edit, and removes a
   whole class of future false "dead" findings for anyone who cites a tree
   (common when documenting a `git filter-branch`/rewrite control, exactly the
   plan this token lives in).

## 4. Execution plan

**Splitting the work.** One writer, sequential, not parallel — the object
citations cluster heavily in a few files (`agent/PLAN-tooling-transformation.md`
alone carries 49 of the 343 sites; `agent/INDEX.md` 32;
`agent/PLAN-secret-namespace-migration.md` 10) and the fenced-vs-not,
dead-on-purpose-vs-not judgment calls documented above need one person holding
the whole classification in their head to stay consistent. If it must be
split, split by **disjoint file set**, never by citation kind within a file
(kind-splitting would have two writers editing the same lines).

Suggested batch order, smallest blast radius first (matches the Tasks list
above):
1. The 9 coincidental tokens (class c) — either fence them or land the UUID-tail
   exemption in the gate first, since it makes several of the fence-wraps
   unnecessary.
2. The 8 already-fragile commit-identity tokens (highest actual risk).
3. The 1 tree-resolver-gap token (land the `tree` kind in `wl_planrec.resolve`
   first; this is a shared-module change, review it on its own).
4. The 4 dead-on-purpose / cross-repo tokens (note-only, no functional change).
5. Leave the 62 healthy commit-identity and 53 blob tokens alone.

**Verification after each edit:**
- `npm run check:ci-plan-citations -- --selftest` first, always — if the
  resolver's own controls don't pass, nothing else means anything (this is the
  gate's own documented anti-vacuity discipline; don't skip it).
- `npm run check:ci-plan-citations` for the real verdict. Remember it only
  judges **added lines** in a diff against the merge-base with `origin/main` —
  editing an existing dead citation IS an added line (the diff sees the whole
  line as removed+added), so every edit in this plan DOES get judged, which is
  the correct behavior here.
- **The correct oracle for "will this survive a `merge --rebase`" is NOT
  `resolve()`'s own commit-kind check** (existence-only, as corrected above) and
  is NOT `merge-base --is-ancestor` (exits 128 on blobs, per `af08c2888`). It is:
  ```
  git rev-list --objects <ref-you-are-about-to-merge-into> | cut -d' ' -f1 > /tmp/reachable.txt
  grep -qf <(echo "$TOKEN") /tmp/reachable.txt   # prefix match needed for abbreviated tokens
  ```
  computed against the **target** ref of the rebase/merge (not just current
  HEAD), because the whole point is to answer "will this object still be there
  after the rewrite", which local HEAD cannot answer once the rewrite has
  already happened locally. Read `.ci/config/carried-reds.json` before this
  work starts — `check:ci-plan-citations` is not currently carried there
  (confirmed by reading the file at `af08c2888`), i.e. it is expected green
  right now; a batch that reds it should be treated as a real regression, not
  pre-existing debt.

**What NOT to do:** do not run any of the file edits from this plan yourself in
this pass. This document is the design; a separate writer session, working
directly in the shared tree (not this isolated worktree), should execute it
after the in-flight `0914-1` push referenced above has landed or paused, to
avoid a second session editing `agent/PLAN-tooling-transformation.md`
concurrently with the live one.

## How to re-run this measurement

From a disposable clone (never the shared tree):
```
git clone --no-local --no-hardlinks <repo> /tmp/citation-audit/clone
cd /tmp/citation-audit/clone && git checkout <branch-tip>
python3 .ci/scripts/quality/check_plan_citations.py --selftest   # must be 24/24 PASS
```
Then, in Python, with `sys.path` extended to `.ci/scripts/quality` and
`.claude/hooks/stop`:
```python
import check_plan_citations as G, wl_planrec as R
files, n = G.corpus_citations(ROOT)                      # 86, 3094
listing = [f for f in G._git("ls-files", "--", "agent").split("\n") if G.in_scope(f)]
# iterate lines, call G.citations(line) for [(kind, token), ...]
# for kind == "object": R.resolve(ROOT, "blob", tok), R.resolve(ROOT, "commit", tok)
```
For the fresh-clone reachability oracle:
```
git rev-list --objects <ref> > /tmp/reachable.txt   # then prefix-match each token
```
