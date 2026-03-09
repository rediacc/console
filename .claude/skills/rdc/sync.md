# rdc repo sync — File Transfer

Transfer files between local machine and remote repositories via rsync over SSH.

## Commands

### Upload to repository
```
rdc repo sync upload -m <machine> -r <repository> [--local <path>] [--remote <subdir>] [options]
```
Uploads files from local directory to the repository mount on the remote machine.
- `--local <path>`: Local directory (default: current directory). Trailing slash is auto-added.
- `--remote <path>`: Subdirectory within the repo to upload into.
- `--mirror`: Delete remote files not present locally.
- `--verify`: Use checksums instead of timestamps for change detection.
- `--confirm`: Preview changes before syncing (interactive).
- `--exclude <patterns...>`: Glob patterns to exclude.
- `--dry-run`: Preview without transferring.

### Download from repository
```
rdc repo sync download -m <machine> -r <repository> [--local <path>] [--remote <subdir>] [options]
```
Same options as upload, reversed direction.

### Check status
```
rdc repo sync status -m <machine> -r <repository> [--local <path>]
```
Dry-run comparison showing what would change.

## Behavior notes

- Uses rsync with archive mode (`-a`): preserves timestamps, permissions, symlinks.
- Files are transferred with `--inplace` and delta compression — only changed bytes are sent over the wire, not entire files. This makes re-syncing large files very fast.
- Runs remote rsync as sudo for full permission handling across container UIDs.
- Change detection is based on file size and modification time by default. Use `--verify` for checksum-based detection when timestamps are unreliable.

## Delta transfer (rsync efficiency)

Rsync uses a rolling-checksum algorithm to transfer only the changed blocks of a file. This means:
- **First sync**: Full file transfer (no remote data to diff against).
- **Subsequent syncs**: Only changed bytes are sent. A 100MB file with 1KB of changes transfers ~1KB.
- **No change**: 0 files transferred — rsync skips files matching on size + mtime.
- Use `--dry-run` to preview what would change before syncing.

### Important: timestamp vs checksum detection

Default detection uses file size + modification time. **Same-size edits are consistently missed** — even config value swaps (e.g., `5000` → `3000`) that don't change file size are invisible to default detection. This applies to files of all sizes (tested with 2.5KB and 157KB files).

- **Size changes are always detected** without `--verify`.
- **Same-size content changes require `--verify`** (checksum mode) to be detected.
- **Rule of thumb**: Use `--verify` whenever editing existing files, changing config values, or reverting changes. The checksum overhead is negligible for small-to-medium file sets.
- **Safest cleanup**: Combine `--verify` with `--mirror` to catch both modified and deleted files in one operation.

### Delta efficiency and CLI output

- The CLI output shows file count and total file size — **not** actual bytes transferred over the wire. Both initial and delta syncs of the same file show the same "Total size" value.
- Rsync's block-level delta transfer happens at the wire level but is not visible in CLI output. To confirm delta efficiency, you would need rsync's `--stats` flag (not currently exposed by the CLI).
- For practical purposes: unchanged files show "0 files transferred", changed files show the file's total size regardless of how many bytes actually went over the wire.

### Seeing delta in action

After making a small change to a file that's already synced:
```bash
# Preview what would change
rdc repo sync upload -m <machine> -r <repo> --local <path>/ --dry-run

# Upload only the delta
rdc repo sync upload -m <machine> -r <repo> --local <path>/
```
Compare "files transferred" and "Total size" across syncs to verify delta behavior.

### Cross-repo file sync

To copy files between repos on different machines (e.g., syncing app code updates):
```bash
# Download from source repo to local temp dir
rdc repo sync download -m <source> -r <repo> --local /tmp/sync-temp/

# Upload to target repo
rdc repo sync upload -m <target> -r <repo> --local /tmp/sync-temp/
```

## Examples

```bash
# Upload app files to a repository
rdc repo sync upload -m server-1 -r my-app --local ./src/

# Download database dumps
rdc repo sync download -m server-1 -r my-app --local ./backups/ --remote data/dumps

# Mirror mode (delete remote files not in local)
rdc repo sync upload -m server-1 -r my-app --local ./deploy/ --mirror

# Preview before syncing
rdc repo sync upload -m server-1 -r my-app --local ./config/ --confirm
```
