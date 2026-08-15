# PLAN: Licence the restore target, so disaster recovery works on a bare machine

Status: draft
Owner: 97604f47
Updated: 2026-08-15

Scope: `renet backup restore` refuses on a machine that holds no repository
licence. That is the disaster-recovery case, so the verb fails exactly where it
is needed. This plan says which licence to issue, where the CLI issues it, what
it costs, and which tests fire when the fix is removed.

---

## 0. Framing correction, established before anything else

The `backup_restore` verb is **new, uncommitted work from this campaign**, not
shipped code:

```
$ cd private/renet && git status --porcelain cmd/renet/backup_restore.go pkg/license/tiermap.go
?? cmd/renet/backup_restore.go
 M pkg/license/tiermap.go
$ git show HEAD:pkg/license/tiermap.go | grep -c backup_restore
0
```

Two consequences:

1. This is a **design input to in-flight work**, not a bug report against a
   release. The fix rides the backup-storage program's own branch. It does not
   need its own PR, and the "one open PR at a time" rule is not in tension here.
2. A related observation is **not** a finding: `backup_restore` is absent from
   `packages/shared/src/renet-contract/data/license-tiers.generated.ts` (163
   entries at HEAD, zero hits for the name), so
   `getRenetFunctionLicenseTier('backup_restore')` returns `undefined`, which
   `renet-license-contract.ts:69-73` documents as "not registered" rather than
   "free". That is simply a generated artifact that has not been regenerated for
   a verb that does not exist upstream yet. **It is a landing requirement of the
   backup-storage program, not a defect**, and I am recording it here only so the
   regenerate step is not forgotten. `.ci/scripts/quality/check-renet-tier-map.sh`
   will fail on it once the Go side is committed.

Everything below is verified against the working tree at the line numbers given.
Where a subagent's anchor disagreed with mine, mine is the one I re-read.

---

## 1. Where the refusal happens, and what it accepts

`private/renet/cmd/renet/backup_restore.go:360-390`, verbatim:

```go
func resolveRestoreLicense(datastoreID, guid string) (
	*license.SignedRepoLicense, *license.RepoLicense, string, error,
) {
	if blob, err := license.LoadPreferredRepoLicense(datastoreID, guid); err == nil && blob != nil {
		if decoded, err := license.DecodeRepoLicense(blob.Payload); err == nil && decoded.RenewalURL != "" {
			return blob, decoded, guid, nil
		}
	}

	scopes, err := license.ListInstalledRepoScopes("")
	...
	for _, scope := range scopes {
		blob, err := license.LoadPreferredRepoLicense(scope.DatastoreID, scope.RepositoryGuid)
		if err != nil || blob == nil {
			continue
		}
		decoded, err := license.DecodeRepoLicense(blob.Payload)
		if err != nil || decoded.RenewalURL == "" {
			continue
		}
		return blob, decoded, scope.RepositoryGuid, nil
	}
	return nil, nil, "", fmt.Errorf(
		"no installed repository license on this machine (not for %s, and not for any other "+
			"repository): the backup session needs one as both credential and address book, and "+
			"nothing on the machine can mint one for a repository whose image does not exist yet",
		guid)
}
```

What it actually accepts, stated precisely:

- **Any** installed blob on the box, for **any** repository guid, in **any**
  datastore scope. The preference order is target-guid-first, then arbitrary
  (directory order from `ListInstalledRepoScopes`).
