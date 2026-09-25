# Rediacc Console Monorepo

## Worktree Warning

**CRITICAL: This repo uses git worktrees.** The working directory (from `pwd`) is the ONLY correct project root. NEVER use paths from other CLAUDE.md files that may appear in the system context — those belong to the main worktree and are a different checkout. All commands (`./run.sh`, `npx tsx`, file paths) MUST use the current working directory, not `/home/muhammed/monorepo/console/`.

**`git worktree add` is hook-blocked from the assistant's own Bash tool** (`.claude/rediacc_hooks/guards/block_worktree_add.py`, chain `pre-bash`), unconditionally — the operator runs it themselves via the `!` prefix when they want one created. **Settled default (2026-09-16): do not ask which checkout new work should happen in.** Continue in whatever checkout the session is already
in. A worktree only ever comes from the operator's own `! git worktree add ...`; there is nothing to gain from asking permission for a decision the assistant cannot execute either way. `.claude/rediacc_hooks/guards/block_settled_questions.py` (chain `pre-ask`) refuses a worktree/branch-routing question the same way it refuses a commit-permission question — if the genuine
cross-session collision risk needs raising, park it as a worklist `[?]` naming the conflict, with a DEFAULT of "continue here", rather than blocking the turn on a question.

## Session Defaults

Standing rules for every task, in this repo and its submodules. The operator should never have to restate them.

### 1. Verified work is committed as it lands, on the one branch

Verified work is committed right away, in small reviewable commits on the single current branch, so uncommitted work never piles up into a mountain nobody can review (operator ruling 2026-09-25; the commit-policy plan under agent/plans).

- **A verified unit** serves one stated purpose inside one epic (one `PR-TASK:` id), has had its acceptance check run with the exit code read (a named test, gate or command at `rc=0`, or the lead's spot-check of a writer's output, rule 4), and touches only paths this session owns: its own edits and the file lists its writers reported. Other sessions' uncommitted paths are theirs, and are never committed by inference.
- **Cadence.** The unit is committed as soon as it is verified, before the next one starts. A worklist item is committed first, then ticked with `commit:<sha>`. Writers never commit: the lead commits each writer's spot-checked output as the report is accepted. A unit above 20 files needs a proof line anyway (`block_unproven_bulk_transform`), which is the signal to split it.
- **Commit form.** `git add -- <new paths>`, then `git commit -F <msg> -- <paths>` (the pathspec form `block_pathspecless_git_commit` enforces). Conventional Commits subject, the verification commands and their exit codes in the body, a `PR-TASK: <id>` trailer, no Co-Authored-By line, no amending: a mistake gets a new fix commit.
- **Pushing is separate from committing.** Pushes are backups and CI triggers, never one per commit: at an epic milestone, at least every 2 hours of committed work, and before a stop that leaves unpushed commits. Each push still needs a `ci:quick` receipt (`block_unverified_push`).
- **One branch, one PR, and no agent path to a second.** Each repository (the console and each submodule under `private/`) holds at most one live `MMDD-N` branch and at most one open PR, whose head is that branch. `block_second_branch` refuses every spelling of a second branch (`checkout -b`, `switch -c`, `branch <new>`, a push to a new remote name, `gh pr create --head <other>`), and `block_second_open_pr` refuses a second PR. A second branch or PR is the operator's own `!` command; there is nothing to ask for.
- **`main` takes only a hotfix, and only the operator pushes it.** `block_commit_on_main` refuses a commit on `main` unless its subject ends in `[hotfix]` and it carries a `Hotfix-Evidence:` trailer (the red main run, or `ASKED:<ISO minute>` when the operator called it a hotfix in this task) and touches at most 5 files; off `main` the tag is refused. The push stays the operator's `!` (`block_push_to_protected_branch`). The tags, the refused CI skip tokens and the git-level hooks behind them are in [docs/agent-reference/ci-gates.md](docs/agent-reference/ci-gates.md) *Commit policy*.

The commit is the safety net, and the tree still holds work from other sessions and agents:

- Never `git checkout` / `restore` / `stash` / `clean` to undo a mistake of this session's
own making. It deletes uncommitted work, including work belonging to others. Repair forward instead, with a new commit when the mistake is already committed.
- Prefer targeted edits over scripted bulk rewrites. When one must be scripted, re-verify
the WHOLE file afterward, not just the part it aimed at. A find-and-replace scoped wider than intended lands in a neighbouring key, function, or file, and the session's own verification will miss it if it only re-checks the target.

### 2. Findings are part of the deliverable

A session is scoped to one ask, but it walks past real defects on the way. Walking past them silently is the failure this rule exists to prevent.

- **A workaround is a bug report.** Routing around something (a command that prints
nothing, a flag that misbehaves, an error that explains nothing) means a defect has been found. Say so, with the exact command and the exact output. Do not quietly take the long way and leave the bug for the next session to rediscover.
- **Discovery is always in scope, and so is the fix.** A finding is fixed in the
session that finds it. Filing an issue never closes a finding. Small and local (no new abstraction, no signature change rippling outward): fix it inline immediately and say so. Bigger than that: ask the machinery (`worklist.py --triage <me> <finding...>` answers INLINE, PLAN+SUBAGENT, or OPERATOR-ONLY with the exact next command), have a Plan agent write the design to
`agent/plans/PLAN-<slug>.md` (committed, survives compaction; it moves once at close into `_done/` or `_removed/` and leaves a stub, which `check:ci-plan-folders --move` does in one step), then implement it THIS session: via a writer sub-agent when the fix's file set is disjoint from the work in hand or the context is heavy (disjoint ownership, max 4, rule 4), inline otherwise. The
fix rides the one branch and its open PR as its own commit (rule 1); there is no second branch to cut for it.
- **Issues are a last resort with exactly three doors:** the fix needs
operator-only powers (secrets, purchases, external accounts, production deploys); the operator explicitly deferred it when asked; or the target is outside this session's write access. "It is big" is not a door. Any last-resort issue must carry the evidence (exact command, exact output) and a ready-to-run brief a future session can execute without rediscovery, and its worklist item
closes only with the door named in the tick evidence (`door:operator-only`, `door:operator-deferred`, or `door:no-write-access`).
- **Unblocking and cross-boundary fixes: do the minimum, then say so loudly.** A gate or
lint rule blocking the task, or a defect in another package or submodule, still gets fixed. Make the smallest change that works and flag it in the summary as something the operator did not ask for, rather than burying it in the diff. Never suppress a gate to get past it (see the BLOCKER convention).
- **Sweep the class, not the instance.** Before calling a bug fixed, grep for its
siblings. One bad call site usually has several.
- **Ask for the big-bang, not for permission to patch one thing.** The operator prefers
ONE comprehensive change over a trickle of small ones, and will usually say yes. So when findings cluster, do not ask about them one at a time and do not propose the minimal patch: put the whole cluster into a single plan (root cause, siblings, tests, regenerated artifacts, submodules included) and ask to run it. Ask as soon as the cluster is visible, not after the session has been
spent working around it. The ask decides PACKAGING (one comprehensive change versus riding the current PR), never WHETHER the findings get fixed: park the ask as a [?] whose DEFAULT is "fix the cluster this session", and keep working anything that is safe under either packaging while it waits.
- **Clean break, no compatibility theater.** There is one operator and no external
consumers. Fix the root cause; do not add migration commands, deprecation windows, fallbacks, or dual code paths to preserve behavior nobody depends on.
- **Once a big-bang is approved, do not descope it unilaterally.** Fan out subagents if it
is large (rule 4). Never quietly downgrade a piece to a stub, a TODO, or a "follow-up issue". If something genuinely cannot be done, say which piece and why, out loud.
- **Track findings in the worklist, not in memory.** The Stop hook
(`.claude/hooks/stop/worklist.py`) refuses to end a turn while any open item remains. It is per-REPO, not per-session, so open items survive a restart and a fresh session inherits them.
- **Use the VERBS, not the file.** Since v10 the store is an append-only JSONL
event log, and the hook prints a `WORKLIST GUIDE` on every full stop naming the exact next command per item. Base the `## Remaining` section on that guide, not on memory: it exists because hand-written status silently ignored the tracked ages, and on its first stop it caught a watch still reported as "ongoing" that had finished 51 minutes earlier.

  ```
  worklist.py --add <me> <text...>              track a new open item, prints its #id
  worklist.py --tick <me> <id> <evidence>       close it; evidence is mandatory
  worklist.py --triage <me> [--id <id>] <finding...>  big/small verdict + next command
  worklist.py --defer <me> <id> <q... DEFAULT: <action>>
  worklist.py --lease <me> <id> <+min|ISO8601Z> worker:<bg-id> [note]
  worklist.py --update <me> <id> <text...>      progress; resets the liveness ladder
  worklist.py --list --open [<me>]              the actionable slice (~2 KB)
  worklist.py --list                            FULL history dump (~550 KB, avoid)
  ```

