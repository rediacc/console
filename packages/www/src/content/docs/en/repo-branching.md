---
title: "Git-like branching"
description: "Treat copy-on-write forks as git commits: freeze a fork into an immutable commit, name branches, check commits out into writable forks, walk history, and merge without ever mutating a live repository."
category: Reference
subcategory: advanced
order: 41
language: en
---

# Git-like branching

Rediacc repositories support git-like versioning built on copy-on-write forks. Each immutable fork is a **commit**: a byte-stable, frozen image that refuses to mount. Branches are named refs that point at a commit. `rdc repo checkout` reflink-clones a commit back into a writable working fork, and `rdc repo merge` combines two lines of history without ever mutating a live repository in place.

The model maps onto two stores. The **machine is the object store**: commits are immutable fork images living on the datastore. The **CLI config is the ref store**: branch names, the current `HEAD`, and the reflog live in your local config, not on the machine. This is the same split git uses between `.git/objects` and `.git/refs`.

## When to use it

Reach for branching when a fork has earned a name. An AI agent ran loose in a fork of production, the result looks good, and you want a frozen, named checkpoint you can return to or promote later: `rdc repo commit` freezes it, `rdc repo branch` names it. Before a risky migration, commit the working fork so you have an exact rollback point that is guaranteed never to change (an immutable commit refuses to mount, so nothing can write into it). To compare two checkpoints, `rdc repo diff` works between any two commits because they share a copy-on-write ancestor. To bring a reviewed line of work back onto a target fork, `rdc repo merge` builds the result in a reflink clone and atomically swaps it in, so a running target is never corrupted mid-merge.

Do not reach for it as a substitute for `rdc repo fork` when you only need a throwaway copy. A plain fork is the right unit for ephemeral, per-test isolation. Commits add value when a state is worth keeping, naming, or shipping.

## How commits and forks relate

A repository is one LUKS image file on a btrfs pool. A fork is a constant-time reflink of that image, so forking a 1 GB repo and a 100 GB repo costs the same. A **commit** is a fork that has been marked immutable: renet refuses to mount it, which keeps its image byte-stable forever. That byte-stability is what makes a commit a reliable rollback point and a deterministic base for cross-machine delta push.

`rdc repo commit` records the commit message, author, timestamp, and parent commit **inside the volume** (so the metadata travels with the image on push) and also mirrors it out-of-volume (so `rdc repo log` can walk history without unlocking anything). The working fork you committed continues unchanged, exactly as git leaves your working tree intact after a commit.

## Commands

### rdc repo commit

Freeze a mounted working fork into a new immutable commit.

```bash
rdc repo commit --name <fork> --message "<message>" -m <machine>
```

| Option | Description | Default |
|--------|-------------|---------|
| `--name <name>` | Working fork to commit. Must be mounted. Required. | required |
| `--message <msg>` | Commit message. Required. | required |
| `--author <author>` | Commit author recorded in the commit metadata. | unset |
| `-m, --machine <name>` | Target machine. Required. | required |
| `--debug` | Verbose diagnostics on stderr. | off |

The new commit is registered in local config with `immutable: true`, and the working fork's `headCommit` advances to point at it. Committing an immutable repository is refused: check it out into a writable fork first.

### rdc repo branch

Create a named branch ref pointing at a working fork's current commit.

```bash
rdc repo branch --branch <name> --name <fork>
```

| Option | Description | Default |
|--------|-------------|---------|
| `--branch <branch>` | Name of the new branch. Required. | required |
| `--name <name>` | Working fork whose current commit the branch points at. Required. | required |

This is a config-only operation. No work happens on the machine. The branch ref maps a name to the working fork's `headCommit`, so the fork must have at least one commit first.

### rdc repo checkout

Reflink-clone an immutable commit (or a branch tip) into a fresh writable working fork.

```bash
rdc repo checkout --ref <commit> --tag <newFork> -m <machine>
rdc repo checkout --ref <branchName> --from <fork> --tag <newFork> -m <machine>
```

| Option | Description | Default |
|--------|-------------|---------|
| `--ref <commit\|branch>` | Commit GUID to check out, or a branch name when `--from` is given. Required. | required |
| `--tag <name>` | Name for the new writable working fork. Required. | required |
| `-m, --machine <name>` | Target machine. Required. | required |
| `--from <workingFork>` | Resolve `--ref` as a branch name on this working fork's branch set. | direct commit |
| `--debug` | Verbose diagnostics on stderr. | off |
| `--skip-router-restart` | Skip the router restart step. | off |

Checkout reuses the fork reflink path, so it is near-instant and constant-time regardless of repository size. The new working fork's `headCommit` is set to the checked-out commit.

### rdc repo log

Walk the commit history reachable from a working fork or a commit.

```bash
rdc repo log --name <fork> -m <machine>
```

| Option | Description | Default |
|--------|-------------|---------|
| `--name <name>` | Working fork or commit to start the history walk from. Required. | required |
| `-m, --machine <name>` | Target machine. Required. | required |
| `--json` | Output the commit history as JSON. | off |
| `--debug` | Verbose diagnostics on stderr. | off |

