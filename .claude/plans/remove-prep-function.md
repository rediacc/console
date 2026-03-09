# Remove prep() Function from Rediaccfile Lifecycle

## Context

The `prep()` function in Rediaccfiles was designed to pull Docker images before `up()`. This is now redundant and harmful:

1. **Redundant**: `up()` functions already use `--pull always` or `renet compose -- up -d` which pulls on start
2. **Harmful during forks**: Docker daemon data (images, layers) lives inside the LUKS volume. When forking/pushing a repo, all Docker data transfers with it. `prep()` re-pulls images unnecessarily, wasting disk space and bandwidth
3. **No backward compatibility needed**: Clean removal, per user decision

## Hostinger (DONE)

All 9 repos on hostinger already had `prep()` removed. Rediaccfiles chowned to `rediacc:rediacc` with `644` permissions.

## File Changes

### 1. Renet — `private/renet/pkg/orchestration/rediaccfile.go`

**Rename `ExecutePrepUp()` → `ExecuteUp()`** and remove prep phase entirely:

```go
// ExecuteUp executes the up() function from Rediaccfiles.
// - Root up() is critical (failure returns error immediately)
// - Subdir up() continues on failure (errors collected)
func (e *RediaccfileExecutor) ExecuteUp(files []RediaccfileInfo) error {
    if len(files) == 0 {
        e.log.Info(i18n.T("orchestration.rediaccfile_no_files"))
        return nil
    }

    e.log.Info(i18n.Tf("orchestration.rediaccfile_found_count", len(files)))
    for _, f := range files {
        if f.Name == rootRediaccfile {
            e.log.Info(i18n.T("orchestration.rediaccfile_root"))
        } else {
            e.log.Info(i18n.Tf("orchestration.rediaccfile_subdir", f.Name))
        }
    }

    // Execute up (root critical, continue on subdir failures)
    e.log.Info("")
    e.log.Info(i18n.T("orchestration.rediaccfile_phase_up"))
    var upFailures []string
    for i, file := range files {
        displayName := file.Name
        e.progress(fmt.Sprintf("Starting %s services... - %d%%", displayName, 10+(85*i/len(files))))

        err := e.ExecuteFunction(file, "up")
        if err != nil {
            e.log.Error(i18n.Tf("orchestration.rediaccfile_up_failed", displayName))
            upFailures = append(upFailures, displayName)
            if i == 0 && file.Name == rootRediaccfile {
                return fmt.Errorf("%s up failed: %w", rootRediaccfile, err)
            }
        } else {
            e.log.Info(i18n.Tf("orchestration.rediaccfile_up_completed", displayName))
        }
    }

    e.log.Info("")
    if len(upFailures) == 0 {
        e.log.Info(i18n.T("orchestration.rediaccfile_up_success"))
    } else {
        e.log.Warn(i18n.Tf("orchestration.rediaccfile_up_with_errors", len(upFailures), strings.Join(upFailures, ", ")))
    }

    return nil
}
```

Delete the old `ExecutePrepUp()` function entirely (lines 215-281).

### 2. Renet — `private/renet/pkg/orchestration/up_down_workflows.go`

- **Remove `PrepOnly bool` field** from `UpOptions` struct (line 30)
- **Replace the PrepOnly/ExecutePrepUp block** (lines 204-227) with a single call:

```go
    if err := executor.ExecuteUp(files); err != nil {
        return err
    }
```

- **Update `UpServices()` docstring** (lines 96-102): Remove "Execute prep()" from the steps list
- Remove import/reference to prep-related i18n keys

### 3. Renet — `private/renet/cmd/renet/repository_up.go`

- **Remove `--prep-only` flag** (line 25): Delete `repositoryUpCmd.Flags().Bool("prep-only", ...)`
- **Remove `prepOnly` parsing** (line 44): Delete `prepOnly, _ := cmd.Flags().GetBool("prep-only")`
- **Remove `PrepOnly: prepOnly`** from opts (line 86)
- **Remove prep-only log message** (lines 100-102): Delete the `if prepOnly { ... }` block

### 4. Renet — `private/renet/pkg/orchestration/rediaccfile_test.go`

- Update test Rediaccfile content that includes `prep()` function (lines 154-156, 240-241)
- Remove `prep()` from test fixture strings — tests should only define `up()` and `down()`

### 5. Renet — `private/renet/pkg/i18n/locales/*.go` (9 files)

Remove these i18n keys from ALL locale files:

```
"orchestration.rediaccfile_phase_prep"
"orchestration.rediaccfile_prep_failed"
"orchestration.rediaccfile_prep_completed"
"orchestration.up_phase_prep"
"orchestration.up_prep_failed"
"orchestration.up_prep_completed"
"orchestration.up_prep_only_completed"
"rediaccfile.execute_prep_up_phase_prep"
```

Also rename any `execute_prep_up_*` keys that remain (for the up phase) if they reference "prep_up":
- `rediaccfile.execute_prep_up_phase_up` → `rediaccfile.execute_up_phase_up` (or just delete if covered by `orchestration.rediaccfile_phase_up`)
- `rediaccfile.execute_prep_up_rediaccfile_root` → `rediaccfile.execute_up_rediaccfile_root` (or delete if redundant)

