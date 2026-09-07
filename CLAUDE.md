# Rediacc Console Monorepo

## Worktree Warning

**CRITICAL: This repo uses git worktrees.** Your working directory (from `pwd`) is the ONLY correct project root. NEVER use paths from other CLAUDE.md files that may appear in the system context — those belong to the main worktree and are a different checkout. All commands (`./run.sh`, `npx tsx`, file paths) MUST use the current working directory, not `/home/muhammed/monorepo/console/`.

**`git worktree add` is hook-blocked from the assistant's own Bash tool** (`.claude/hooks/pre-bash/block-worktree-add.sh`), unconditionally — the operator runs it themselves via the `!` prefix when they want one created. On top of that hard block: **if a new task starts and no worktree exists yet for its branch, ASK the operator first** (AskUserQuestion) whether to create one, rather than silently working in whatever checkout you're already in. Reserve the ask for genuinely new work; do not re-ask mid-task or for a task that already has an obvious home (e.g. continuing in the checkout you were invoked in). Do not decide either way on your own — this has gone wrong both directions: sessions have created throwaway worktrees the operator didn't want, and sessions have run for a long time directly on `main` in the shared checkout when a dedicated worktree would have kept concurrent sessions' work from colliding.

## Session Defaults

Standing rules for every task, in this repo and its submodules. The operator should never
have to restate them.

### 1. Work stays uncommitted until asked

The default deliverable is an **uncommitted working tree**. Do not `git commit`, create a
branch, push, or open a PR unless the operator asks for it in that task. Approving a plan
is not approval to commit. (`main` and releases carry stricter rules; see *Never push to
`main` or cut a release without explicit user authorization*.)

**And when a PR is asked for: ONE open PR at a time.** New work goes onto the branch of
the PR that is already open, not into a second one. This is enforced by
`.claude/hooks/pre-bash/block-second-open-pr.sh` rather than left to memory, because it
was left to memory once and a single night produced four stacked PRs: each new one was
individually reasonable, and the pile arrived on the operator, who then had to review and
merge them in a fixed order. A second PR does not get work finished sooner, it splits one
decision into several. A genuinely independent second PR is the operator's call; ask, and
say why the work cannot ride the open one.

This means there is **no safety net**, and the tree usually holds work from other sessions
and agents:

- Never `git checkout` / `restore` / `stash` / `clean` to undo your own mistake. It
  deletes uncommitted work, including work that is not yours. Repair forward instead.
- Prefer targeted edits over scripted bulk rewrites. If you must script one, re-verify the
  WHOLE file afterward, not just the part you aimed at. A find-and-replace scoped wider
  than you intended lands in a neighbouring key, function, or file, and your own
  verification will miss it if it only re-checks the target.

### 2. Findings are part of the deliverable

A session is scoped to one ask, but it walks past real defects on the way. Walking past
them silently is the failure this rule exists to prevent.

- **A workaround is a bug report.** If you route around something (a command that prints
  nothing, a flag that misbehaves, an error that explains nothing), you have found a
  defect. Say so, with the exact command and the exact output. Do not quietly take the
  long way and leave the bug for the next session to rediscover.
- **Discovery is always in scope, and so is the fix.** A finding is fixed in the
  session that finds it. Filing an issue never closes a finding. Small and local
  (no new abstraction, no signature change rippling outward): fix it inline
  immediately and say you did. Bigger than that: ask the machinery
  (`worklist.py --triage <me> <finding...>` answers INLINE, PLAN+SUBAGENT, or
  OPERATOR-ONLY with the exact next command), have a Plan agent write the design
  to `agent/PLAN-<slug>.md` (committed, survives compaction), then
  implement it THIS session: via a writer sub-agent when the fix's file set is
  disjoint from your current work or your context is heavy (disjoint ownership,
  max 2, rule 4), inline otherwise. The fix rides the current PR when
  risk-compatible, otherwise its own branch cut the same session.
