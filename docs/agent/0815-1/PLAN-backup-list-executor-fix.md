# PLAN: backup list reads the machine it runs on, locally
Status: executing
Owner: 97604f47
Updated: 2026-08-16

## TL;DR

`rdc backup list --machine <m>` asks machine `m` to SSH to itself and then looks in two
subdirectories (`hot/`, `cold/`) that nothing writes to on a machine any more. Both halves
must go:

1. Add a **local** source arm to `renet backup list` (`--source local`), which walks
   `<datastore>/repositories` with `os.ReadDir` instead of shelling out to `ssh`.
2. Stop inventing paths. List the datastore's repository directory itself, enumerate any
   non-GUID subdirectory found there (which is where a `hot/` or `cold/` tree would show up
   if one existed), and let `--path` mean exactly one path.

Dropping the invented paths is also what removes the `.catch(() => [])`: the swallow exists
only because the CLI guessed two paths that may not exist. When every listed path comes from
a `ReadDir`, every error is a real error and must surface.

---

## Root cause A: the executor machine and the source machine are the same machine

`resolveListExecutor` returns the same name in both roles
(`packages/cli/src/commands/backup.ts:36-38`):

```ts
if (opts.machine) {
  return { machine: opts.machine, sourceType: 'machine', from: opts.machine };
}
```

The caller then uses `machine` as the executor (`backup.ts:93`, `runOpts = { machine, ... }`)
and `{ sourceType, from }` as the source (`backup.ts:86`). `fetchBackupList` passes
`machineName` to the executor (`packages/cli/src/commands/repo-backup-list.ts:95,106-113`),
and the local executor SSHes to that machine and runs `renet execute --executor local` there
(`packages/cli/src/services/executor/local-executor.ts:8,698,2193`).

On the machine, the bridge builds an SSH-only command
(`private/renet/pkg/functions/commands/backup.go:740-765`): for `sourceType == machine` it
appends `--src-host`, `--src-user`, `--src-path` from `resolveMachineDetails`
(`backup.go:48-63`) and `--ssh-key /home/<machineUser>/.ssh/id_rsa` (`backup.go:761-764`).
`renet backup list` has exactly two arms, `machine` (SSH) and `storage` (retired)
(`private/renet/cmd/renet/backup_list.go:110-153`), and the machine arm requires `--src-host`
(`backup_list.go:118-120`) and always shells out to `ssh`
(`backup_list.go:200-267`, connection probe at `:212-216`).

So `m` opens an SSH session to `m` to read a directory on its own disk.