Files: `en.go`, `ar.go`, `de.go`, `es.go`, `fr.go`, `ja.go`, `ru.go`, `tr.go`, `zh.go`

### 6. Renet — `private/renet/pkg/i18n/hash.go`

Remove prep-related keys from the `technicalKeys` list:

```go
// DELETE these entries:
"orchestration.rediaccfile_phase_prep",
"orchestration.up_phase_prep",
"rediaccfile.execute_prep_up_phase_prep",
"rediaccfile.execute_prep_up_phase_up",
"rediaccfile.execute_prep_up_rediaccfile_root",
```

### 7. Renet — `private/renet/cmd/renet/main.go`

Remove `msg.repository.up.phase_prep_only` i18n key reference if present.

### 8. CLI — `packages/cli/src/commands/repo.ts`

- **Remove `--prep-only` option** (line 291): Delete `.option('--prep-only', ...)`
- **Remove `prepOnly` from type** (line 303): Delete `prepOnly?: boolean;`
- **Remove prep-only param** (line 314): Delete `if (options.prepOnly) params.option = 'prep-only';`

### 9. CLI — `packages/cli/src/i18n/locales/*/cli.json` (9 files)

- Remove `"prepOnlyOption"` key from `commands.repo.up` object
- Update `commands.repo.up.description` to remove "prep/" reference (currently says "run Rediaccfile prep/up")

Files: `en/cli.json`, `ar/cli.json`, `de/cli.json`, `es/cli.json`, `fr/cli.json`, `ja/cli.json`, `ru/cli.json`, `tr/cli.json`, `zh/cli.json`

### 10. CLI — `packages/cli/src/i18n/locales/.translation-hashes.json`

- Remove `"commands.repo.up.prepOnlyOption"` entry

### 11. Template Rediaccfiles — `packages/json/templates/**/Rediaccfile` (27 files)

Remove `prep()` from all template Rediaccfiles. For templates with useful non-pull logic (mkdir, chmod, etc.), move that logic to the beginning of `up()`.

**Templates with only pulls** (just delete prep entirely):
- `caching/memcached`, `caching/redis`
- `platforms/nginx`

**Templates with pulls + mkdir/chmod** (move mkdir/chmod to beginning of up):
- `databases/postgresql`, `databases/mariadb`, `databases/mysql`, `databases/mssql`
- `databases/percona`, `databases/rethinkdb`, `databases/crate`
- `databases/cassandra`, `databases/couchdb`, `databases/influxdb`
- `databases/arangodb`, `databases/neo4j`, `databases/solr`
- `analytics/plausible`, `automation/n8n`
- `messaging/docker-mailserver`, `messaging/listmonk`, `messaging/rabbitmq`
- `monitoring/heartbeat`, `monitoring/prometheus-grafana`
- `platforms/gitlab`, `platforms/nextcloud-aio`, `platforms/wordpress`
- `search/elasticsearch`

**Special case — `networking/cloud-switch`** (move all prep content to up):
- Has `sysctl`, `docker build`, and `tunnel.sh up` — all belong in `up()`

### 12. Bridge test fixture — `packages/bridge-tests/fixtures/bridge/Rediaccfile.nginx`

- Remove `prep()` function (lines 9-13)
- Also remove the `_compose()` wrapper and `--network-id` usage (uses old pattern)
- Simplify to use `renet compose --` directly

### 13. Renet — Rediaccfile validation (optional cleanup)

In `rediaccfile.go` `ValidateRediaccfile()`: The validation currently checks for `docker compose` and `--network-id` patterns. No prep-specific validation exists, so no changes needed here.

## Verification

```bash
# 1. Build renet
cd private/renet && ./build.sh dev

# 2. Run Go tests (orchestration + commands)
cd private/renet && go test ./pkg/orchestration/... ./cmd/renet/...

# 3. Type check CLI
npx tsc --noEmit --project packages/cli/tsconfig.json

# 4. Verify template Rediaccfiles have no prep()
grep -r "prep()" packages/json/templates/

# 5. Verify no orphan i18n keys referencing prep
grep -r "phase_prep\|prep_only\|prep_failed\|prep_completed\|PrepOnly\|prep-only" private/renet/pkg/ private/renet/cmd/ packages/cli/src/

# 6. Deploy a test repo on hostinger to confirm up() works without prep
./rdc.sh repo up mail -m hostinger
./rdc.sh machine containers hostinger
```

## Summary

| Category | Files | Changes |
|----------|-------|---------|
| Go orchestration | 3 | Remove prep phase from ExecutePrepUp→ExecuteUp, UpServices, repository_up.go |
| Go i18n | 10 | Remove ~8 prep keys from 9 locale files + hash.go |
| Go tests | 1 | Update test fixtures to remove prep() |
| CLI TypeScript | 1 | Remove --prep-only option from repo.ts |
| CLI i18n | 10 | Remove prepOnlyOption from 9 locale files + hashes |
| Templates | 27 | Remove prep() from all Rediaccfile templates |
| Bridge tests | 1 | Remove prep() from test fixture |
| **Total** | **53 files** | |