`log` walks the parent chain recorded by `rdc repo commit`, reading the out-of-volume state mirror so no commit is unlocked or mounted. It is read-only.

### rdc repo merge

Merge a source commit or fork into a target working fork, without mutating the live target in place.

```bash
rdc repo merge --name <target> --from <source> -m <machine>
rdc repo merge --name <target> --from <source> --resolve theirs -m <machine>
```

| Option | Description | Default |
|--------|-------------|---------|
| `--name <name>` | Target working fork to merge into. Required. | required |
| `--from <source>` | Source commit or fork to merge from. Required. | required |
| `-m, --machine <name>` | Target machine. Required. | required |
| `--force` | Quiesce a mounted or running target first, then merge. Never mutates a live mount. | off |
| `--resolve <ours\|theirs>` | Per-file three-way merge: fold the source's per-file changes onto the target, keeping (`ours`) or taking (`theirs`) the source's version for files changed on both sides. Omit for whole-image take-theirs. | off |
| `--base <guid>` | Common-ancestor commit for the three-way merge (used with `--resolve`). Defaults to the source commit's parent, or the target's current commit. | auto |
| `--debug` | Verbose diagnostics on stderr. | off |

The result is built in a reflink clone and atomically swapped in behind a crash-safe marker, so an interrupted merge leaves the original target intact. A mounted or running target is refused unless `--force`, which cleanly shuts the target down before swapping.

Without `--resolve`, the merge is a whole-image take-theirs (the target becomes the source). With `--resolve`, it is a per-file three-way merge against the source commit's recorded parent: files changed only on one side are taken from that side, and files changed on both sides are resolved by the flag. Conflicting paths are reported.

### rdc repo gc

Garbage-collect immutable commit objects on a machine that no branch or HEAD reaches.

```bash
rdc repo gc -m <machine>            # dry-run preview (default)
rdc repo gc --apply -m <machine>    # delete the unreachable commits
```

| Option | Description | Default |
|--------|-------------|---------|
| `-m, --machine <name>` | Machine to collect on. Required. | required |
| `--apply` | Actually delete the unreachable commits (otherwise a dry-run preview). | off |
| `--debug` | Verbose diagnostics on stderr. | off |

Reachability is computed from the local config (the ref store): the set of commits reachable by following each branch tip and HEAD down the parent chain. Immutable commits on the machine outside that set are unreachable. A mounted object or a working fork is never collected.

### rdc repo fsck

Validate the config refs against the objects present on a machine.

```bash
rdc repo fsck -m <machine>
```

| Option | Description | Default |
|--------|-------------|---------|
| `-m, --machine <name>` | Machine to check. Required. | required |

Reports dangling refs (a branch tip or HEAD pointing at a GUID with no object on the machine) and orphan commits (an immutable commit on the machine that no ref reaches). It is read-only; reclaim orphans with `rdc repo gc --apply`.

### Immutable forks

`rdc repo fork --immutable` marks the new fork read-only at creation, producing a commit-equivalent base without a separate `commit` step.

```bash
rdc repo fork --parent <name> --tag <tag> --immutable -m <machine>
```

An immutable fork refuses to mount, which keeps its image byte-stable forever. This is useful as a frozen base for cross-machine delta push, where the base must be identical on both ends. To make changes, check it out (or fork it again) into a writable copy.

## Examples

### Commit a working fork

```bash
$ rdc repo commit --name myapp:work --message "schema migration applied" -m server-1
Committed 4f3c2a1b9d8e: schema migration applied
```

### Commit with an explicit author

```bash
$ rdc repo commit --name myapp:work --message "nightly snapshot" --author ci-bot -m server-1
Committed 7a1b2c3d4e5f: nightly snapshot
```

### Name a branch at the current commit

```bash
$ rdc repo branch --branch staging --name myapp:work
Branch "staging" -> 4f3c2a1b9d8e
```

### Check a commit out into a fresh writable fork

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag rollback-test -m server-1
```

### Check a branch tip out by name

With `--from`, the `--ref` value is resolved as a branch name on the given working fork:

```bash
$ rdc repo checkout --ref staging --from myapp:work --tag staging-copy -m server-1
```

### Walk the history

```bash
$ rdc repo log --name myapp:work -m server-1
commit 4f3c2a1b9d8e
  Author: ci-bot  Date: 2026-05-29T10:14:02Z
  schema migration applied
commit 9d8e7a1b2c3d
  Author: ci-bot  Date: 2026-05-28T22:01:55Z
  initial import