- **Issues are a last resort with exactly three doors:** the fix needs
  operator-only powers (secrets, purchases, external accounts, production
  deploys); the operator explicitly deferred it when asked; or the target is
  outside this session's write access. "It is big" is not a door. Any last-resort
  issue must carry the evidence (exact command, exact output) and a ready-to-run
  brief a future session can execute without rediscovery, and its worklist item
  closes only with the door named in the tick evidence (`door:operator-only`,
  `door:operator-deferred`, or `door:no-write-access`).
- **Unblocking and cross-boundary fixes: do the minimum, then say so loudly.** A gate or
  lint rule blocking the task, or a defect in another package or submodule, still gets
  fixed. Make the smallest change that works and flag it in the summary as something the
  operator did not ask for, rather than burying it in the diff. Never suppress a gate to
  get past it (see the BLOCKER convention).
- **Sweep the class, not the instance.** Before calling a bug fixed, grep for its
  siblings. One bad call site usually has several.
- **Ask for the big-bang, not for permission to patch one thing.** The operator prefers
  ONE comprehensive change over a trickle of small ones, and will usually say yes. So when
  findings cluster, do not ask about them one at a time and do not propose the minimal
  patch: put the whole cluster into a single plan (root cause, siblings, tests,
  regenerated artifacts, submodules included) and ask to run it. Ask as soon as the
  cluster is visible, not after you have spent the session working around it.
  The ask decides PACKAGING (one comprehensive change versus riding the current
  PR), never WHETHER the findings get fixed: park the ask as a [?] whose
  DEFAULT is "fix the cluster this session", and keep working anything that is
  safe under either packaging while it waits.
- **Clean break, no compatibility theater.** There is one operator and no external
  consumers. Fix the root cause; do not add migration commands, deprecation windows,
  fallbacks, or dual code paths to preserve behavior nobody depends on.
- **Once a big-bang is approved, do not descope it unilaterally.** Fan out subagents if it
  is large (rule 4). Never quietly downgrade a piece to a stub, a TODO, or a "follow-up
  issue". If something genuinely cannot be done, say which piece and why, out loud.
- **Track findings in the worklist, not in your head.** The Stop hook
  (`.claude/hooks/stop/worklist.py`) refuses to end a turn while any open item
  remains. It is per-REPO, not per-session, so open items survive a restart and a
  fresh session inherits them.
- **Use the VERBS, not the file.** Since v10 the store is an append-only JSONL
  event log, and the hook prints a `WORKLIST GUIDE` on every full stop naming the
  exact next command per item. Base your `## Remaining` section on that guide, not
  on memory: it exists because hand-written status silently ignored the tracked
  ages, and on its first stop it caught a watch still reported as "ongoing" that
  had finished 51 minutes earlier.

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

  Item ids are hex but NOT fixed width: items migrated from the old markdown
  carry 12 characters, newly added ones 8. Never parse them assuming a length.
- **The store is shared, so never hand-edit it.** A second session may be running
  in this worktree, and two read-modify-writes lose the loser's items silently.
  The verbs append one event under a lock, which is what makes concurrent use
  safe. The legacy markdown file is still synced for compatibility, but writing to
  it directly is not the interface any more.
- **Tag every item `(<session-id-prefix>)`. The tag is load-bearing, not a label.**
  The hook blocks only on items tagged with YOUR session (an untagged item counts as
  yours, so forgetting the tag is safe but claims it). Other sessions' open items are
  REPORTED to the operator, never blocked on. Without ownership a second session
  deadlocks: it cannot do those items without racing live work in the same tree, and
  it must not tick or delete another session's tracking. Never tick or remove an item
  that is not yours.