**Why it fails on a real machine, and why the fleet hides it.** Nothing in the product ever
places a private key on a CLI-provisioned machine: cloud provisioning injects only the
operator's *public* key (`packages/cli/src/services/tofu/provision.ts:69-86`), `rdc machine
setup` only runs `renet setup` (`packages/cli/src/commands/machine/register.ts:295`), and the
only per-machine `authorized_keys` writer is the repo key, which is pinned to a forced
`command="renet sandbox-gateway ..."` (`packages/cli/src/services/repo/repo-key-deployment.ts:20-40`)
and therefore useless for a listing. `/home/<user>/.ssh/id_rsa` exists only on the local ops
fleet, where `mesh` copies one shared private key to every VM (`private/renet/pkg/infra/mesh/mesh.go:281-292`)
after `ssh-copy-id`ing its public half (`mesh.go:265`), and on ceph VMs, which explicitly append
their own key to their own `authorized_keys` (`private/renet/pkg/infra/ceph/provisioner.go:1577-1586`).

That asymmetry is a trap for the test plan: **self-SSH succeeds on the KVM/mesh fleet and
fails on a customer machine.** A CI e2e leg on the fleet cannot prove cause A is fixed. Only
a test that makes `ssh` unusable can (see Test 3). Corroboration that machine-to-machine trust
is not a product feature at all: the dual-group migrate e2e establishes it by hand, with a
comment saying a real cross-DC migrate would too
(`packages/e2e-tests/tests/migrate/18-dual-group-migrate.test.ts:209-223`).

## Root cause B: it probes two hardcoded subdirectories that machine-side pushes never use

`backup.ts:99-109` fans out over `['hot', 'cold']` and `.catch(() => [])` on each.

`hot/` and `cold/` are the **storage** (rclone) layout, and only ever were. `buildPushParams`
prefixes the mode only for a storage target (`packages/cli/src/commands/repo-backup.ts:105-106`),
and `storageMode` is computed only when `resolvedType === 'storage'` (`repo-backup.ts:275-285`).
A machine push writes the bare GUID: `remoteFinalPath = <destPath>/repositories/<destName>`
(`private/renet/cmd/renet/backup_push.go:415-416`), and `backup_push` declares no `path`
parameter at all (`private/renet/pkg/functions/commands/backup.go:71-107`).

The storage arm is retired on both sides (`packages/cli/src/commands/repo-backup.ts:183-189`,
`private/renet/cmd/renet/backup_list.go:148-149`, `backup.go:767-769`), and scheduled backups
now run `renet backup snapshot` into the chunk store, with the rclone destination kind refused
outright since 2026-08-15 (`packages/cli/src/services/backup/backup-schedule-unit-generator.ts:118-128,144-172`).

**So on a machine, `hot/` and `cold/` are directories that nothing has written to since the
rclone arm was removed, and the flat `repositories/` directory that everything does write to
is the one path the command never looks in.** The task brief's premise that `hot`/`cold` are
"where SCHEDULED backup runs write" is now stale; correcting it is what makes the fix simple.

## Root cause C (same bug, third symptom): directory-shaped images are dropped by the renderer

`renderBackupList` filters out every entry with `isDirectory`
(`packages/cli/src/commands/repo-backup-list.ts:138-139`). A repository image is a *file* for
LUKS repos and a *directory* for directory-based (kube) repos: `backup push` branches on
exactly that (`private/renet/cmd/renet/backup_push.go:501-506`). So even where the listing
reaches the right directory, a pushed kube repo is silently discarded before it is printed.

The remote listing script has the matching asymmetry: non-directories are GUID-filtered,
directories are passed through unfiltered (`backup_list.go:227-230`), which is why the CLI
had to filter at all.

## Root cause D: a missing path and a failed listing are the same exit code

The remote script starts `cd '<path>' 2>/dev/null || exit 1` (`backup_list.go:219-221`), so a
subdirectory that does not exist produces exit 1 with no stderr, and renet reports it as
`failed to list files: exit status 1` (`backup_list.go:261-267`), indistinguishable from a
genuine failure.

Downstream, `fetchBackupList` does **not** throw on an execution failure: it renders the
failure and returns an empty array (`repo-backup-list.ts:115-121`), and
`renderLocalExecutionFailure` sets `process.exitCode = 1`
(`packages/cli/src/utils/local-execution-failures.ts:52,81,89-92`). That is exactly the
reported symptom: **exit 1, an error line, and an empty table printed underneath it.** The
`.catch(() => [])` at `backup.ts:105` is a second, independent swallow: it eats
`ValidationError`s thrown before dispatch (`repo-backup-list.ts:96,102-104`), which are
configuration errors the operator needs to see.

The repo already has the right instinct one file over: `listGuidsAtPath` in
`packages/cli/src/commands/storage.ts:104-121` distinguishes "directory not found" from a real
failure and throws on the latter, with a comment calling the swallow-all version a P1 hazard.

---

## Decisions (the four questions)

### Q1. What `--machine <m>` should mean, and whether renet can do a local read

**`--machine <m>` means "list the repository images stored on m".** Executor `m`, source
**local**.

A local read is **not supported today** and must be added: `renet backup list` has only the
`machine` and `storage` arms (`backup_list.go:110-153`), and the bridge FunctionDef declares
`sourceType` as `enum{machine,storage}` (`backup.go:205-216`), which the generated CLI-side
zod schema mirrors (`packages/shared/src/renet-contract/data/functions.schema.ts:24-31`). The
CLI validates params against that schema before dispatch
(`repo-backup-list.ts:98-99`), so the CLI **cannot** send `sourceType: 'local'` until the
renet contract is regenerated. That ordering is step 0 of the implementation.

Precedent that a local walk is cheap and already understood: `renet list repositories` does
`os.ReadDir(<datastore>/repositories)` with a GUID filter and per-entry `os.Stat`, reporting
size and mtime (`private/renet/pkg/list/repositories.go:46-52,96-108,202-217`). I am **not**
reusing it: the same function also runs Docker `Info` per socket and scans systemd units
(`repositories.go:53-71`), which is a lot of work for a listing, and its shape is
`RepositoryInfo`, not `BackupListEntry`. A stat-only walk in `backup_list.go` is about 40
lines and keeps the existing JSON payload shape that the CLI parser already handles
(`repo-backup-list.ts:37-65`).

### Q2. Enumerate instead of probing fixed names

**Yes, and enumeration belongs in renet**, one level deep, driven by `ReadDir` rather than by
a hardcoded name list. The rule that makes it unambiguous:

- entry name matches the GUID pattern (`backup_list.go:94`), file **or** directory: it is an
  artifact. Emit it.
- entry is a directory whose name is **not** a GUID (`hot`, `cold`, anything an operator
  made): it is a container. Emit its GUID-matching children, tagged with the subdirectory
  name.
- anything else, including the in-flight temp `.<guid>` that a push writes before the atomic
  rename (`backup_push.go:415`): skip. The GUID regex is anchored, so a leading dot already
  excludes it.

**Cost:** one `ReadDir` of `repositories/` plus one `ReadDir` per non-GUID subdirectory, plus
one `Stat` per emitted entry. No SSH, no Docker, no `du`. Directory-shaped images report
size 0, exactly as the remote script does today (`backup_list.go:238-241`); computing a real
size would mean walking every image and is not worth it for a listing.

### Q3. `--path`

`--path` keeps working and gets a sharper meaning: **exactly this path, no enumeration.** It
is joined onto `repositories/` as it is today (`backup_list.go:129-136`), and when it is
given, non-GUID subdirectories beneath it are not descended into. This preserves every
existing use (`rdc backup list -m m --path hot` still lists `repositories/hot`) and is the
only reading under which "the path does not exist" is unambiguously an error worth reporting:
the operator named it.

### Q4. Which failures surface

**All of them.** The distinction the brief asks for stops being needed once the CLI stops
guessing:

| Case | Behaviour |
| --- | --- |
| `--path <p>` given, `repositories/<p>` missing | error naming the path, non-zero exit. The operator named a path that is not there. |
| `repositories/` itself missing | error. A machine with a datastore always has it; its absence is a broken datastore, not an empty backup set. |
| a subdirectory found by `ReadDir` cannot be read (permissions, IO) | error. It existed one syscall ago. |
| no artifacts anywhere | success, exit 0, empty table. |

So: no `.catch(() => [])`, and `fetchBackupList` must **throw** on an execution failure rather
than rendering it and returning `[]` (`repo-backup-list.ts:115-121`), so the caller's
`handleError` (`backup.ts:115-117`) is the single exit path and no empty table is ever printed
under an error line. `fetchBackupList` has exactly one production caller (`backup.ts:95,102`),
so this is a local change; the only other reference is a vitest mock
(`packages/cli/src/commands/__tests__/backup-restore-datastore.test.ts:56`).

---

## What a user relying on today's behaviour would notice

`backup list` is shipping, so state it plainly:

1. **`-m <m>` starts returning rows.** Today it returns an empty table and exit 1 on any
   machine that cannot SSH to itself, which is every CLI-provisioned machine.
2. **The rows include the machine's own live repository images**, not only pushed copies.
   That is deliberate and cannot be filtered: a pushed artifact carries the *source repo's*
   GUID (`repo-backup.ts:105-106` passes `repositoryGuid` as `dest`), so any filter keyed on
   "GUIDs config knows about" would hide precisely the artifacts this fix exists to show. The
   Name column already resolves known GUIDs to names and leaves unknown ones raw
   (`repo-backup-list.ts:136-146`), which is the honest presentation of "what is on this
   machine's datastore".
3. **The `Mode` column becomes `Path`**, valued `-` at the root or the subdirectory name.
   "Mode" meant hot/cold, a concept that only ever existed for the retired storage arm.
   Renaming is a hand-edit of `COMMAND_OUTPUT_HINTS` (`packages/cli/src/config/command-docs.ts:500-503`)
   plus a contract regeneration; JSON consumers see the key change. If the operator prefers
   zero JSON churn, keep the key `mode` and only change its values, which is a one-line
   difference in step 4.
4. **`--storage` disappears** rather than throwing `storageRetired` (`backup.ts:39-47`).
   The refusal has been in place since the rclone removal, so nothing working breaks.
5. **Directory-shaped (kube) repo images appear** where they were silently dropped.

---

## Implementation, in dependency order

### Step 0. renet: local source arm (`private/renet/cmd/renet/backup_list.go`)

- Add `sourceTypeLocal = "local"` next to the existing constants
  (`private/renet/cmd/renet/backup_pull.go:33-34`, where `sourceTypeMachine`/`sourceTypeStorage`
  live).
- Add `Path string \`json:"path,omitempty"\`` to `BackupListEntry` (`backup_list.go:36-44`),
  carrying the subdirectory relative to `repositories/`, empty at the root. The client can no
  longer tag entries itself once renet enumerates, so renet must say where each entry came
  from. Additive, so the existing SSH arm keeps producing valid payloads.