```

### History as JSON

`--json` emits the structured walk, newest first:

```bash
$ rdc repo log --name myapp:work --json -m server-1
{
  "success": true,
  "start": "4f3c2a1b9d8e",
  "entries": [
    {
      "guid": "4f3c2a1b9d8e",
      "message": "schema migration applied",
      "author": "ci-bot",
      "parent": "9d8e7a1b2c3d",
      "committed_at": "2026-05-29T10:14:02Z",
      "immutable": true
    }
  ]
}
```

### Diff two commits

`rdc repo diff` works between any two commits because they share a copy-on-write ancestor. Check one commit out, then diff it against another:

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag review -m server-1
$ rdc repo diff --name review --base myapp:work -m server-1
M  db/schema.sql

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

See [rdc repo diff](/en/docs/repo-diff) for the full diff reference.

### Merge a reviewed line back

```bash
$ rdc repo merge --name myapp:main --from myapp:work -m server-1
Merged myapp:work into myapp:main
```

### Merge into a running target

A mounted or running target is refused unless `--force`, which quiesces it first:

```bash
$ rdc repo merge --name myapp:main --from myapp:work --force -m server-1
Merged myapp:work into myapp:main
```

### Per-file three-way merge

Two forks (`feature` and `hotfix`) checked out from the same commit each changed some files. `--resolve theirs` folds the source (`hotfix`) into the target (`feature`): files only one side changed are taken from that side, and files both sides changed are resolved to the source. The base is auto-detected from the shared ancestor (or pin it with `--base`):

```bash
$ rdc repo merge --name myapp:feature --from myapp:hotfix --resolve theirs -m server-1
Merged myapp:hotfix into myapp:feature (three-way); 1 conflict(s) resolved --theirs: [config/app.yaml]
```

`config/app.yaml` changed on both sides and was resolved to the source; a file only `hotfix` added is applied, and a file only `feature` changed is kept. The conflict paths are reported so you can review them.

### Create an immutable base directly

```bash
$ rdc repo fork --parent myapp --tag baseline-v1 --immutable -m server-1
```

## Delta push and pull

An immutable, byte-stable image is also the foundation for **block-level delta transfer**. When the same immutable base exists on two machines, a push or pull can compute the changed blocks against that base and move only those, instead of scanning the whole encrypted image. A 1 GB repository with a few changed blocks then transfers in megabytes.

You do not normally pass a base by hand. After a full push, the CLI retains the pushed image as an immutable base on both machines and records it, so the **next** push of that repository automatically ships only the delta, with no flag, even for a fork that already exists on the target. (A *full* re-push of an existing fork still needs `--force`, since that replaces the whole image rather than applying a verified delta.) Pass `--delta-base <guid>` to pin a specific base, and `--strategy <auto|physical|shared>` to control how changed blocks are detected (`auto` is correct in nearly all cases).

```bash
# First push is a full transfer; it also retains a reusable base on both ends.
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# After local changes, the next push ships only the changed blocks, no flag needed.
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# Pin an explicit base (an immutable commit present on both machines).
$ rdc repo push --name myapp:work --to-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# Delta also works in reverse, pulling only changed blocks from a machine source.
$ rdc repo pull --name myapp:work --from-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# Re-pull an existing local repository (overwrite it) with --force.
$ rdc repo pull --name myapp:work --from-machine backup-1 --force -m server-1
```

Delta transfer applies only between machines (a remote with the FIEMAP base). Pushes to cloud object storage always transfer the full image. The base must be byte-identical on both ends, which is exactly what an immutable commit or `--immutable` fork guarantees.

## JSON schema

`rdc repo log --json` wraps the renet result in the standard envelope. The walked history lives in `entries`, newest first:

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Whether the walk completed. |
| `start` | string | GUID the walk started from. |
| `entries` | array | One object per commit, newest first. |
| `entries[].guid` | string | Commit GUID. |
| `entries[].message` | string | Commit message. Omitted when empty. |
| `entries[].author` | string | Commit author. Omitted when empty. |
| `entries[].parent` | string | Parent commit GUID. Omitted at the root. |
| `entries[].committed_at` | string | RFC 3339 commit timestamp. Omitted when unset. |
| `entries[].immutable` | boolean | Whether the commit is marked read-only (always true for a real commit). |

For the envelope fields and the auto-detection rules that emit JSON in non-TTY environments, see the [JSON Output Reference](/en/docs/ai-agents-json-output).

## Limitations

- **Refs are local.** Branch names, `HEAD`, and the reflog live in your CLI config, not on the machine. Pushing a commit to another machine ships the commit object and its in-volume metadata, but the branch ref is a config-side concept.
- **A commit refuses to mount.** That is the point: immutability is what makes a commit byte-stable. To run or edit a commit, check it out into a writable working fork first.
- **Merge resolution is file-level, not line-level.** Both whole-image take-theirs (no `--resolve`) and per-file three-way (`--resolve ours|theirs`) are supported. The three-way merge resolves conflicts a whole file at a time per the flag; it does not produce line-level hunks or merge markers within a file.
- **History is a parent chain.** `rdc repo log` walks the single `parent` link recorded at commit time. It stops when it reaches a commit whose metadata is not present on the queried machine.

## See also

- [rdc repo diff](/en/docs/repo-diff). File-level diff between any two related commits or forks.
- [Repositories](/en/docs/repositories). Create, fork, mount, and operate repositories.
