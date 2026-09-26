# PLAN: backup list reads the machine it runs on, locally
Status: compacted
First-Seen: 2026-09-17
Owner: 97604f47
Full-Text: f7a5351a9 agent/PLAN-backup-list-executor-fix.md
Full-Text-Blob: 660292bf31cbeb875e0ba036c84015bb12632d5b
Record-Sig: f315cc25

## Why
`rdc backup list --machine m` was broken three ways at once. It resolved `m` as both the executor and the source, so the machine was asked to SSH into itself to read its own disk, which only works on the internal KVM fleet where a shared private key is copied to every VM and fails on every customer machine. It then probed two hardcoded subdirectories, `hot/` and `cold/`, left over
from the retired rclone layout, that nothing writes to any more, while never looking in the flat `repositories/` directory that everything does write to. A `.catch(() => [])` swallowed the resulting errors, and the renderer separately discarded every directory-shaped entry, dropping kube repo images. The operator saw exit code 1, an error line, and an empty table printed underneath
it.

## Outcome
SHIPPED, measured 2026-09-06. The header claims steps 1 to 7 are "scheduled post-push"; steps 1 to 6 landed two days after the plan was last updated, so THE HEADER IS STALE AND THE TREE WINS.

- The renet local arm exists: `case sourceTypeLocal:` at
`private/renet/cmd/renet/backup_list.go:259`, with `listLocal` at :121 and `listLocalScoped` at :176. Its commit is renet 1a572e9, "feat(renet): backup list --source local, so a machine stops SSHing to itself" (2026-08-17), an ancestor of the renet remote's main.
- The contract carries it: `private/renet/pkg/functions/commands/backup.go:218-219`
offers `{"local","machine","storage"}` with `Default: "local"`, regenerated into `packages/shared/src/renet-contract/data/functions.schema.ts:32-35`. Console commit 57088691d, an ancestor of origin/main.
- The CLI stopped inventing paths: `packages/cli/src/commands/backup.ts:52` builds
`{ sourceType: 'local', from: machine }`, and `resolveListExecutor`, `--storage`, `placementExclusive` and the `['hot','cold']` fan-out with its `.catch(() => [])` are all gone. Console commit daa01bf58, "feat(cli): backup list reads the machine's own datastore" (2026-08-18), an ancestor of origin/main.
- Errors now surface: `packages/cli/src/commands/repo-backup-list.ts:140` throws
``backup list failed: ${tail}`` instead of rendering an empty table.

THE PLAN'S OWN EXECUTION RECORD CITES A COMMIT THAT DOES NOT EXIST. It names renet `8ef4f3e` for step 0; `git rev-parse` in the renet submodule does not resolve it. The commit that actually added `cmd/renet/backup_list_local_test.go` is 1a572e9. Do not trust the sha in the full text.

WHAT DID NOT LAND: the plan's Go test 4 (`TestBackupListBuildLocalArm`) does not exist, the CLI vitest tests 5 to 9 do not exist, `backup_list` is still waived at `.ci/policy/.e2e-coverage-allowlist:20`, and step 7's `--datastore` flag was never added to `backup list`. The `Mode` to `Path` column rename was declined in favour of the plan's own fallback: the key stays `mode` and
`packages/cli/src/commands/backup.ts:53` maps `mode: e.path ?? ''`.

## Lessons
- A machine SSHing to itself passes every test run on a fleet where one private key
is copied to every host. The fleet is the reason the defect was invisible, not the reason it was benign: no customer machine ever holds that key.
- `.catch(() => [])` was a symptom, not a decision. The swallow existed only because
the caller guessed two paths that might not exist; once every listed path comes from a `ReadDir`, every error is real and the swallow removes itself.
- A commit sha written into a plan's execution record is not evidence. This one names
a renet commit that does not resolve, while the work it claims is demonstrably present under a different sha.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: step
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:06:10Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: packages/cli/src/commands/backup.ts, packages/cli/src/commands/repo-backup-list.ts, packages/cli/src/services/executor/local-executor.ts, private/renet/pkg/functions/commands/backup.go, private/renet/cmd/renet/backup_list.go, packages/cli/src/services/tofu/provision.ts, packages/cli/src/commands/machine/register.ts, packages/cli/src/services/repo/repo-key-deployment.ts, private/renet/pkg/infra/mesh/mesh.go, private/renet/pkg/infra/ceph/provisioner.go, packages/e2e-tests/tests/migrate/18-dual-group-migrate.test.ts, packages/cli/src/commands/repo-backup.ts, private/renet/cmd/renet/backup_push.go, packages/cli/src/services/backup/backup-schedule-unit-generator.ts, packages/cli/src/utils/local-execution-failures.ts, packages/cli/src/commands/storage.ts, packages/shared/src/renet-contract/data/functions.schema.ts, private/renet/pkg/list/repositories.go, packages/cli/src/commands/__tests__/backup-restore-datastore.test.ts, packages/cli/src/config/command-docs.ts
Gates: check:ci-cli-contract, check:ci-command-planes, check:ci-command-tree, check:ci-i18n-cli-key-usage, check:ci-i18n-command-parity, check:ci-renet-tiers, check:ci-renet-types, check:cli-docs, check:cli-examples, check:test-cli
Why-Source: auto
Read-History: `git show 660292bf31cbeb875e0ba036c84015bb12632d5b` recovers the text; `git log --find-object=660292bf31cbeb875e0ba036c84015bb12632d5b --all` names the commit

## History
- 2026-09-06T17:06:10Z compacted by 8f55d4f0 from `step` (record-sig f315cc25)