- The **only** acceptance predicate is `decoded.RenewalURL != ""`. Nothing else
  is checked locally. `DecodeRepoLicense` verifies nothing at all
  (`private/renet/pkg/license/store.go:239-242`: "parses a signed blob's base64
  payload WITHOUT verifying anything"). The type carries `HardExpiresAt`,
  `RepositoryGuid`, `GrandGuid`, `MaxRepositorySizeGb` and helpers
  `IsHardExpired()` / `NeedsRefresh()` (`types.go:10-40`, `:73-83`); the restore
  path calls none of them. Expiry and entitlement are the server's job at session
  mint.
- `ListInstalledRepoScopes` reads directory names only, no payloads
  (`store.go:182-219`), from `/var/lib/rediacc/license/repos/<guid>/` and
  `/var/lib/rediacc/license/datastores/<id>/repos/<guid>/` (`store.go:16-37`,
  `pkg/config/constants.go:93`).

Two downstream uses of the resolved licence, and only two:

- `backup_restore.go:202` : `sessionURL, err := backupSessionURL(decoded.RenewalURL)`,
  a pure suffix swap (`backup_snapshot.go:380-391`, renew-suffix in, session-suffix out).
- `backup_restore.go:210-224` : the raw blob is handed to `chunkstore.MintSession`
  as `Blob: blob`.

**The failure is not signalled as `LICENSE_REQUIRED`.** `runBackupRestore` returns
a plain `fmt.Errorf("restore failed: %s", record.Reason)`
(`backup_restore.go:150`), and there is no exit-10 emitter anywhere in
`backup_restore.go`. This matters for section 3: the CLI's existing
`LICENSE_REQUIRED` recovery framework
(`packages/cli/src/services/executor/local-executor.ts:974`,
`RENET_LICENSE_REQUIRED_EXIT_CODE = 10` at `renet-license-contract.ts:7`) can
never fire for a restore. That is the first of two structural reasons the gap is
invisible to the existing machinery.

The comment's own concession at `backup_restore.go:355-357` is accurate and I
verified it: the sole writer of a licence blob in renet is `writeRepoLicenseAt`
(`pkg/license/store.go:273`), whose only non-test caller is the renewal path
(`pkg/license/renew.go:318`), and the guid it writes under comes from a scope
directory that already exists. Renet has no mint or install verb; the only
`license` subcommand is `renew` (`cmd/renet/license_renew.go:25-35`). **Renet
cannot fix this on its own. The fix is necessarily CLI-side.**

---

## 2. WHICH licence to issue, and why

### 2.1 What the chunk store actually needs the licence for

This is the question that decides between the candidates, and the tree answers it
without needing the live round trip.

The blob is exchanged for a session. `authenticateLicenseBlob` does not exist in
renet (it appears only in the comment at `backup_restore.go:349`); the real one is
`private/account/src/services/subscription.service.ts:1147`, and it resolves the
**subscription** from the blob (Ed25519 verify, issuance-ledger chain-hash
cross-check, 40-day machine-id grace, `resolveEntitledSubscription`,
`checkRepoGuidOwnership`).

The session row persists only `subscriptionId`, `machineId`, `intent`,
`tokenHash`, `expiresAt` (`private/account/src/services/backup-storage.service.ts:187-195`;
`src/db/schema.ts:1540-1558` has no `repository_guid` or `lineage_guid` column).
The principal is correspondingly `{ sessionId, subscriptionId, machineId, intent }`
(`backup-storage.service.ts:84-89`).

Object keys are composed **server-side only**
(`private/account/src/services/backup-chunk-store.ts:44-55`):

```ts
tenantPrefix: (subscriptionId) => `t/${subscriptionId}/`,
lineagePrefix: (subscriptionId, lineageGuid) => `t/${subscriptionId}/l/${lineageGuid}/`,
```

so `t/<subscription>/` comes from the session principal and `l/<lineage>/` comes
from the **caller-supplied** `input.lineageGuid`. The client refuses to compose a
prefix at all (`private/renet/pkg/chunkstore/session.go:688-695`).

`mintReadGrant` (`backup-storage.service.ts:682-753`, route
`POST /backups/read-grants` at `private/account/src/routes/backups.ts:101-106`)
performs exactly four checks: data-plane configured, `intent === 'restore'`,
subscription row exists, and a manifest chain walk scoped by `subscriptionId`
that refuses a snapshot belonging to a different lineage
(`backup-storage.service.ts:653-658`). **There is no check that the requested
lineage matches the authenticating licence's grand guid.** `grep -rn "grandGuid"
private/account/src` returns zero hits in `backup-storage.service.ts`,
`routes/backups.ts`, or `backup-chunk-store.ts`.

On the renet side, restore never reads the grand guid out of the licence either:
`grep -n GrandGuid cmd/renet/backup_restore.go` returns nothing, and the lineage
comes from the `--lineage` flag (`backup_restore.go:104`, threaded to
`SessionControlPlane.Lineage` at `:226-230`). The backup (write) path is the one
that derives it from the licence (`backup_snapshot.go:240-249`).

**Conclusion, from code rather than from the round trip:** the isolation boundary
is the **subscription**, not the grand guid. A blob minted for grand A authorises
reading lineage B provided B belongs to the same subscription. The design comments
on both sides say this is deliberate (`backup-storage.service.ts:245-247`;
`backup_restore.go:348-352`).

### 2.1a Empirically confirmed, end to end

The `roundtrip` agent has since executed the real restore on the live fleet, and
it agrees with the reading above. The verb's own record on worker2:

```json
{"guid":"9c1de5f0-1111-4000-8000-abcdef000001","status":"restored",
 "snapshotId":"20260815T041418Z-c1e8778364245163",
 "lineage":"d2fe7d2c-ebb2-4aee-adaa-5c9bf03f5b13",
 "licenseFrom":"7a41b4dc-bff1-45ac-8be4-8d684d87590a",
 "chainDepth":1,"cellsTotal":256,"cellsZero":225,
 "chunksWanted":31,"chunksFetched":31,"chunksReused":0,
 "bytesFetched":130023424,"grantsMinted":2,"durationMs":5017}
```

`licenseFrom` is worker2's throwaway carrier (grand `7a41b4dc`), `lineage` is
worker1's source grand (`d2fe7d2c`), and 31 of 31 chunks were fetched, 124 MiB,
with the restored image byte-identical to the source. A licence minted for one
grand authorised, addressed, and completed a full read of a different grand's
objects.

The earlier hand probe isolated *where* the decision is made: a session mint with
the carrier blob returned HTTP 200 and resolved to the same `subscriptionId` that
worker1's licence resolves to, and the subsequent read-grant for the foreign
lineage returned `404 BACKUP_MANIFEST_MISSING` with the text "in this
subscription". A data refusal, not a scope refusal: a grand-scoped design would
have rejected the lineage before looking for a manifest.

So section 2.1 is no longer a code reading. **It is measured.** The fork is
closed on the permissive branch.

### 2.2 The candidates

**(b) A target-local licence, relying on the any-repo fallback (the carrier-repo
workaround, productised).**

The team lead's reading of the round trip is that (b) is now viable, because the
failure mode I was warned about ("a fix that passes and does not work") has been
ruled out. **The premise is right and the conclusion does not follow**, and this
is the one place where I am arguing against my own instructions, so I want to be
exact about why.

The measurement rules out **one** way (b) could fail: it proves the chunk-store
read is authorised. My rejection of (b) never rested on that. It rests on what
happens **after** the restore, in a part of the system the round trip did not
exercise, because the round trip drove `renet backup restore` directly over SSH
and stopped at the restored image.

The reason, and it is untouched by the measurement:

`rdc backup restore` has a `--up` flag on the same command
(`packages/cli/src/commands/backup.ts:165`, acted on at `:235-237`). `--up` runs
`repository_up`, which is `TierRepoLicenseOperate`
(`private/renet/pkg/license/tiermap.go:34`), and operate-tier resolves the licence
**guid-specifically**, with no any-repo fallback and no soft failure
(`private/renet/pkg/functions/executor_local.go:487-495`, verified by reading it
rather than by report):

```go
	if operate {
		repoLicense, err = license.ValidateInstalledRepoLicenseOperate(datastoreID, repoGUID)
	} else {
		repoLicense, err = license.ValidateInstalledRepoLicense(datastoreID, repoGUID)
	}
	if err != nil {
		return license.NewRequiredError(err)
	}
```

`repoGUID` there is the restored repo's own guid. A carrier licence satisfies
`resolveRestoreLicense`'s any-repo fallback, the restore succeeds exactly as the
round trip measured, and then the very next step returns `LICENSE_REQUIRED`.

**So (b) ships as "the restore succeeded and the repo will not start".** That is
the same class of defect as the original gap, moved one step later and made
harder to diagnose, because the restore's own record says `restored` and the
failure surfaces on a different verb. The round trip could not have caught it: it
stopped at the image and verified the bytes, which is the right scope for
answering the authorisation question and the wrong scope for answering this one.

The `roundtrip` agent's closing suggestion, that a CLI-side issue "does NOT need
to mint a licence for the restored guid specifically, any licence in the
subscription will do, which should simplify your design considerably", is correct
about the restore verb in isolation and wrong about the command. It also buys
nothing: issuing for the source guid and issuing for an arbitrary guid cost
**exactly the same** (one monthly issuance slot, section 6.2), take the same code
path, and send the same request. There is no simplification available, only a
choice of which guid to name, and one of the two choices additionally makes
`--up` work.

Two smaller strikes against (b): the carrier is a throwaway repo the operator did
not ask for, whose own creation consumes a second issuance slot; and its licence
is an orphan on the machine afterwards.

**(a) A licence for the SOURCE repository guid, issued to the TARGET machine,
installed under the TARGET datastore's identity. This is the recommendation.**

Defence, four independent reasons:

1. **It is the licence the restored repo needs anyway.** The restore registers the
   target config record with the source's guid:
   `packages/cli/src/commands/backup.ts:191-202`, `repositoryGuid: source.repositoryGuid`.
   So the licence issued before the restore is the licence `repository_up`,
   `repository_limits`, and every later operate-tier verb will look for. Nothing
   is orphaned and no second issuance is needed after the restore.
2. **It satisfies the restore check on the preferred path, not the fallback.**
   `LoadPreferredRepoLicense(datastoreID, guid)` hits on the first branch
   (`backup_restore.go:363`), so `record.LicenseFrom` names the target repo rather
   than an unrelated one, which is what an operator reading the record expects.
3. **It carries the right size cap.** The signed payload embeds
   `MaxRepositorySizeGb`, enforced server-side at issue
   (`subscription.service.ts:1324-1329`) and read back by
   `repository_limits.go:39`. A carrier licence minted for a 1 GB throwaway would
   cap a restored 500 GB repo. Section 4.2 says where the CLI gets the real size.
4. **It requires no server change.** `checkRepoGuidOwnership`
   (`subscription.service.ts:1739`) only refuses a guid already bound to a
   *different* subscription. The source repo's guid is already this
   subscription's, so issuance passes. The signed payload takes
   `grandGuid: input.grandGuid ?? input.repositoryGuid`
   (`subscription.service.ts:1361`), so the source lineage travels in the blob
   even though nothing currently reads it back on the restore path. That is
   deliberate belt-and-braces: if lineage scoping is ever added server-side, a
   licence issued this way is already correct, whereas a carrier licence would
   break on that day.

**(c) Something else, considered and rejected:** a dedicated "restore licence" or
a new server route that mints a short-lived read-only credential. It is a cleaner
security story (see the findings in section 7), but it is a new signed artifact
type, a new route, a new renet acceptance path, and a new expiry policy, for a
case that candidate (a) already covers with existing machinery. Not now. Recorded
as the shape to reach for if section 7's squatting finding is ever acted on.

### 2.3 What the command should DO on an unlicensed target

Asked directly by the team lead. Three options were on the table.

**Recommendation: issue automatically, silently, as a pre-flight.** No prompt, no
new flag, no error to read.

- **Against "fail with an actionable message naming the exact command":** this is
  the option that sounds responsible and is not. The operator running this command
  is, by construction, standing in front of a dead server. Every extra step is
  taken under time pressure by someone who may never have run the command before.
  More decisively, there is no honest message to write: the remedy today is the
  carrier-repo trick, and **the whole finding is that the operator should not have
  to know it**. Writing it into an error message ships the workaround as the
  product.
- **Against "prompt":** a prompt cannot be answered on the `-y` path, in a script,
  or in agent mode, which is where DR procedures actually run. It would also be
  asking the operator to authorise something they cannot evaluate, since the cost
  (section 6) is one monthly issuance slot they have no way to price at that
  moment.
- **For "issue automatically":** it is what `repo create` already does at the same
  seam (`local-executor.ts:1897-1917`), so it is the established behaviour of this
  codebase for "the machine needs a licence to do the thing you asked for"; the
  cost is bounded and self-releasing (section 6); and with the 6.3 skip probe a
  repeated or already-licensed restore costs nothing at all.

The visible behaviour should be one timed step in the existing timeline, exactly
as provisioning renders one (`t('timing.step.activating')` /
`'timing.step.licenseActivated'`, `local-executor.ts:1902`). The operator sees
that a licence was activated. They are never asked to do anything about it.

**Stated explicitly, because it is the point of the finding:** no part of this
design requires the operator to know about the carrier-repo trick, to create a
throwaway repo, or to understand that renet accepts any licence on the machine.
If any step of the implementation reintroduces that requirement, including as an
error message or a documented workaround, it has missed the finding.

---

## 3. Where the CLI change goes

### 3.1 Where it must NOT go

**Do not add `backup_restore` to the repo-provisioning set.** Two reasons, both
hard:

- `isRepoProvisioningFunction` (`packages/cli/src/services/renet/renet-license-contract.ts:141-145`)
  requires `functionName.startsWith('repository_')` **and** tier `create`.
  `backup_restore` fails the prefix. So does
  `resolveRepoLicenseContext`, which returns `null` at
  `packages/cli/src/services/executor/local-executor.ts:385`:
  `if (!functionName.startsWith('repository_')) return null;`
  (verified myself; a subagent reported `:387`).
- Renet deliberately makes restore `TierNone`, and the comment is the whole
  argument (`private/renet/pkg/license/tiermap.go:61-68`): "backup_restore is
  TierNone ... it is the DISASTER RECOVERY verb. A tier gate on it would mean an
  expired licence can lock a customer out of their own backed-up data". Promoting
  it to create-tier would reintroduce exactly the lockout this plan is trying to
  remove. The refusal in `resolveRestoreLicense` is an *implementation*
  requirement (a session needs a bearer blob), not a *tier* decision, and the two
  must not be conflated.

**Do not rely on the `LICENSE_REQUIRED` recovery framework.** It is unreachable
twice over: restore never exits 10 (section 1), and even if it did, the
non-provisioning branch of `maybeIssueLicense`
(`local-executor.ts:1197-1219`) calls `refreshRepoLicensesBatch`, which works from
a remote `renet ... license-scan` of **installed repositories**
(`packages/cli/src/services/account/license.ts:645-651`). A bare DR machine has
none, so the outcome is `no_known_repos` (`license.ts:83`). The recovery path
cannot help a machine whose whole problem is that it is empty.

### 3.2 Where it goes

A restore-specific pre-flight, structurally parallel to
`ensureRepoLicenseForProvisioning` (`local-executor.ts:1302-1346`) and placed
beside it, invoked from the same seam that already branches on function class.

**Seam:** `local-executor.ts:1897`, today:

```ts
if (isRepoProvisioningFunction(options.functionName)) {
  ... await Promise.all([runVerify(), runLicense()]);
} else {
  await runVerify();
}
```

Add a second arm for the restore case. Concretely, a new predicate
`isRestoreLicenseFunction(functionName)` (`functionName === 'backup_restore'`,
living in `renet-license-contract.ts` beside `isRepoProvisioningFunction` so the
two classifications stay in one file), and a new
`ensureRepoLicenseForRestore(options, machine, sshPrivateKey, remoteRenetPath, sftp)`
next to `ensureRepoLicenseForProvisioning`.

Why here and not in `runChunkRestore` (`backup.ts:386-423`): the command has no
SSH handle. `issueRepoLicense` needs an `SFTPClient` and the remote renet path
(`packages/cli/src/services/account/license.ts:398-447`), and it installs the blob
by `sudo tee` over that SFTP session's shell into
`/var/lib/rediacc/license/datastores/<datastoreId>/repos/<guid>/<keyId>.json`
(`license.ts:600-642`). All of that already exists at the `:1897` seam and nowhere
else. Putting the pre-flight in the command would mean opening a second SSH
session for it.

**`ensureRepoLicenseForRestore` body, differing from the provisioning version in
exactly three places:**

1. Same `REDIACC_SKIP_MACHINE_ACTIVATION === '1'` early return
   (`local-executor.ts:1310`) and same subscription-token acquisition
   (`:1314-1323`). Copy, do not refactor: the provisioning version is reached
   concurrently with machine verification and any shared helper would have to be
   correct for both.
2. **A different context resolver.** `resolveRepoLicenseContext` cannot be reused
   (prefix gate, and its size probe `stat`s an image that does not exist yet,
   `local-executor.ts:484-494`). Write `resolveRestoreLicenseContext`, which
   derives:
   - `repositoryGuid` from the target repo's config record, which
     `backup.ts:191-202` has **already written** before the executor runs, so
     `configService.getRepository(params.repository)` returns the source guid.
   - `grandGuid` from the same record (`source.grandGuid ?? source.repositoryGuid`,
     matching what `backup.ts:220` passes as `lineage`).
   - `kind` by the same rule as `buildRepoLicenseContext`
     (`local-executor.ts:426-428`): `grandGuid && grandGuid !== repositoryGuid ? 'fork' : 'grand'`.
   - `datastoreId` by **reusing `resolveProvisioningDatastoreId` unchanged**
     (`local-executor.ts:286-320`). It reads the placement from the config record,
     and `backup.ts:185-187` already writes `placement` for both the
     `--datastore` and the `--machine` case. This is the piece that makes the blob
     land where `datastore.IdentityAt(opts.DatastorePath)` will look for it
     (`backup_restore.go:195`); getting it wrong is a licence installed somewhere
     nothing reads.
   - `requestedSizeGb` from the **manifest**, not from the machine. See 4.2.
3. **A skip-if-already-present probe.** See section 6.3; this is what keeps a
   retried restore from burning an issuance per attempt.

**Server: no new or changed route.** `POST /account/api/v1/licenses/activate-repo`
(`private/account/src/routes/license.ts:140-160`) already accepts
`repositoryGuid`, `grandGuid`, `kind`, `requestedSizeGb`, `datastoreId` from an
`apiTokenAuth('license:activate')` caller and signs without requiring the
repository to exist anywhere server-side (there is no repository table:
`src/db/schema.ts` has only `subscriptionActivations`, `repoLicenseIssuanceSlots`,
`partnerEvalLicenses` among licence-shaped tables). The CLI-side wrapper
`issueRepoLicense` already sends every field needed
(`packages/cli/src/services/account/license.ts:398-441`). Nothing to add.

### 3.3 Prerequisite: the CLI entry point, reported broken and apparently already fixed

The `roundtrip` agent reports that `rdc backup restore` cannot reach the restore
path at all, independently of licensing, and had to drive `renet backup restore`
directly over SSH:

```
$ ./rdc.sh --config roundtrip backup restore rtprobe@w1 --as rtcli --at <snap> -m w2 -y
EXIT=1  "backup_restore needs the target repository's GUID, and
         "d2fe7d2c-..." does not resolve to one"
```

diagnosed as `BackupRestoreCommand.Build` feeding an already-resolved GUID back
into the name-keyed `p.GetRepositoryGUID`.

**That report is stale, and I am flagging it rather than designing around it.**
The working tree now contains `ResolveRepositoryGUID`
(`private/renet/pkg/functions/commands/registry.go:35-43`), which tries the
name-keyed map first and then accepts a bare GUID:

```go
func ResolveRepositoryGUID(p *provider.VaultProvider, repo string) string {
	if guid := p.GetRepositoryGUID(repo); guid != "" {
		return guid
	}
	if repoGUIDPattern.MatchString(repo) {
		return repo
	}
	return ""
}
```

`backup.go:735` calls it, as do the four siblings at `:425`, `:569`, `:645`,
`:681`. The helper is **uncommitted and post-dates the report**
(`git show HEAD:pkg/functions/commands/registry.go | grep -c ResolveRepositoryGUID`
is 0; both files show as modified), so somebody fixed this between the round
trip hitting it and now.

**Marked as a hypothesis, not a conclusion: I have read the fix, I have not run
it.** The round trip should re-run the CLI entry point and confirm, because this
plan's entire pre-flight hangs off `runChunkRestore` and is worthless if the
command cannot be invoked. Do not treat "the code looks right" as the answer;
that is precisely the mistake this program keeps paying for.

One thing in the round trip's diagnosis is worth keeping regardless of whether
the entry point now works: it observed that the four sibling verbs have a
whole-datastore fallback where restore does not, so a failed resolution there
"silently widens to the whole datastore" instead of failing. `backup.go:733`
documents the asymmetry as deliberate for restore. Whether the siblings' widening
is deliberate too, or is a latent bug where a mistyped repo name silently
operates on everything, is **outside this plan's scope and worth someone
checking**. I did not verify it and am not asserting it.

---

## 4. The bare-metal case

### 4.1 What the CLI already requires, before licensing enters the picture

`rdc backup restore` cannot run on an unregistered machine today, and this is
**not** a licensing constraint:

- The **target machine must be in the active config**: `resolveRestoreMachine`
  (`backup.ts:132-153`) calls `assertMachineExists`, and the executor calls
  `configService.getLocalMachine` (`local-executor.ts:1943`), which throws
  `Machine "<name>" not found` (`packages/cli/src/services/config/config-resources.ts:130-138`).
- The **source repo record must be in the active config**:
  `resolveRestoreTarget` (`backup.ts:280-283`) throws
  `commands.backup.restore.sourceUnknown` when `configService.getRepository(ref.name)`
  misses. The lineage passed to the chunk store comes from that record
  (`backup.ts:220`), and so does the repo credential the restored image needs.

So the honest answer is: **yes, the operator must register the machine first, and
must have a config that still contains the source repo record.**

### 4.2 Is that acceptable

**For the machine: yes, and it needs no extra step.** `rdc machine add <name> --ip --user`
(`packages/cli/src/commands/machine/register.ts:113-151`) is a purely local config
write plus a best-effort `ssh-keyscan`; its only precondition is an active config
(`config-resources.ts:60-64`). It contacts no server, consumes no activation, and
costs nothing. It is already the first thing an operator does with a replacement
box.

**For the config: yes, but only because it is already load-bearing for a reason
bigger than licensing.** Without the config record the restore cannot know the
lineage *or* the repo credential (the LUKS passphrase). A restored image with no
credential unlocks for nobody: the restore would succeed and the repo would be
inert. The product already recognises this and already nudges:
`warnIfConfigStorageUnenrolled()` at `backup.ts:207`, whose comment names the case
("a restore into a config with no config-storage enrollment cannot recover the repo
credential (the LUKS passphrase) on a fresh host, warn, never block").

**Therefore: no separate step in this plan.** Config-storage enrollment is the
designed recovery route for the config itself, and licensing does not change the
calculus in either direction. Stated plainly so nobody mistakes this plan for more
than it is: **this plan makes DR work for an operator who has their config and a
registered machine. It does nothing for an operator who has lost the config, and
no licensing change could, because the passphrase is gone too.**

**Size, since the machine cannot supply it.** `resolveRequestedSizeGb`
(`local-executor.ts:471-499`) `stat`s the repo image, which by definition does not
exist during a restore, and would fall back to the 1 GB floor. Use the manifest
index instead: `listManifests` returns `totalBytes`
(`private/account/src/services/backup-storage.service.ts:1077-1087`), and
`totalBytes` is written from the snapshot's `m.ImageBytes`
(`private/renet/pkg/chunkstore/session.go:461`), i.e. the full logical image size.
`resolveSnapshotAt` (`backup.ts:347-379`) already fetches that index for the
`--at`-is-a-time case. Two implementation notes: it currently short-circuits when
`--at` is already a snapshot id (`backup.ts:348`), so the size lookup needs the
index fetched unconditionally or the chosen manifest threaded down; and the value
must reach the executor, most simply as an explicit param on the
`getExecutor().execute()` call at `backup.ts:401-407` that the new context
resolver reads. Round up, and apply the same `MIN_REQUESTED_SIZE_GB` floor
(`local-executor.ts:499`).

---

## 5. Tests that fire on a planted defect

### 5.1 Why the existing suite was green

Stated first because it is the actual lesson. **Every command-level restore test
mocks the executor wholesale**: `packages/cli/src/commands/__tests__/backup-restore-datastore.test.ts:45-47`
does `getExecutor: () => ({ execute: mockExecute })`, and
`backup-restore-at.test.ts` never invokes the executor at all. Nothing in
`local-executor.ts` runs in any restore test. **A test written at command level
cannot catch this class of defect**, no matter how thorough. The new tests must
drive `localExecutorService.execute()` directly, as
`packages/cli/src/services/__tests__/local-executor*.test.ts` do.

Second reason: renet's own failure is a plain error string, so no CLI recovery
path and no exit-code assertion could have noticed.

### 5.2 The tests

Home: a new `packages/cli/src/services/__tests__/local-executor-restore-license.test.ts`,
copying the established mocking pattern from `local-executor.test.ts:33` and
`:71-75` (hoisted `mockIssueRepoLicense: vi.fn()`, partial `vi.mock('../account/license.js', ...)`
that keeps `isDatastoreScopedId` real), plus the two environment preconditions
those tests need: `delete process.env.REDIACC_SKIP_MACHINE_ACTIVATION`
(`local-executor-license-size.test.ts:198`) and
`mockGetSubscriptionTokenState.mockReturnValue({ kind: 'ready', ... })` (`:216-220`).

| # | Assertion | Planted defect it catches | Silent on a clean tree |
|---|---|---|---|
| T1 | `execute({ functionName: 'backup_restore', ... })` then `expect(mockIssueRepoLicense).toHaveBeenCalledTimes(1)` | The seam call at `local-executor.ts:1897` is deleted or its predicate is inverted. **This is the required test from the brief.** | Yes |
| T2 | `expect(mockIssueRepoLicense.mock.calls[0][2]).toMatchObject({ repositoryGuid: SOURCE_GUID, grandGuid: SOURCE_LINEAGE, kind: 'grand', datastoreId: 'ds-...' })` (pattern: `local-executor.test.ts:676`) | A licence issued for the **wrong guid**: the target *name*, a fresh guid, or a carrier. Candidate (b) shipped by accident fails here and passes T1. | Yes |
| T3 | `requestedSizeGb` equals the manifest's `totalBytes` rounded up, not the 1 GB floor | The size falls back to the stat probe or the floor, capping the restored repo. | Yes |
| T4 | Negative control: `execute({ functionName: 'backup_list' })` and `{ functionName: 'backup_pull' }` then `expect(mockIssueRepoLicense).not.toHaveBeenCalled()` (pattern: `local-executor.test.ts:281`) | A predicate widened to "any backup verb", which would make T1 pass for the wrong reason and would issue licences on every read. | Yes |
| T5 | Skip probe: with a usable blob already reported by the mocked remote scan, `expect(mockIssueRepoLicense).not.toHaveBeenCalled()` | The skip-if-present logic (6.3) is dropped, so every retry burns an issuance slot. | Yes |

T1 without T2 and T4 is not enough, and the brief is right to say so: T1 alone is
satisfied by any implementation that calls the mint with anything at all.

**Instrument proof (per the standing rule that a sweep needs a control).** Before
declaring these tests done, plant each defect and confirm the corresponding row
goes red. Specifically for T1, comment out the new arm at `local-executor.ts:1897`
and confirm the run fails; if it passes, the test is not wired to the code path it
claims to guard, which is exactly how this gap survived a green suite the first
time.

### 5.3 The test that would have found the gap in the first place

Unit tests would not have. This gap was found by driving the product on a fleet,
and the coverage hole is at the drill level:

- `scripts/drills/backup.sh` leg d, `leg_d_point_in_time_restore` (`backup.sh:1058`),
  is **host-only**: it restores through a read grant from the host and says so
  (`backup.sh:74-75`, `:376-378`, "no MACHINE runs the restore in this host-only
  drill"). No machine ever executes `renet backup restore`, so no machine's
  licence store is ever consulted.
- `.ci/scripts/private/license-e2e.sh` `run_battery` (`:394-424`) drives
  `repository create` and `repository up` (`:399-400`) and covers missing/valid/
  delegated/forged/tier-split, but has no restore scenario.

Recommended, in priority order:

1. **Extend `scripts/drills/backup.sh` leg d with a machine-side restore onto a
   machine holding no licence.** This is the only test in the repo that would have
   failed before this fix and passes after it. It is also the expensive one; it
   needs a fleet.
2. **Add a `license-e2e.sh` scenario** asserting that `backup restore` on an empty
   licence store fails with the `resolveRestoreLicense` message (codifying the
   renet-side limitation) and that it is **not** rejected by a tier gate
   (guarding the `TierNone` decision at `tiermap.go:61-68`, which a future
   refactor could quietly reverse).

---

## 6. Blast radius

Checked against the licensing paths rather than assumed, because the brief is
right that a wrong answer here burns operator quota on every restore.

**Direct answer to the team lead's question, before the detail.** Issuing a
licence at restore time does **not** meaningfully consume against the
column-authoritative activation cap: that cap counts **machines**, an existing
machine reuses its row, and a fresh machine's row self-releases on a 5-hour
float. **But there is a second meter, and this one does get burned: a monthly
repo-licence issuance slot, consumed on every single call with no dedupe by repo
or machine, failed retries included.** So the naive implementation is a defect of
exactly the kind described: a DR procedure that silently spends quota each time
it is exercised. Section 6.3 is the mitigation, and it is part of the fix rather
than a follow-up.

### 6.1 Machine activation cap: one slot, self-releasing, unavoidable

The cap is **per machine**, and it is column-authoritative: `const maxMachines = sub.maxActivations;`
with the comment "The cap comes from `sub.maxActivations` (the DB column), never
from the plan constant" (`private/account/src/services/subscription.service.ts:1434-1446`),
enforced at `:1484`. There is **no per-repo cap**.

- Restoring onto a machine **already in use**: `claimMachineSlotHard` finds the
  existing activation row and only bumps `lastSeenAt`
  (`subscription.service.ts:1462-1482`, `return { isNew: false, ... }`).
  **Zero new consumption.**
- Restoring onto a **fresh DR machine**: one activation slot, released by the
  5-hour float (`MACHINE_AUTO_RELEASE_MS` at
  `packages/shared/src/subscription/constants.ts:72`, applied by
  `pruneStaleActivations`, `subscription.service.ts:1602-1613`, called from
  `claimMachineSlotHard:1448`).

This cost is **not introduced by this plan**: any command against a new machine
claims a slot. Nothing to mitigate.

### 6.2 Monthly issuance slot: this is the real cost, and it is per call

`claimRepoLicenseIssuanceSlot` is invoked **unconditionally** on the single-issue
path (`subscription.service.ts:795`, implementation `:1674-1722`, limit
`sub.maxRepoLicenseIssuancesPerMonth`). The table's only unique index is
`(subscription_id, month_key, slot_number)` (`src/db/schema.ts:483-487`);
`repositoryGuid` and `machineId` are recorded but participate in **no** dedupe.
Only the *batch* path can skip, via its `status: 'unchanged'` shortcut
(`subscription.service.ts:939-950`).

**So a naive implementation burns one monthly issuance per restore attempt,
including every failed retry.** A DR session that fails three times on an unrelated
error costs four. That is the one thing in this plan that can genuinely surprise an
operator.

### 6.3 The mitigation, and it is part of the fix, not a follow-up

Probe before issuing: run the same remote scan the batch refresh already uses,
`scanRemoteRepoLicenses` via `licenseScanCommand('license-scan', renetPath, datastore)`
(`packages/cli/src/services/account/license.ts:645-651`), and **skip issuance
entirely** when the target datastore already holds a blob for the source guid whose
window is still valid. This makes a retried restore cost zero extra issuances and
makes a restore onto an already-licensed machine a no-op. T5 in section 5.2 is the
test that keeps it.

Note it must probe for the **source guid in the target datastore scope**, not "any
licence on the machine". Probing for "any" would reproduce the carrier-repo bug
from the other direction: it would skip issuance on a machine that holds an
unrelated licence, the restore would then pass via the any-repo fallback, and
`--up` would fail.

### 6.4 Nothing is re-metered

Storage usage is metered at commit on the backup path
(`backup-storage.service.ts:936-944`, `logicalBytes: input.totalBytes`). A restore
mints a **restore-intent** session (`backup_restore.go:210-221`,
`Intent: chunkstore.SessionIntentRestore`), and `mintReadGrant` writes no usage
rows. Issuing a licence writes an issuance-ledger row and a slot row and nothing
billable beyond the slot in 6.2.

### 6.5 Permanent guid binding: not triggered here, but worth knowing

The first issuance for a guid binds it to the subscription forever; another
subscription is then refused with "This repository (GUID) was originally licensed
under a different subscription. Contact support to transfer."
(`subscription.service.ts:1739-1745`). For a restore the guid is already this
subscription's own (it was issued when the source repo was created), so this plan
creates no new binding. It does mean a restore driven from a config containing a
foreign guid would permanently squat it. See finding F3.

---

## 7. Findings surfaced on the way, which are not this plan's job to fix

Recorded with evidence so they are not rediscovered. None of these blocks the plan.

- **F1. `mintReadGrant` has no test for the property this fix depends on.**
  `private/account/tests/integration/backup-read-grant.test.ts` covers
  cross-*subscription* refusal (`:602`) and cross-lineage-within-a-chain (`:573`),
  but has **no** case for "a licence issued for repo A mints a read grant over
  lineage B in the same subscription". That is the exact behaviour section 2.1
  relies on, and it is currently unpinned: a future tightening of `mintReadGrant`
  would break restore silently. **This one is worth adding while the fix is being
  written**, because it converts an undocumented invariant into a guarded one.
- **F2. `/licenses/activate-repo` signs for arbitrary UUIDs.** There is no
  repository table and no existence check; `checkRepoGuidOwnership` only refuses a
  guid already bound elsewhere (`subscription.service.ts:1739`). One call can
  permanently squat any unclaimed GUID against every other tenant. Pre-existing,
  unrelated to restore, and the reason candidate (a) needs no server change.
- **F3. Team scoping evaporates at the backup session.** Activations carry
  `teamId`; `backup_sessions` (`src/db/schema.ts:1540-1558`) does not. A
  team-scoped token's licence yields a subscription-wide storage session.
  Pre-existing.
- **F4. `resolveRestoreLicense`'s any-repo fallback is load-bearing today and
  becomes vestigial after this fix.** Once the CLI installs the right licence, the
  fallback only ever fires for a hand-run `renet backup restore`. Leaving it is
  fine (it is the escape hatch for exactly that), but its comment at
  `backup_restore.go:355-358` should be updated to say the CLI-side
  issue-before-restore now exists, or the next reader will re-derive this whole
  plan.

---

## 8. Is this a product decision rather than an implementation

**No. It is an implementation, and the decision it rests on is now measured.**
The one genuinely forked question (does a licence minted for one grand authorise
reading another lineage) is answered twice over: by the code in section 2.1, and
by a completed cross-grand restore of 31 of 31 chunks in section 2.1a. The
boundary is the subscription, deliberately, with comments on both sides saying so.

The choice between candidates (a) and (b) is likewise settled rather than
preferential, by `--up` and the guid-specific operate-tier check, and that
particular question is **not** affected by the measurement (section 2.2).

There is one thing that **is** the operator's call, and it is small: **whether a
restore should be allowed to consume a monthly issuance slot at all.** Section 6.3
reduces it to one per genuinely new restore, which is the same cost as creating
the repo would have been. If the operator's view is that disaster recovery must
never be gated by a monthly quota, that is a different and larger change: a
quota-exempt issuance class, which is candidate (c) territory. My recommendation
is to proceed with (a) plus the 6.3 probe and not build the exemption, on the
grounds that one issuance per DR event is proportionate and the failure mode
(quota exhausted during a disaster) is better addressed by the cap being
generous than by a special case in the signing path. **Flagging it rather than
deciding it silently.**

---

## 9. Implementation checklist

0. **Prerequisite:** re-run `rdc backup restore` end to end and confirm the entry
   point works (section 3.3). Everything below hangs off `runChunkRestore` and is
   worthless if the command cannot be invoked. Do not accept a code reading here.
1. `renet-license-contract.ts`: add `isRestoreLicenseFunction`, beside
   `isRepoProvisioningFunction` (`:141`).
2. `local-executor.ts`: add `resolveRestoreLicenseContext` (near `:333`) and
   `ensureRepoLicenseForRestore` (near `:1302`); reuse
   `resolveProvisioningDatastoreId` (`:286`) and `issueOrExplainSlotLimit` (`:1358`)
   unchanged.
3. `local-executor.ts:1897`: add the restore arm.
4. `ensureRepoLicenseForRestore`: skip-if-present probe via
   `scanRemoteRepoLicenses` (`account/license.ts:645`), scoped to source guid +
   target datastore.
5. `backup.ts`: thread the manifest's `totalBytes` down to the executor call
   (`:401-407`); fetch the manifest index unconditionally in `resolveSnapshotAt`
   or return the chosen manifest rather than just its id.
6. `backup_restore.go:355-358`: update the comment (F4).
7. New `local-executor-restore-license.test.ts` with T1 to T5; plant each defect
   and confirm the matching row goes red before calling it done.
8. Add the F1 read-grant test in `private/account/tests/integration/backup-read-grant.test.ts`.
9. Extend `scripts/drills/backup.sh` leg d with a machine-side restore onto an
   unlicensed machine; add the `license-e2e.sh` scenario.
10. Regenerate the shared renet contract so `backup_restore` carries its tier
    (section 0); this is a landing requirement of the backup-storage program, and
    `.ci/scripts/quality/check-renet-tier-map.sh` enforces it.