- Add `listLocal(listPath string, enumerate bool) ([]BackupListEntry, error)` implementing the
  Q2 rules with `os.ReadDir` + `os.Stat`, reusing `guidPattern` (`backup_list.go:94`) and
  emitting RFC3339 UTC `ModTime` to match the remote script's format
  (`backup_list.go:246-251`).
- Wire the `case sourceTypeLocal:` arm into the switch at `backup_list.go:110`, before the
  `machine` case. It must not require `--src-host` and must not construct an `ssh` command.
- Errors: return the `os` error wrapped with the path. `runBackupList` already wraps as
  `list failed: %w` (`backup_list.go:155-157`), which surfaces to the CLI through the
  executor's captured stderr.
- Update the cobra `Long`/`Example` text (`backup_list.go:57-69`) so the local arm is
  documented; `--source` help text at `:79` still says "'machine' (SSH); 'storage' is retired".

### Step 1. renet: bridge FunctionDef and Build (`private/renet/pkg/functions/commands/backup.go`)

- `backup_list` FunctionDef (`backup.go:205-216`): add `local` to both `Options` and `Enum`
  for `sourceType`, make it the `Default`, and rewrite the description. Leave `from` **required**
  (`backup.go:212`): the CLI keeps sending the machine name, which is what the result's
  `Source` field reports and what `assertBackupFromExists` validates. Keeping it required
  makes the schema delta a pure enum widening.
