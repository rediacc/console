---
title: "rdc repo diff"
description: "Show a git-style, file-level diff between two copy-on-write forked repositories by comparing their encrypted images at the block level, without decryption."
category: Reference
subcategory: advanced
order: 40
language: en
---

# rdc repo diff

`rdc repo diff` reports which files changed between two related repositories: a fork and its parent, or any two repositories that share a copy-on-write ancestor. Pass `--name <fork>` to diff a fork against the parent that local config records for it, or add `--base <repo>` to diff against an arbitrary related repository, where `--base` is the base (old) side and `--name` is the target (new) side. The command is read-only and never decrypts the images. It compares them at the block level on the remote machine, so cost tracks the number of changed blocks, not the size of the repository: a 1 GB repo and a 100 GB repo with the same edits take the same time. If the whole repository changed, block count scales with size and so does cost.

## When to use it

So: reach for `repo diff` before you promote a fork. An AI agent ran loose in a forked copy of production and you want to see exactly which files it touched before merging the change back: `repo diff --name <fork> -m <machine>` gives you that file list in seconds. Seconds. After a disaster-recovery restore, diff the restored fork against the snapshot it was supposed to reproduce to confirm the expected file set came back and nothing else drifted. For a long-lived fork that has run alongside its parent for weeks, the diff shows accumulated divergence (config edits, log accretion, schema migrations) without mounting and walking both trees by hand.

Do not use it across unrelated repositories. The two sides must share a copy-on-write ancestor, because the comparison works on the shared block history. It is also not a binary diff tool: `--content` produces line-level output only for text files, and binaries report `Binary files differ`.

## Command reference

### Synopsis

```bash
rdc repo diff --name <fork> -m <machine>            # diff a fork against its parent
rdc repo diff --name <fork> --base <repo> -m <machine>   # diff against an arbitrary related repo
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--name <name>` | Repository to inspect (the target, new side). Required. | required |
| `--base <name>` | Repository to diff against (the base, old side). Defaults to the parent of `--name`, resolved from local config. | parent of `--name` |
| (no format flag) | Name-status output: a colored `A`/`M`/`D`/`R` letter per changed file plus a one-line summary. | on |
| `--name-only` | One changed path per line, no status letter. Pipe-friendly. | off |
| `--stat` | Per-file change magnitude (byte and block deltas) with a totals footer. | off |
| `--content <path>` | Unified text diff of a single file. Text only; binaries report `Binary files differ`. | off |
| `--json` | Structured output for agents and scripts. | off |
| `--fast` | Skip the content-hash confirmation step and trust the block filter. Faster, but may over-report files as Modified. | off |
| `-m, --machine <name>` | Target machine. Required. | required |
| `--debug` | Verbose diagnostics on stderr. | off |
| `--skip-router-restart` | Skip the router restart step. | off |

## Examples

### Default name-status against the parent

With only `--name`, the fork is diffed against the parent recorded in local config. Here the fork `test-1gb:fork1` has one modified file:

```bash
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### Diffing against an explicit base

Pass `--base` to diff against an arbitrary related repository. `--base` is the base (old) side, `--name` is the target (new) side:

```bash
$ rdc repo diff --name test-1gb:fork1 --base test-1gb:latest -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### Change magnitude with `--stat`

`--stat` adds the byte and block delta per file and a totals footer:

```bash
$ rdc repo diff --name test-1gb:fork1 --stat -m hostinger
 hello.txt | +8 bytes, 1 block

1 file changed, 4096 bytes touched
```

### Paths only, piped to a tool

`--name-only` prints one path per line with no status letter, ready to feed into another command:

```bash
$ rdc repo diff --name test-1gb:fork1 --name-only -m hostinger | xargs -I{} echo "review: {}"
review: hello.txt
```

### Line-level diff of one file

`--content` produces a unified diff of a single text file:

```bash
$ rdc repo diff --name test-1gb:fork1 --content hello.txt -m hostinger
--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-the original line of text in the parent
+the original line of text in the parent, now edited
```

### Filtering JSON with jq

`--json` emits the structured envelope on stdout, so it pipes cleanly into `jq`:

```bash
$ rdc repo diff --name test-1gb:fork1 --json -m hostinger | jq '.data.entries[] | select(.status=="M")'
{
  "status": "M",
  "path": "/hello.txt",
  "type": "file",
  "old_size": 53,
  "size": 61,
  "bytes_changed": 4096,
  "blocks_changed": 1,
  "inode": 13,
  "content_changed": true,
  "mode_changed": false,
  "uid_changed": false,
  "gid_changed": false
}
```

## Output formats

### Name-status (default)