- **A COMPACTION is the one case where a peer is really you, and `--adopt` is how you
  say so.** A compaction can hand one continuous conversation a new session id, and the
  rule above then fires against the session's own work. On 2026-09-02 that left four
  settled decisions open all night, reported to the operator every stop as a peer's,
  while the session reasoned about a peer that did not exist. If open items are
  attributed to a prefix you believe was you before a compaction, run
  `worklist.py --adopt <me> <prev>`. It records the edge only on harness evidence -- a
  `compact_boundary` your transcript opens with, plus conversational record uuids both
  transcripts share -- and there is deliberately no `--force`: two genuinely concurrent
  sessions share zero such records, which is what makes the check a refutation rather
  than a formality. Nothing is rewritten, so the `(<prefix>)` tag keeps naming whoever
  really wrote the item. **Do not guess.** Same cwd, same branch and adjacent times are
  ROUTINE for concurrent sessions in this tree, so they prove nothing; if `--adopt`
  refuses, the items are not yours.
- **Defer as a QUESTION, not a note.** Four states, and only four: `- [ ]` open,
  `- [x]` done, `- [?]` needs an operator decision, and `- [>]` in-flight on
  BACKGROUND work. A `- [>]` lease carries a UTC expiry (max 120 min ahead) AND a
  `worker:<bg-id>`, because since v10 the hook VERIFIES that worker against the
  operating system rather than believing the claim. A worker that cannot be
  verified is reported as unverifiable, never accused of being dead; only a worker
  the event itself has dropped counts as gone. An item with no live worker enters
  the 45/90/120 minute ladder: ping, then investigate, then resolve.
- **A `- [?]` must carry `DEFAULT:`, and the default EXECUTES.** Autonomy is
  time-boxed, not indefinite: an unanswered deferral whose window closes becomes an
  order to do the default and tick it with evidence, draining a few per stop.
  Reserve `- [?]` for decisions that are genuinely the operator's: anything you can
  settle from the code, the request, or a sensible default is yours to do, and
  parking it as "blocked on you" wastes a round trip. Thirty open deferrals is a
  symptom of over-asking, not a queue.
- **End with what remains**, which under this rule is short: operator-deferred
  `[?]` items and last-resort issues with their doors named. A "found, not
  fixed" entry that fits neither category means the fix-in-session rule was
  not followed; go back and fix it.
- **`## Remaining` is a list of things you CANNOT do right now, not a to-do
  list.** An item belongs there only if it is (a) `[?]` awaiting an operator
  answer, (b) `[>]` leased to a verifiably live worker, (c) waiting on a
  specific external run, or (d) a last-resort issue with its door named.
  **Nothing else may appear.** If you catch yourself writing "blocked on:
  nothing" — or "next up", or "ready to start" — that is not a status, it is a
  confession that you are stopping with work in hand. Delete the line and do
  the work.

  **This is the failure this section exists to prevent, and it has happened.**
  Over roughly ten consecutive stops in one session, the loop was: hook pushes
  back -> do exactly ONE item, or only a maintenance chore (rewrite STATE.md,
  refresh the brief, update a plan) -> stop again -> hook pushes back. The
  session reported several items as "Blocked on: nothing" and stopped anyway,
  with no background agent and no monitor running. The hook itself eventually
  fired `NOTHING HAS MOVED IN 3 CONSECUTIVE STOPS`. The operator had to
  intervene.

  Two mechanisms make this easy to fall into, so name them:
  1. **The hook's checks become a substitute for progress.** STATE.md
     staleness, the session brief and plan freshness are each individually
     correct, and together they supply an endless stream of hook-satisfying
     NON-work. Satisfying a check is not shipping anything.
  2. **A push-back is not a work order for one item.** The hook naming the next
     item does not mean "do that one and stop". It means the queue is not
     empty. Drain it: keep going until every remaining item is genuinely (a)-(d)
     above.

  The operator's asks decide PACKAGING, never WHETHER (rule 2). "Waiting for
  the operator to pick a branch" does not block the code that would go on
  either branch — write it under the default and let the answer choose where it
  lands. And a turn that ends is a turn that costs a round trip: the bar for
  stopping is "there is genuinely nothing I can advance", not "I have produced
  a defensible report".