- `BackupListCommand.Build` (`backup.go:736-777`): gate the `--src-host`/`--src-user`/`--src-path`/`--ssh-key`
  block on `sourceType == destTypeMachine` as it already is (`backup.go:752`), and add nothing
  for `local` beyond `--source local`. `AddDatastore` (`backup.go:741`, implementation at
  `private/renet/pkg/functions/commands/registry.go:261-266`) already forwards the datastore.

### Step 2. Regenerate the renet contract (blocking for anything CLI-side)

```bash
cd private/renet && go build -o bin/renet ./cmd/renet
private/renet/bin/renet functions generate-types \
  --output packages/shared/src/renet-contract/data --version dev
```

(exact text from `.ci/scripts/quality/check-renet-types.sh:74-77`; there is no npm script for
it). This is what lets the CLI's `validateFunctionParams` accept `sourceType: 'local'`
(`packages/shared/src/renet-contract/data/functions.schema.ts:24-31`). Gates:
`npm run check:ci-renet-types`, `npm run check:ci-renet-tiers`.

### Step 3. CLI command (`packages/cli/src/commands/backup.ts`)

- Delete `resolveListExecutor` (`backup.ts:31-49`) and the `--storage` option
  (`backup.ts:58`), the `placementExclusive` guard (`backup.ts:72-74`), and the two-path fan-out
  (`backup.ts:99-109`).
- The action becomes: require `--machine`, throw `placementRequired` (reworded) when absent,
  build `{ sourceType: 'local', from: machine }`, add `path` only when `--path` was given, one
  `fetchBackupList` call, filter by the artifact ref as today (`backup.ts:111-113`), render.
- Keep `[artifact-ref]` and its `startsWith` filter unchanged; `place-rules.test.ts:54` pins
  `backup list` as `optional-filter` and that stays true.

### Step 4. CLI fetch/render (`packages/cli/src/commands/repo-backup-list.ts`)

- `BackupListEntry` gains `path?: string` (`repo-backup-list.ts:10-15`); `TaggedBackupEntry.mode`
  is derived from it by the caller, or the interface renames `mode` to `path` outright if the
  column rename in Step 5 is taken.
- `assertBackupFromExists` (`:67-89`): add an explicit `local` arm mapping to
  `assertMachineExists`. Without it, `local` falls into the "unknown source type" branch
  (`:76-88`) and does a machine-then-storage probe, which happens to work and is exactly the
  kind of accident that rots.