Item ids are hex but NOT fixed width: items migrated from the old markdown carry 12 characters, newly added ones 8. Never parse them assuming a length.
- **The store is shared, so never hand-edit it.** A second session may be running
in this worktree, and two read-modify-writes lose the loser's items silently. The verbs append one event under a lock, which is what makes concurrent use safe. The legacy markdown file is still synced for compatibility, but writing to it directly is not the interface any more.
- **Tag every item `(<session-id-prefix>)`. The tag is load-bearing, not a label.**
The hook blocks only on items tagged with THIS session (an untagged item counts as this session's, so forgetting the tag is safe but claims it). Other sessions' open items are REPORTED to the operator, never blocked on. Without ownership a second session deadlocks: it cannot do those items without racing live work in the same tree, and it must not tick or delete another session's
tracking. Never tick or remove an item belonging to another session.
- **A COMPACTION is the one case where a peer is really this same session, and `--adopt`
is how that gets said.** A compaction can hand one continuous conversation a new session id, and the rule above then fires against the session's own work. On 2026-09-02 that left four settled decisions open all night, reported to the operator every stop as a peer's, while the session reasoned about a peer that did not exist. If open items are attributed to a prefix that plausibly
WAS this session before a compaction, run `worklist.py --adopt <me> <prev>`. It records the edge only on harness evidence -- a `compact_boundary` the transcript opens with, plus conversational record uuids both transcripts share -- and there is deliberately no `--force`: two genuinely concurrent sessions share zero such records, which is what makes the check a refutation rather
than a formality. Nothing is rewritten, so the `(<prefix>)` tag keeps naming whoever really wrote the item. **Do not guess.** Same cwd, same branch and adjacent times are ROUTINE for concurrent sessions in this tree, so they prove nothing; if `--adopt` refuses, the items belong to another session.
- **Defer as a QUESTION, not a note.** Four states, and only four: `- [ ]` open,
`- [x]` done, `- [?]` needs an operator decision, and `- [>]` in-flight on BACKGROUND work. A `- [>]` lease carries a UTC expiry (max 120 min ahead) AND a `worker:<bg-id>`, because since v10 the hook VERIFIES that worker against the operating system rather than believing the claim. A worker that cannot be verified is reported as unverifiable, never accused of being dead; only a
worker the event itself has dropped counts as gone. An item with no live worker enters the 45/90/120 minute ladder: ping, then investigate, then resolve.
- **A `- [?]` must carry `DEFAULT:`, and the default EXECUTES.** Autonomy is
time-boxed, not indefinite: an unanswered deferral whose window closes becomes an order to do the default and tick it with evidence, draining a few per stop. Reserve `- [?]` for decisions that are genuinely the operator's: anything settleable from the code, the request, or a sensible default belongs to this session, and parking it as "blocked on the operator" wastes a round trip.
Thirty open deferrals is a symptom of over-asking, not a queue.
- **End with what remains**, which under this rule is short: operator-deferred
`[?]` items and last-resort issues with their doors named. A "found, not fixed" entry that fits neither category means the fix-in-session rule was not followed; go back and fix it.
- **`## Remaining` is a list of things that CANNOT be done right now, not a to-do
list.** An item belongs there only if it is (a) `[?]` awaiting an operator answer, (b) `[>]` leased to a verifiably live worker, (c) waiting on a specific external run, or (d) a last-resort issue with its door named. **Nothing else may appear.** A line like "blocked on: nothing" — or "next up", or "ready to start" — is not a status, it is a confession that the session is stopping
with work in hand. Delete the line and do the work.

**This is the failure this section exists to prevent, and it has happened.** Over roughly ten consecutive stops in one session, the loop was: hook pushes back -> do exactly ONE item, or only a maintenance chore (rewrite STATE.md, refresh the brief, update a plan) -> stop again -> hook pushes back. The session reported several items as "Blocked on: nothing" and stopped anyway, with
no background agent and no monitor running. The hook itself eventually fired `NOTHING HAS MOVED IN 3 CONSECUTIVE STOPS`. The operator had to intervene.

Two mechanisms make this easy to fall into, so name them:
  1. **The hook's checks become a substitute for progress.** STATE.md
     staleness, the session brief and plan freshness are each individually
     correct, and together they supply an endless stream of hook-satisfying
     NON-work. Satisfying a check is not shipping anything.
  2. **A push-back is not a work order for one item.** The hook naming the next
     item does not mean "do that one and stop". It means the queue is not
     empty. Drain it: keep going until every remaining item is genuinely (a)-(d)
     above. There are two exceptions. The first is a full writer cap: with every writer slot verified live and every remaining item leased or queued (`worker:queue`), the hook stands down (`CAP-SATURATED WAIT`) and stopping is correct. It still blocks on a free slot, a dead writer, an expired `DEFAULT`, or a stale STATE.md in the last context band before compaction (agent/plans/PLAN-stop-hook-cap-saturated-wait.md).
     The second is `FOCUS MODE`, a PR wind-down that `/pr-babysit` and `/pr-merge` switch on with `worklist.py --focus <me> babysit|merge [--pr <n>] [--branch <b>]`: finish, don't start. Running writers and in-flight items finish, and plan, queue and hygiene pushes park and are named in one `FOCUS ENDED` line when focus ends. CI red, dead watches, unread reports, STATE.md near compaction and hook integrity still block. The judge is skipped and advisories are batched. `block_focus_spawn` refuses new writer spawns except declared fix work: `focus-fix:#<id>` in the spawn, naming an open item of this session that carries `pr:<n>` (plus the `pr-babysitter` loop itself under `babysit`). Focus ends on `--focus <me> off`, when the PR merges or closes, or after 24 hours (agent/plans/PLAN-stop-hook-focus-mode.md).

The operator's asks decide PACKAGING, never WHETHER (rule 2). "Waiting for the operator to pick the packaging" does not block the code that would go into either one — write it under the default and let the answer choose where it lands. And a turn that ends is a turn that costs a round trip: the bar for stopping is "there is genuinely nothing left to advance", not "a defensible report
has been produced".

### 3. Verification comes before the claim

- **Run the real thing.** Output, exit-code, and error-path defects are invisible to code
reading and to mocked tests. Drive the actual command and read stdout and stderr
  SEPARATELY: a wrapper that swallows output, or progress text landing on stdout, only
shows up in the raw bytes.
- **A plan's claim about unread code is a hypothesis.** Verify the load-bearing
ones before relying on them. Approved plans are wrong about real code often enough that the first live run is part of the implementation, not a formality.
- **Do not trust a report that has not been spot-checked**, including a subagent's and
this session's own from earlier. Check the artifact, not the summary of it.
- **Name the gates that ran, and the ones that were skipped.** Before calling a failure
pre-existing or environmental, show that none of its findings are in files this session touched.
- **"Cannot be done here" is a claim, so probe it before making it.** Closing an item
as impossible without running the command that proves it is how work gets abandoned while sounding diligent. A CRIU pin bump was reported as needing infrastructure this session did not have; `docker version` answered in one second, and it did.

### 4. Reach for subagents on investigation and planning

Reading and thinking parallelize well here; writing does not. Use them accordingly.

- **Investigate with them by default.** Any question that means sweeping several files,
packages, or naming conventions goes to `Explore` or `general-purpose` agents rather than into this session's own context. Read-only fan-out is cheap: run several at once.
Ask each for conclusions with `file:line` evidence, never file dumps. This kind of dispatch defaults to `model: "haiku"`: the tree already holds the answer, and a citation that does not resolve is caught on sight.
- **Plan with them on anything non-trivial.** For a design with real trade-offs, run
`Plan` agents (up to 3, different angles) and synthesize. Their plans are proposals, not findings: check the load-bearing claims directly before acting (see rule 3).
- **Writing agents: at most 4 at a time, with disjoint file ownership.** The cap is enforced by the Stop hook roster (`wl_roster.WRITER_CAP`) and the pre-agent guard; lease every writer; read-only work goes to `Plan`/`Explore`, which do not count. State the exact
files each one owns and forbid it from touching any other. Two agents editing one file, or one agent running a repo-wide regenerate script, corrupts the tree. Also forbid `git checkout/restore/stash` and any `sync`/`regenerate` script in their prompts, for the reasons in rule 1.
- **Spot-check every agent's output against the artifact.** Their reports are accurate
about intent and quietly wrong about placement. Verify structure across the whole file set they touched, not just the keys or symbols they claimed to change.
- **Model choice is by task SHAPE, never by language or domain.** Haiku for
READ-ONLY work and for very small, low-risk follow-ups: investigation and search fan-out, surveys, bounded classification, and a one-line correction to something already read. Haiku is NOT routed general write or implementation work any more -- not a port, not a mechanical sweep, not doc churn -- even where a pre-existing oracle would decide correctness and being wrong would be
loud. That carve-out was retired by the operator on 2026-09-23 (`D-M1`), so an oracle no longer buys a cheap tier the right to produce an artifact; the i18n naturalization pipeline is a script rather than an `Agent` dispatch and keeps its own `--model haiku` default.
Opus when the artifact created IS the oracle: new guards, new gates, schema design, multi-file planning, anything adversarial. Sonnet is an escalation tier, not a default. **[docs/agent-reference/model-routing.md](docs/agent-reference/model-routing.md)** carries the full rule, the oracle caveat, and worked examples.

## Architecture

Self-hosted infrastructure platform. Each machine runs Docker-based repositories with encrypted, isolated environments.

### Key Concepts

- **Repository**: An isolated application deployment (e.g., `mail`, `gitlab`, `nextcloud`). Each repo has its own Docker daemon at `/var/run/rediacc/docker-<networkId>.sock`, loopback IP range (127.0.x.x/26), and mount at `/mnt/rediacc/mounts/<guid>/`.
- **Fork**: `rdc repo fork <name> --tag <tag>` makes a new repo (`<name>:<tag>`) with a fresh GUID and networkId that shares the parent's data via BTRFS reflink. **Forks are near-instant and constant-time** regardless of repo size: a 100 GB repo and a 1 GB repo fork in the same seconds. Use forks freely as the per-test isolation unit, do NOT assume fork cost scales with repo size.
- **Renet**: Network orchestrator on the machine. Manages compose files, loopback IPs, Docker daemon lifecycle. CLI: `sudo renet list all --json`, `sudo renet compose -- up -d`.
- **Rediaccfile**: Bash script with lifecycle functions (`up()`, `down()`, `info()`) sourced by renet during deployment.
- **Config**: CLI configuration file for connecting to machines, and a complete "universe": each config is a flat JSON file (`~/.config/rediacc/<name>.json`, default `rediacc.json`) carrying its account server and keys under `account.*`, its machines/repos/credentials, and a unique ID and version number. Its token lives beside it at `api-token-<name>.json`. Multiple named configs are supported; `--config <name>` (or `REDIACC_CONFIG`) selects one, `rdc config current` shows the active one.
- **State Provider**: Abstraction layer (`CloudStateProvider`, `LocalStateProvider`) that routes API calls based on adapter detection.
- **Config Storage**: Optional zero-knowledge encrypted config sync. Setup and management via the web portal (`/account/config-storage`), unlock via passkey with PRF, master password, or recovery code (LUKS-style key slots). One org-wide CEK encrypts every team's configs; team scoping is server-side access control, not cryptographic isolation. Enabled from the CLI with `rdc config remote enable` (opens an `/account/config-remote` handoff page, seeds the store from the local config on first enable); sync is implicit, and reads are served from an encrypted-at-rest local cache when the server is offline (with a staleness warning), while writes require the server and fail closed. Member management via portal.

### Packages

| Package | Description |
|---------|-------------|
| `packages/cli/` | `rdc` CLI tool (Commander.js); includes SSH/SFTP/sync/terminal utilities under `src/remote/` |
| `packages/www/` | Marketing website (Astro) |
| `packages/shared/` | Shared types, config, services (consumed by cli, www, account) |

## Search first

Before creating a new file, gate, doc, or provider, search the tree for whether it already exists — under a different name, built by another session, or documented somewhere a plan doesn't point to. Several campaign boxes closed by finding the work already landed and only the record was stale, not by doing it again.

## CLI (`packages/cli/`)

### Common Commands

The thing a command acts on is a **positional ref**, not a `--name` flag: `name`, `name:tag` for a fork, optionally `name@machine`. The machine is derived from the ref. Worked examples for status, term, repo up/sync/logs/exec and vscode are in [docs/agent-reference/cli.md](docs/agent-reference/cli.md).

### Config Setup

The default config (`~/.config/rediacc/rediacc.json`) is created automatically on first use. `rdc config init <name>` creates a named one, `--config <name>` selects it, and `rdc config current` shows the active one.

### CLI Code Structure

`packages/cli/src/` splits four ways: `commands/` (hand-registered Commander subtrees), `remote/` (SSH, SFTP, rsync, terminal, VS Code), `services/` (domain logic, no barrels) and `utils/`. The domain list and tests layout are in [docs/agent-reference/cli.md](docs/agent-reference/cli.md).

### How the Local Adapter Works

The CLI reads machine and repo config from the active config file and connects over SSH directly; `LocalResourceState` reads that file directly too.

## Terminology

When writing documentation, help text, error messages, or code comments, follow these rules:

- **No "modes"**: Say "local adapter", never "local mode".
- **One adapter**: `local` is the only adapter. The experimental cloud adapter (middleware-backed) was removed; do not reintroduce cloud/middleware terminology.
- **Config auto-creation**: Default config is created automatically on first use. Don't tell users to run `rdc config init` for the default config. `config init <name>` is for named configs only.
- **Keep docs concise**: No verbose explanations or workarounds for error messages. Document what the command does, not how to work around issues.
- **The work is the subject, not the person**: the second person and the first person stay out of prose, commit messages and PR bodies, and praise goes to the work.
R1-R18, and the single file they live in, are in [docs/agent-reference/prose-style.md](docs/agent-reference/prose-style.md), enforced by `check:ci-prose-style` and two hook guards. That gate is shrink-only, so a green means no NEW finding rather than a clean tree, and nine of the eighteen rules are advisory by declaration rather than enforced.

## i18n / Translations

English (`packages/www/src/i18n/translations/en.json`) is the source of truth; the 12 other locales are DERIVED and **naturalized** — idiomatic, never word-for-word. Optimize English first, then lock it with `npm run i18n:generate-hashes`; on an English change re-translate only the delta. `check-i18n-naturalization` blocks `check:i18n` when a naturalized key goes stale.

**Read [docs/i18n/CONVENTIONS.md](docs/i18n/CONVENTIONS.md) before touching any translation.** It carries the pipeline, the per-language ledger, and why `--model haiku` is the default.

## Local environment (setup, devbox, `./rdc.sh`)

`./run.sh setup` prepares a machine idempotently and hands back a URL: host tools, docker, the devcontainer image, then ONE devbox container per worktree behind a shared traefik proxy, so the machine publishes exactly one port. `./run.sh devbox up|status|stop|shell|logs` drives it. Servers inside the devbox must bind `0.0.0.0` (`REDIACC_DEV_BIND`) or traefik answers 502.

Bare `./rdc.sh` targets PRODUCTION. Local development is an explicit opt-in, `./rdc.sh --dev` (or `RDC_DEV=1`); bench is just another config, `./rdc.sh --config bench`. There is no `RDC_PROD` or `RDC_BENCH`.

**[docs/agent-reference/local-env.md](docs/agent-reference/local-env.md)** carries the rest, and is worth reading BEFORE fighting any of it rather than after.

## Build & Test

**This monorepo uses npm, not pnpm.**

`.npmrc` enforces supply-chain hardening: `ignore-scripts=true`, `allow-git=none`. The 24h dependency freshness window is NOT npm hardening: npm never enforces it, and it lives in `.ci/config/release-age.json` (`minimum_release_age_minutes`), where the repo's dependency gates read it. The `ignore-scripts` flag blocks all dependency lifecycle scripts; after every `npm install` or `npm ci`, run `npm run install:natives` to compile the three packages that genuinely need scripts (ssh2, cpu-features, esbuild). The script passes `--ignore-scripts=false`
explicitly because `npm rebuild` otherwise silently respects the global flag and does nothing. Source of truth: `.ci/scripts/quality/check_npmrc.py`.

### npm 11 is the only npm

npm 11, at the exact `NPM_VERSION` in `.devcontainer/toolchain.env`, is the only supported npm, locally and in CI. `.github/actions/setup-node-npm` installs it in every workflow and is the only permitted `actions/setup-node` site; the devcontainer and every Dockerfile stage that runs `npm ci` install it too. `check:ci-lockfile` resolves each lockfile under that npm and refuses one the pinned npm would rewrite, so after any lockfile change `npx -y npm@<NPM_VERSION> install --package-lock-only --ignore-scripts` in the lockfile's directory writes the form to commit.

```bash
# Install dependencies
npm install && npm run install:natives

# Build shared package (required before www or cli)
cd packages/shared && npm run build

# Type check
npx tsc --noEmit --project packages/cli/tsconfig.json

# Run tests
cd packages/cli && npm test

# Build website
cd packages/www && npm run build

# Dev server (website)
cd packages/www && npm run dev
```

## Versioning

Version source of truth: **git tags** (e.g., `v0.8.3`). No version bump commits; injected at build time only, never stored in source, so every `package.json` carries the `0.0.0-dev` placeholder and none is published to npm.

**[docs/agent-reference/versioning.md](docs/agent-reference/versioning.md)** carries `resolve-version.sh`'s mechanics, the per-component injection table (CLI, CLI Docker, www, renet), and `bump.sh`'s two push-to-main-only call sites.

## Release Channels

Two channels, both production-quality: **edge** (continuously deployed on every merge to main) and **stable** (the default, promoted from edge after a 7-day soak).

**[docs/agent-reference/release-process.md](docs/agent-reference/release-process.md)** carries the channel URLs, the R2 layout, and the dispatch commands.

## Media Assets (tutorial/solution videos + tutorial-narration audio)

Tutorial and solution videos and the tutorial-narration audio cache live in Cloudflare R2 (bucket `rediacc-www-media`, served at `media.rediacc.com`), not in git. A fresh checkout has none of them and does not need them for `npm run dev`: the site fetches from the CDN at runtime and the two CI gates check the manifest, not the filesystem.

**[docs/agent-reference/media-assets.md](docs/agent-reference/media-assets.md)** carries the four prefixes, the pre-publish completeness gate that must never leave `publish-solutions.sh`, the audio-cache exception to the Cache Rule, the sync scripts, and both consequences of the 2026-08-23 history rewrite that changed every commit SHA in the repository.

## CI/CD Pipeline

Single pipeline: CI validates everything BEFORE publish. CD is a thin promote step, and if CI fails, CD never triggers.

```
CI: quality -> build -> dry-run -> validate install (6 platforms) -> ci-complete
CD (auto on CI success): promote Docker -> git tag -> GitHub Release -> R2 -> deploy edge
```

**[docs/agent-reference/release-process.md](docs/agent-reference/release-process.md)** carries `release_mode`'s semantics (GitHub itself rejects anything but `patch`/`retry`), the hotfix and workers-only dispatch inputs, and the 7-day soak / `force` behavior on the production promote.

## Quality Gates and the BLOCKER convention

`npm run ci` runs the checks CI runs. Three things live in their own files because they are lookup material, not standing rules:

- **[docs/agent-reference/ci-gates.md](docs/agent-reference/ci-gates.md)** — what `npm run ci` covers,
the quick fix for each gate, CI failure triage, the fix cycle, watchdog and auto-retry semantics, and the rule against pushing `main` or releasing unasked. **Read it when a gate fails or before touching CI.**
- **[docs/agent-reference/suppressions.md](docs/agent-reference/suppressions.md)** — every escape hatch
(allowlists, blocklists, overrides) and the `BLOCKER:` reason each one must carry, plus the liveness gate that proves a reason is still true. **Read it before adding an entry to any allowlist, and never suppress a gate to get past it.**
- **[docs/agent-reference/TRAPS.md](docs/agent-reference/TRAPS.md)** — ways a session gets FOOLED rather
than blocked: a check that cannot fail, a ruling taken on faith, a comment that invites the deletion of the line it guards, an error that was only ever hiding the next one. **Read it when a result looks clean and the question of what it would look like if the check had not run is still unasked.**

### The shape of the gate estate

Both tables below are GENERATED from `scripts/ci-runner/gates.lock.json` and `.claude/settings.json` by `npx tsx scripts/gen/gen-docs.ts --write`, and verified by `gate-test:docs-gen`, which fails on drift either way. Do not hand-edit between the markers, and do not quote a number out of them into prose elsewhere: that is how `ci-gates.md` came to tell readers there were "254 fast
gates" against a live 312. Per-gate detail is in [docs/agent-reference/ci-gates.md](docs/agent-reference/ci-gates.md).

<!-- >>> gen-docs: gates-summary -->

Scans: scripts/ci-runner/gates.lock.json, folded to one row per CI lane.

| Where it runs | Registered | `gate: true` | Slow | Is a gate test |
|---|---|---|---|---|
| (all lanes) | 357 | 347 | 63 | 5 |
| local-only (CI never runs it) | 13 | 10 | 4 | 0 |
| step / build-renet | 1 | 1 | 1 | 0 |
| step / quality-branch | 9 | 9 | 0 | 0 |
| step / quality-code | 103 | 102 | 19 | 0 |
| step / quality-content | 45 | 45 | 5 | 0 |
| step / quality-go | 16 | 16 | 3 | 0 |
| step / quality-i18n | 40 | 38 | 3 | 0 |
| step / quality-packages | 13 | 13 | 6 | 0 |
| step / quality-security | 25 | 24 | 3 | 5 |
| step / quality-static | 64 | 64 | 4 | 0 |
| step / quality-wiring | 1 | 1 | 0 | 0 |
| step / quality-www-build | 16 | 13 | 15 | 0 |
| test (a gate test drives it) | 11 | 11 | 0 | 0 |

14 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->

The last hook row is the one to act on: a tracked file under `.claude/hooks/` that nothing reaches, transitively, from that wiring is dead code beside live guards. The `hook-guards` region of [scripts/data/doc-registry.md](scripts/data/doc-registry.md) names them.

<!-- >>> gen-docs: hook-summary -->

Scans: the `hooks` wiring in .claude/settings.json, folded to one row per event, with the unreached residue.

| Hook event | Matchers | Hook files |
|---|---|---|
| PostCompact | 1 | 1 |
| PostToolUse | 2 | 2 |
| PreCompact | 1 | 1 |
| PreToolUse | 4 | 1 |
| SessionStart | 1 | 1 |
| Stop | 1 | 1 |
| SubagentStop | 1 | 1 |
| TeammateIdle | 1 | 1 |
| (all events) | 12 | 5 |
| (tracked hook files nothing reaches) | - | 17 |

10 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->