### 3. Verify before you claim

- **Run the real thing.** Output, exit-code, and error-path defects are invisible to code
  reading and to mocked tests. Drive the actual command and read stdout and stderr
  SEPARATELY: a wrapper that swallows output, or progress text landing on stdout, only
  shows up in the raw bytes.
- **A plan's claim about code you have not read is a hypothesis.** Verify the load-bearing
  ones before relying on them. Approved plans are wrong about real code often enough that
  the first live run is part of the implementation, not a formality.
- **Do not trust a report you have not spot-checked**, including a subagent's and your own
  from earlier in the session. Check the artifact, not the summary of it.
- **Name the gates you ran, and the ones you skipped.** Before calling a failure
  pre-existing or environmental, show that none of its findings are in files you touched.
- **"Cannot be done here" is a claim, so probe it before you make it.** Closing an item
  as impossible without running the command that proves it is how work gets abandoned
  while sounding diligent. A CRIU pin bump was reported as needing infrastructure this
  session did not have; `docker version` answered in one second, and it did.

### 4. Reach for subagents on investigation and planning

Reading and thinking parallelize well here; writing does not. Use them accordingly.

- **Investigate with them by default.** Any question that means sweeping several files,
  packages, or naming conventions goes to `Explore` or `general-purpose` agents rather
  than into your own context. Read-only fan-out is cheap: run several at once. Ask each
  for conclusions with `file:line` evidence, never file dumps.
- **Plan with them on anything non-trivial.** For a design with real trade-offs, run
  `Plan` agents (up to 3, different angles) and synthesize. Their plans are proposals, not
  findings: check the load-bearing claims yourself before acting (see rule 3).
- **Writing agents: at most 2 at a time, with disjoint file ownership.** State the exact
  files each one owns and forbid it from touching any other. Two agents editing one file,
  or one agent running a repo-wide regenerate script, corrupts the tree. Also forbid
  `git checkout/restore/stash` and any `sync`/`regenerate` script in their prompts, for
  the reasons in rule 1.
- **Spot-check every agent's output against the artifact.** Their reports are accurate
  about intent and quietly wrong about placement. Verify structure across the whole file
  set they touched, not just the keys or symbols they claimed to change.
- **Model choice:** Opus for code and design, Sonnet for translation and naturalization.

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

## CLI (`packages/cli/`)

### Common Commands

The thing a command acts on is a **positional ref**, not a `--name` flag. A repo ref is
`name`, `name:tag` for a fork, and optionally `name@machine` to assert placement. The
machine is derived from the ref, so `-m/--machine` is gone from most repo commands (it
survives where there is nothing to derive from, e.g. `repo create`, or as a batch filter,
e.g. `repo up --all -m <machine>`).

```bash
# Full machine status (SSH + renet list all)
rdc machine status <machine>

# Filter by section: --system --containers --services --repositories --network --block-devices
rdc machine status <machine> --containers

# SSH terminal: one positional target, a machine name or a repo ref
# (a repo ref sets DOCKER_HOST and the working dir); -c runs one command
rdc term connect <machine>
rdc term connect <repo>
rdc term connect <machine> -c "command"

# Deploy/update a repository (machine derived from the ref)
rdc repo up <repo>

# File sync: a directory, or one file with --remote-file
rdc repo sync upload <repo> --local ./local-path
rdc repo sync download <repo> --local ./out --remote-file etc/config.toml

# Container logs / exec
rdc repo logs <repo> -c <container> --lines 50
rdc repo exec <repo> -c <container> -- <command>

# VS Code remote (one positional target, like term)
rdc vscode connect <repo>
```

### Config Setup

The default config (`~/.config/rediacc/rediacc.json`) is created automatically on first use.
`rdc config init <name>` creates a named one, `--config <name>` selects it, and
`rdc config current` shows the active one.