- `fetchBackupList` (`:115-121`): throw instead of render-and-return-`[]`. The caller's
  `handleError` renders. Keep the renet output tail in the thrown error's message so the
  operator still sees the engine's own words.
- `renderBackupList` (`:138-139`): drop the `!e.isDirectory` filter. Sort by path then name
  (`:151-153`), header `Path` instead of `Mode` (`:155-161`) if Step 5 is taken.

### Step 5. Curated registries and locales

- `packages/cli/src/config/command-docs.ts:244-250`: delete the `--storage` example.
- `command-docs.ts:500-503`: `columns: ['path', 'name', 'guid', 'size', 'modified']` if
  renaming. **Nothing gates this against the renderer** (only `primaryKey ∈ columns` is
  checked, `packages/cli/scripts/generate-cli-contract.ts:467-474`), so Test 9 below closes
  that hole.
- `packages/cli/src/i18n/locales/en/cli.json`, `commands.backup.list`: delete `optionStorage`,
  `storageRetired`, `placementExclusive`, `examples.byStorage`; reword `optionPath` (it
  currently says "When omitted, hot/ and cold/ are listed and merged") and `placementRequired`
  (it currently offers `--storage`). Mirror in the other 12 locales by hand: the www
  naturalization pipeline does not cover CLI locales
  (`scripts/check-translation-hashes.ts:292-294`). Leaving a now-unused key in place fails
  `npm run check:ci-i18n-cli-key-usage`, so the deletions are mandatory, not cosmetic.

### Step 6. Regeneration order

```bash
npm run build:packages                            # package.json:19, both exporters need dist
npm run export:command-tree -w @rediacc/cli       # packages/cli/package.json:10
npm run generate:cli-contract -w @rediacc/cli     # packages/cli/package.json:11 (also the 13 i18n bundles)
npm run generate:cli-docs -w @rediacc/www         # packages/www/package.json:10 (re-runs the export internally)
npx tsx packages/cli/scripts/generate-skill-reference.ts > .claude/skills/rdc/reference.md
npm run i18n:generate-hashes                      # package.json:185, ALWAYS LAST
```

Gates bound to those artifacts: `check:ci-command-tree`, `check:ci-cli-contract` (diffs
`contract.json`, `contract.generated.ts` and all 13 locale bundles),
`check:ci-i18n-command-parity`, `check:cli-docs`, `validate:cli-docs -w @rediacc/www`,
`check:cli-examples`, `check:ci-command-planes`, plus `check:ci-renet-types` from step 2. The
skill reference has **no gate** (`scripts/check-cli-docs.ts:82-83`) and is already stale on
this very command (it still says "on a machine or storage"), so regenerate it deliberately.

### Step 7 (recommended, decide before starting): `--datastore <name>`

`backup list -m m` lists the machine's implicit default datastore. An artifact pushed into a
named datastore is invisible, which is the same class as issue #74
(`packages/cli/src/commands/repo-backup.ts:281-284`). The executor request type already
carries `datastore` (`packages/cli/src/services/executor/types.ts:45,77`) and the bridge
already forwards it (`registry.go:261-266`), so this is one option plus one passthrough, and
it costs nothing extra in regeneration because the surface is being regenerated anyway.
*Unverified by me:* that the executor's `datastore` option reaches `p.Datastore()` on the
renet side for a non-repo verb. Verify that before committing to it; if it does not, drop
step 7 and file it rather than half-wiring it.

---

## Test plan

Every test below is stated with the defect it is planted against. A test that cannot be made
to fail by re-introducing the bug it names does not count.

**Go, `private/renet/cmd/renet/backup_list_test.go`** (runs in CI: the `test-renet` job, no
account server, `RENET_EXPECT_NO_ACCOUNT_SERVER` is set at `.github/workflows/ct-tests.yml:1530`):

1. `TestListLocalFlatRootAndEnumeratedSubdirs`. Fixture: `repositories/<guidA>` (file),
   `repositories/<guidB>/` (directory image), `repositories/.<guidC>` (in-flight temp),
   `repositories/notes.txt`, `repositories/hot/<guidD>`. Assert exactly `{guidA, guidB,
   hot:guidD}`, with `guidB.isDirectory == true` and `guidD.path == "hot"`.
   *Fires on:* reverting to a hardcoded `hot`/`cold` probe (guidA vanishes); dropping the
   enumeration (guidD vanishes); dropping the GUID/dot filter (the temp and `notes.txt`
   appear); re-adding a directory filter (guidB vanishes).
   *Silent when clean.*