Each changed file gets a status letter and its path. `A` is added, `M` modified, `D` deleted, `R` renamed (with the old path shown). A summary line follows with the count per category.

### `--name-only`

One path per line, no status letter, no summary. Use it when a downstream command wants a clean file list.

### `--stat`

Each line carries the file's byte delta and block delta. A footer reports the total file count and total bytes touched. This shows where the weight of a change sits, not just which files moved.

### `--content <path>`

A standard unified diff (`---`/`+++` headers, `@@` hunks) for one text file. Binary files report `Binary files differ` and produce no hunks.

### `--json`

The full structured result. Data goes to stdout; progress and diagnostics go to stderr, so the JSON pipes cleanly into `jq` or another parser even while progress is printing.

## JSON schema

The CLI wraps the renet result in the standard envelope (`success`, `command`, `data`, `errors`, `warnings`, `metrics`). The diff result lives in `data` with snake_case fields:

```json
{
  "success": true,
  "command": "repo diff",
  "data": {
    "base": "<base-guid>",
    "target": "<target-guid>",
    "added": 0,
    "modified": 1,
    "deleted": 0,
    "renamed": 0,
    "strategy": "shared",
    "fast": false,
    "degraded": false,
    "block_size": 4096,
    "total_bytes_changed": 4096,
    "entries": [
      {
        "status": "M",
        "path": "/hello.txt",
        "type": "file",
        "old_size": 53,
        "size": 61,
        "bytes_changed": 4096,
        "blocks_changed": 1,
        "inode": 13,
        "content_changed": true,
        "mode_changed": false,
        "uid_changed": false,
        "gid_changed": false
      }
    ]
  }
}
```

Each object in `entries[]` describes one changed path:

| Field | Type | Description |
|-------|------|-------------|
| `status` | `A` \| `M` \| `D` \| `R` | Added, Modified, Deleted, or Renamed. |
| `path` | string | Path on the target side (or base side for a deletion). |
| `old_path` | string | Previous path. Present only on renames. |
| `type` | `file` \| `dir` \| `symlink` \| `other` | Entry kind. |
| `old_size` | number | Size in bytes on the base side. |
| `size` | number | Size in bytes on the target side. |
| `bytes_changed` | number | Bytes that differ, rounded up to whole blocks. |
| `blocks_changed` | number | Number of changed blocks. |
| `inode` | number | Inode number, used for rename detection. |
| `content_changed` | boolean | Whether file content (not just metadata) changed. |
| `mode_changed` | boolean | Whether the file mode changed. `old_mode`/`new_mode` are present when true. |
| `uid_changed` | boolean | Whether the owner changed. `old_uid`/`new_uid` are present when true. |
| `gid_changed` | boolean | Whether the group changed. `old_gid`/`new_gid` are present when true. |
| `old_target` / `new_target` | string | Symlink targets. Present for changed symlinks. |

For the envelope fields and the auto-detection rules that emit JSON in non-TTY environments, see the [JSON Output Reference](/en/docs/ai-agents-json-output).

## How it works

A repository is a LUKS2 image file on a btrfs pool, and a fork is a constant-time reflink of that image. `repo diff` compares the two encrypted images at the block level via FIEMAP, reading filesystem metadata only and never decrypting anything. It shifts the changed ciphertext offsets by the LUKS data offset to get ext4-device offsets, then maps those offsets back to file names through each file's ext4 extent map. A final inode-identity walk of both mounts reconciles the result into Added, Modified, Deleted, and Renamed entries. Because the work is bounded by the count of changed blocks, the diff is independent of repository size, and because it reuses a live mount in place, it never disturbs a running repository. The full mechanism is described in [Git diff for encrypted disk images](/en/blog/git-diff-for-encrypted-disk-images).

## Limitations

- **Related forks only.** Both sides must share a copy-on-write ancestor. There is no meaningful block-level comparison between unrelated repositories.
- **Rename detection is inode-based.** A file is reported as renamed when the same inode appears at a new path. A delete-then-recreate (a new inode) shows as a Deleted plus an Added entry, not a rename.
- **`--content` is text-only.** It produces line-level hunks for text files. Binaries report `Binary files differ`.
- **`--fast` may over-report Modified.** It trusts the block filter and skips the content-hash confirmation, so a file whose blocks moved without changing content can appear as Modified.
- **Extent-walk time scales with fragmentation, not size.** A heavily fragmented filesystem has more extents to map, which lengthens the walk even when the byte volume of changes is small.

## See also

- [rdc repo fork](/en/docs/repositories). Create the copy-on-write fork that this command diffs.
- [rdc repo status](/en/docs/repositories). Current state of a single repository.
- [rdc repo cat](/en/docs/repositories). Read a single file out of a repository.