### CLI Code Structure

`packages/cli/src/` splits four ways, and the split is the thing to know rather than the file
list, which `ls` derives and a pasted tree does not:

- `commands/` hand-registered Commander subtrees, one file or directory per command
- `remote/` SSH, SFTP, rsync, terminal, VS Code server modules (this was `shared-desktop/`)
- `services/` business logic grouped by domain, concrete modules with no barrels: `account/`,
  `backup/`, `config/`, `core/`, `executor/`, `machine/`, `provision/`, `renet/`, `repo/`,
  `telemetry/`, `update/`, `tofu/` (the OpenTofu cloud-VM provisioning engine, reached from
  `commands/machine/provision.ts`), plus `state.ts` for `getStateProvider()`
- `utils/` cross-command helpers (command policy, agent guard, config schema, errors, platform, repo classify/target/executor)

Unit tests are central under `services/__tests__/`, mirroring `commands/__tests__/`.

### How the Local Adapter Works

The CLI reads machine and repo config from the active config file and connects over SSH directly; `LocalResourceState` reads that file directly too.

## Terminology

When writing documentation, help text, error messages, or code comments, follow these rules:

- **No "modes"**: Say "local adapter", never "local mode".
- **One adapter**: `local` is the only adapter. The experimental cloud adapter (middleware-backed) was removed; do not reintroduce cloud/middleware terminology.
- **Config auto-creation**: Default config is created automatically on first use. Don't tell users to run `rdc config init` for the default config. `config init <name>` is for named configs only.
- **Keep docs concise**: No verbose explanations or workarounds for error messages. Document what the command does, not how to work around issues.

## i18n / Translations

English (`packages/www/src/i18n/translations/en.json`) is the source of truth; the 12
other locales are derived. **Read `docs/i18n/CONVENTIONS.md` before touching any
translation.** Key rules:

- English must read as natural, daily language (grade 5-7 for marketing; technical for
  docs). Optimize English first, then lock it: after any English value change run
  `npm run i18n:generate-hashes`.
- Non-English values are **naturalized** (native, idiomatic phrasing, NOT literal /
  word-for-word). Never bulk-replace a locale file with machine/literal translations.
  Preserve every `{{placeholder}}`, HTML tag, number, and product name; mirror English
  keys/order/structure; change values only.
- **On English change, re-translate only the delta**: `npm run i18n:naturalize-status`
  lists the stale keys; re-naturalize just those via `private/growth/i18n_pipeline`
  (`./run.sh --lang <lang> --surface <surface>` — its ledger skips already-done keys).
- **Use `--model haiku`** (the default, cheapest capable model — English/Turkish were done
  on haiku; the ledger records the model per language). Only bump to sonnet/opus for a
  language whose haiku output reads awkward. Cost compounds ×12 languages.
- `check-i18n-naturalization` is a blocking gate in `check:i18n`: it fails when an
  already-naturalized key goes stale (English changed without re-naturalizing).

## Local environment (setup, devbox, `./rdc.sh`)

`./run.sh setup` prepares a machine and hands back a URL, idempotently: host tools, docker,
the devcontainer image, then ONE devbox container per worktree. Every container sits behind a
single shared traefik proxy routing by Host header, so the whole machine publishes exactly one
port. `./run.sh devbox up|status|stop|remove|shell|logs` drives the container and
`./run.sh setup --check` reports what is missing without changing anything. Servers started
inside the devbox must bind `0.0.0.0` (`REDIACC_DEV_BIND`), or traefik answers 502.

Bare `./rdc.sh` behaves like an installed `rdc` and therefore targets PRODUCTION. Local
development against the dev gateway is an explicit opt-in, `./rdc.sh --dev` (or `RDC_DEV=1`),
and bench is just another config, `./rdc.sh --config bench`. There is no `RDC_PROD` or
`RDC_BENCH`.