2. `TestListLocalPathErrors`. (a) `--path nope` against a fixture without it returns an error
   whose message contains `nope`. (b) a fixture with no `repositories/` directory returns an
   error. (c) an empty but existing `repositories/` returns zero entries and **no** error.
   *Fires on:* mapping ENOENT to "empty result" (a and b go silent); treating an empty
   directory as an error (c fires).
3. `TestListLocalNeverExecsSSH`. Prepend a temp dir to `PATH` containing an `ssh` shim that
   exits 42 and writes a marker file, then run the local arm. Assert success, correct entries,
   and that the marker does not exist.
   *Fires on:* the local case falling through to `listFromMachine` (`backup_list.go:200`), the
   exact defect of cause A. **This is the only test in the plan that can prove cause A**, since
   self-SSH works on the KVM fleet (`mesh.go:265,281-292`) and therefore masks the bug in every
   e2e environment CI has.
4. `TestBackupListBuildLocalArm` (`private/renet/pkg/functions/commands/`, alongside
   `backup_repo_guid_test.go`). `Build` with `sourceType=local` yields a command containing
   `--source local` and containing **neither** `--src-host` nor `--ssh-key`; with
   `sourceType=machine` it still contains both.
   *Fires on:* ungating the SSH block at `backup.go:752`, or forgetting `--source local`.
   Note the survey found **no** existing Go test asserting the `backup_list` FunctionDef param
   set, so this is new ground, not a duplicate.

**CLI vitest, new `packages/cli/src/commands/__tests__/backup-list.test.ts`** (runs in CI via
`npm run check:test-cli`, no account server; `backup_list` is licence tier `none`, pinned by
`packages/cli/src/services/__tests__/renet-license-tiers.test.ts:35`):

5. `sends one local listing`. Mock the executor; run `backup list -m prod-1`. Assert exactly
   **one** `backup_list` execute call, `machineName === 'prod-1'`, params
   `{ sourceType: 'local', from: 'prod-1' }`, and **no** `path` key.
   *Fires on:* restoring the `['hot','cold']` fan-out (two calls); leaving `sourceType:
   'machine'` (cause A, at the CLI boundary); sending a default `path`.
6. `--path is passed through verbatim and suppresses enumeration`. One call with
   `path: 'hot'`.
   *Fires on:* dropping `--path` handling, or re-merging it with a default path set.
7. `a failed listing does not print a table`. Executor returns `{ success: false, error: 'boom' }`.
   Assert non-zero `process.exitCode`, that `boom` reached the error output, and that
   `renderBackupList` was **not** called.
   *Fires on:* re-adding `.catch(() => [])` (`backup.ts:105`), or leaving `fetchBackupList`
   returning `[]` after rendering (`repo-backup-list.ts:115-121`), which is what produces
   today's "exit 1 plus an empty table".
8. `renders a directory-shaped image`. Feed `renderBackupList` a GUID-named entry with
   `isDirectory: true`; assert it appears in the rows.
   *Fires on:* the current `!e.isDirectory` filter (`repo-backup-list.ts:139`), i.e. cause C.
9. `output hints match the renderer`. Assert `COMMAND_OUTPUT_HINTS['backup list'].columns`
   deep-equals the column keys built in `renderBackupList`. Export the column list from
   `repo-backup-list.ts` so both sides read one array.
   *Fires on:* renaming a column in one place only. This closes a gap that no gate covers today
   (only `primaryKey ∈ columns` is enforced, `generate-cli-contract.ts:467-474`).

**E2E (bridge/KVM, account-free, CI-runnable):** add a leg to an existing suite that already
pushes between machines: `rdc repo push <repo> --to <machineB>`, then
`rdc backup list -m <machineB> --json`, assert the repo's GUID is present and the exit code is
0.
*Fires on:* cause B (today it returns an empty table, because `repositories/hot` does not
exist on B). *Cannot fire on:* cause A, for the mesh-key reason above. Say so in the test's
comment, or the next session will read a green e2e as proof of the wrong thing.
If this leg lands, `backup_list` must be **removed** from `.e2e-coverage-allowlist:20` in the
same change, because that gate fails as stale once a waived function becomes covered
(`.e2e-coverage-allowlist:1-9`).

**Not runnable in CI:** anything needing an account server. The only account-tier backup suite
is `packages/e2e-tests/tests/26-backup-storage-cli.test.ts`, whose config
(`playwright.backup-storage.config.ts`) is run by no workflow and is absent from
`LIVE_CONFIG_REGISTRY` (`scripts/check-e2e-coverage.ts:87-93`). None of the tests above need it.

**Manual verification before calling it done** (rule 3: run the real thing). On a real
CLI-provisioned machine, not a fleet VM:
`./rdc.sh backup list -m <machine>` with stdout and stderr captured separately, before and
after. Expect: before, exit 1 and an empty table; after, exit 0 and the datastore's images.
Then `./rdc.sh backup list -m <machine> --path nope` must exit non-zero and name `nope`.

---

## What I would NOT change

- **`-m/--machine` stays an option, and `[artifact-ref]` stays the positional.** The brief is
  right that this is a batch filter, not the object of the verb; `place-rules.test.ts:54` pins
  it. Converting it to a positional would be a second, unrelated migration.
- **No `requiredOption` for `--machine`.** Keeping the explicit `placementRequired` error keeps
  a message we control and can translate; Commander's built-in text is not localised.
- **No fan-out over all machines when `-m` is omitted.** It reads as a convenience and costs one
  SSH round trip per machine in the config, with partial-failure semantics nobody has designed.
- **`backup_pull`'s machine arm.** It has the *identical* two-arm switch
  (`private/renet/cmd/renet/backup_pull.go:357-398`), so `rdc backup restore <repo>@m -m m`
  (restoring an artifact that is already on the target machine) self-SSHes exactly like list
  did. It is a real sibling of cause A and it should be fixed, but not here: a local pull is a
  reflink/copy with its own delta, seed and licence paths (`backup_pull_delta.go`), which is a
  design, not a patch. **Named as a finding below rather than silently skipped.**
- **The chunk-store verbs** (`backup manifests|usage|verify|restore --at`). Different store,
  different index, untouched.
- **The GUID resolver in the renderer** (`repo-backup-list.ts:136-146`). It already does the
  right thing.
- **Filtering the machine's own live repos out of the listing.** Cannot be done correctly: a
  pushed artifact carries the source repo's GUID (`repo-backup.ts:105-106`), so the filter
  would hide the artifacts, not the noise.

---

## Adjacent findings (verified, outside this plan's edit set)

1. **`rdc storage prune` is dead on arrival.** It calls `backup_list` and `backup_delete` with
   `sourceType: 'storage'` (`packages/cli/src/commands/storage.ts:145-152,188-199`), which renet
   refuses outright (`private/renet/pkg/functions/commands/backup.go:767-769`, `backup_delete`
   at `:825-827`). The command is registered and reachable (`packages/cli/src/cli.ts:334`).
2. **A documented example that cannot work.** `rdc backup list --storage backups-s3`
   (`command-docs.ts:247-249`) is guaranteed to throw `storageRetired`. `check:cli-examples`
   validates example *syntax* against the command tree, not whether the command can succeed.
   Step 5 removes it.
3. **`.claude/skills/rdc/reference.md:477` is stale** ("on a machine or storage") and has no
   gate (`scripts/check-cli-docs.ts:82-83`). Step 6 regenerates it.
4. **`backup_pull` shares cause A** (see above), needing its own plan.
5. **No gate ties `COMMAND_OUTPUT_HINTS` to the actual rendered columns.** Test 9 covers this
   command; the class is wider.

## Unverified

- Whether the executor's `datastore` option reaches `p.Datastore()` for a non-repo verb
  (blocks step 7 only).
- Whether machine-side pushes *ever* wrote `hot/`/`cold/` historically. Every path I read
  gates the mode prefix on a storage target, but I did not walk the git history; if a machine
  in the field does have those directories, the enumeration in Q2 lists them anyway, which is
  why the design does not depend on the answer.
- The precise `os.Stat` failure modes on a btrfs subvolume mid-snapshot. Step 0 should treat a
  per-entry `Stat` error as a skipped-with-warning entry rather than a fatal listing error;
  I did not verify how the existing SSH script behaves there (`stat -c %s ... || echo 0`
  suggests it silently reports 0).