**[docs/agent-reference/local-env.md](docs/agent-reference/local-env.md)** carries the rest,
and it is worth reading BEFORE fighting any of it rather than after: the four setup steps,
why the docker-group gap closes itself, why `account db` serves sqlite-web and not Drizzle
Studio, why the container runs as YOU and why `node_modules` is not shared with the host, the
`--native` SEA loop, the `RDC_RENET_LICENSE=1` license reproduction and where its public key
does NOT come from, the `rdc run` escape hatch, `./run.sh rotation`, and `scripts/dev/`.

## Build & Test

**This monorepo uses npm, not pnpm.**

`.npmrc` enforces supply-chain hardening: `ignore-scripts=true`, `allow-git=none`, `minimum-release-age=1440`. The `ignore-scripts` flag blocks all dependency lifecycle scripts; after every `npm install` or `npm ci`, run `npm run install:natives` to compile the three packages that genuinely need scripts (ssh2, cpu-features, esbuild). The script passes `--ignore-scripts=false` explicitly because `npm rebuild` otherwise silently respects the global flag and does nothing. Source of truth: `.ci/scripts/quality/check-npmrc.sh`.

### The 27-line `package-lock.json` flip is npm 11 vs npm 10, and it is cosmetic

**npm 11 is canonical. This section said the opposite until 2026-09-06** (issue
#587): `main` had been carrying npm 11's lockfile since `42e6a18f8` while this
file called that form the deviation, so every session that read this section
"fixed" it back and the flip oscillated. The operator was asked directly whether
to revert the lockfile or migrate, and chose migrate. The direction below is
therefore inverted from what you may remember; the measurements are unchanged,
because the two forms differ only in the way described here.

A working tree can sprout a `package-lock.json` diff of exactly 27 lines, all
`"dev": true`, that nobody remembers making. Do not go hunting for the script
that "corrupted" it, and do not commit it either:

- **Trigger**: any `npm install`-family write run under **npm 10**
  (`npx -y npm@10 install --package-lock-only` reproduces it exactly), which
  ADDS 27 redundant nested dev markers that npm 11 omits. The canonical pin is
  `CANONICAL_NPM="npm@11"` in `check-lockfile.sh`, and `.devcontainer/Dockerfile`
  installs npm 11 so the environment that writes lockfiles writes that form.
  Under npm 11 the same 27 lines appear as DELETIONS, which is the shape this
  section used to describe as the fault.
- **CI still installs with npm 10**, and that is not a contradiction: setup-node
  with Node 22 bundles npm 10 and no workflow overrides it. Canonical means "the
  form we write", not "the only npm that has to read it". `check:ci-lockfile`
  runs `ci --dry-run` under BOTH majors for exactly this reason, so a form that
  npm 10 could not install would still be caught.
- **NOT the trigger**: `npm run install:natives`. `npm rebuild` does not write
  the lockfile, verified on both a warm tree and a fresh one straight after a
  clean `npm ci`. Nor do `npm outdated`, `npm ls`, or `npm audit`.
- **Impact: none.** All 27 entries sit under `node_modules/tsx/**`, and `tsx` is a
  devDependency still marked dev at its own node, so npm prunes the whole subtree
  regardless. `npm ci --omit=dev --dry-run` resolves the same 179 packages from *either*
  form, and `check:ci-lockfile` passes both under both majors (re-measured across all 11
  lockfiles on 2026-09-06). Diff noise, not a correctness problem: hence no gate.
- **Fix**: `npx -y npm@11 install --package-lock-only --ignore-scripts`
  restores the canonical form byte for byte. If you are on npm 11 already, a
  plain `npm install --package-lock-only --ignore-scripts` does the same thing.
- **That npm 10 pin is GONE, re-tested 2026-09-06.** `.ci/lib/local-common.sh`
  used to install with `npx -y npm@10` whenever the local npm was not 10,
  guarding a reproduced npm 11 hoisting defect (zod flattened to a 3.x
  transitive copy, breaking `packages/shared`). It no longer reproduces. THE
  CLEAN-ROOM RECIPE, which `check-lockfile.sh` cites by that name: copy the root
  manifests, the lockfile, `.npmrc` and all seven workspace `package.json` files to a
  scratch directory and run `npx -y npm@<major> install --ignore-scripts` there -- a real
  tree, because both a hoist and a peer ERESOLVE are invisible to `--package-lock-only`
  and `--dry-run`, neither of which writes a `node_modules`. Run that way on 2026-09-06,
  all eleven zod copies landed exactly where the npm 10 tree puts them, including
  `packages/shared/node_modules/zod` at 4.5.4. The likely cause is the
  `overrides` entry now forcing zod `^4.4.3` tree-wide. Removing the downgrade
  also closes the last path that rewrote the root lockfile into the
  non-canonical form on every local loop, which is what #587 exists to stop.

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

Version source of truth: **git tags** (e.g., `v0.8.3`). No version bump commits.

`resolve-version.sh --current` reads the latest tag and `--bump-type patch|minor|major`
calculates the next. The version is injected at build time and never stored in source, so
every `package.json` carries the `0.0.0-dev` placeholder and none is published to npm.

| Component | Injection method |
|-----------|-----------------|
| CLI binary | `CLI_VERSION` env -> esbuild `--define:__CLI_VERSION__` |
| CLI Docker | Same as CLI binary (bundle built with env) |
| www footer | `APP_VERSION` env / git tag fallback |
| renet (Go) | `-ldflags "-X main.Version=..."` |

`bump.sh` is still used by the CLI for the npm pack tarball name, on push-to-main only.

## Release Channels

Two channels, both production-quality. **edge** is continuously deployed: tagged and released
on every merge to main, downloaded from `cli/edge/`, serving `edge.rediacc.com` whose D1 is
cloned from production daily. **stable** is the default, promoted from edge after a 7-day soak,
downloaded from `cli/stable/`, serving `www.rediacc.com`. R2 layout:
`rediacc-releases/cli/{edge,stable}/{manifest.json,latest.json,rdc-*}`

## Media Assets (tutorial/solution videos + tutorial-narration audio)

Tutorial and solution videos and the tutorial-narration audio cache live in Cloudflare R2
(bucket `rediacc-www-media`, served at `media.rediacc.com`), not in git. A fresh checkout has
none of them and does not need them for `npm run dev`: the site fetches from the CDN at
runtime and the two CI gates check the manifest, not the filesystem. The git-history rewrite
that removed them landed 2026-08-23 and changed every commit SHA in the repository.

**[docs/agent-reference/media-assets.md](docs/agent-reference/media-assets.md)** carries the
four prefixes (the fourth is the one that was never mirrored to R2), the pre-publish
completeness gate that lives in `private/growth` and must never be removed from
`publish-solutions.sh`, the audio-cache exception to the Cache Rule, the sync scripts and
their credentials, and both consequences of the history rewrite.

## CI/CD Pipeline

Single pipeline: CI validates everything BEFORE publish. CD is a thin promote step.

```
CI: quality -> build -> dry-run -> validate install (6 platforms) -> ci-complete
CD (auto on CI success): promote Docker -> git tag -> GitHub Release -> R2 -> deploy edge
```

Install validation runs pre-publish against R2 staging artifacts. Docker is validated on push-to-main only (PR images are dry-run). If CI fails, CD never triggers.

Release dispatch (EDGE): `gh workflow run "Release to Edge" -f ci_run_id=<id> -f release_mode=patch|retry`
(the workflow declares only `patch` and `retry`; `minor`/`major` are rejected by GitHub)
Hotfix (edge + stable): `gh workflow run "Release to Edge" -f ci_run_id=<id> -f release_mode=patch -f publish_stable=true`
Production (eu/us/asia): `Release to Production` — daily cron after the 7-day soak, or dispatch with `-f force=true`.

## Quality Gates and the BLOCKER convention

`npm run ci` runs the checks CI runs. Three things live in their own files because
they are lookup material, not standing rules:

- **[docs/agent-reference/ci-gates.md](docs/agent-reference/ci-gates.md)** — what `npm run ci` covers,
  the quick fix for each gate, CI failure triage, the fix cycle, watchdog and
  auto-retry semantics, and the rule against pushing `main` or releasing unasked.
  **Read it when a gate fails or before touching CI.**
- **[docs/agent-reference/suppressions.md](docs/agent-reference/suppressions.md)** — every escape hatch
  (allowlists, blocklists, overrides) and the `BLOCKER:` reason each one must carry,
  plus the liveness gate that proves a reason is still true.
  **Read it before adding an entry to any allowlist, and never suppress a gate to
  get past it.**
- **[docs/agent-reference/TRAPS.md](docs/agent-reference/TRAPS.md)** — ways a session gets FOOLED rather
  than blocked: a check that cannot fail, a ruling taken on faith, a comment that
  invites the deletion of the line it guards, an error that was only ever hiding
  the next one. **Read it when a result looks clean and you have not yet asked what
  it would look like if the check had not run.**

### The shape of the gate estate

Both tables below are GENERATED from `scripts/ci-runner/gates.lock.json` and
`.claude/settings.json` by `npx tsx scripts/gen-docs.ts --write`, and verified by
`gate-test:docs-gen`, which fails on drift in both directions. Do not hand-edit between the
markers, and do not quote a number out of them into prose elsewhere: that is how
`ci-gates.md` came to tell readers there were "254 fast gates" against a live 312. Per-gate
detail is in [docs/agent-reference/ci-gates.md](docs/agent-reference/ci-gates.md).

<!-- >>> gen-docs: gates-summary -->

Scans: scripts/ci-runner/gates.lock.json, folded to one row per CI lane.

| Where it runs | Registered | `gate: true` | Slow | Is a gate test |
|---|---|---|---|---|
| (all lanes) | 458 | 448 | 95 | 149 |
| local-only (CI never runs it) | 12 | 9 | 3 | 0 |
| step / build-renet | 1 | 1 | 1 | 0 |
| step / quality-branch | 4 | 4 | 0 | 0 |
| step / quality-code | 91 | 90 | 19 | 0 |
| step / quality-content | 42 | 42 | 4 | 0 |
| step / quality-go | 16 | 16 | 3 | 0 |
| step / quality-i18n | 40 | 38 | 3 | 0 |
| step / quality-packages | 14 | 14 | 7 | 0 |
| step / quality-security | 166 | 165 | 37 | 149 |
| step / quality-static | 43 | 43 | 3 | 0 |
| step / quality-www-build | 16 | 13 | 15 | 0 |
| test (a gate test drives it) | 13 | 13 | 0 | 0 |

13 row(s). Generated by `npx tsx scripts/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->

The last hook row is the one to act on: a tracked file under `.claude/hooks/` that nothing
reaches, transitively, from that wiring is dead code beside live guards. The `hook-guards`
region of [scripts/data/doc-registry.md](scripts/data/doc-registry.md) names them.

<!-- >>> gen-docs: hook-summary -->

Scans: the `hooks` wiring in .claude/settings.json, folded to one row per event, with the unreached residue.

| Hook event | Matchers | Hook files |
|---|---|---|
| PostCompact | 1 | 4 |
| PostToolUse | 2 | 8 |
| PreCompact | 1 | 1 |
| PreToolUse | 3 | 5 |
| SessionStart | 1 | 3 |
| Stop | 1 | 1 |
| SubagentStop | 1 | 1 |
| TeammateIdle | 1 | 1 |
| (all events) | 11 | 15 |
| (tracked hook files nothing reaches) | - | 2 |

10 row(s). Generated by `npx tsx scripts/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->
