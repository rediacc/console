---
title: "git diff for Encrypted Disk Images: Diffing Forks Without Decrypting Them"
description: "Forks are constant-time, but answering what a fork changed used to mean decrypting and walking the whole filesystem. rdc repo diff reports A/M/D/R between two forks by comparing the encrypted images at the block level, so cost tracks changed blocks, not repository size."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-28
category: guide
tags:
  - luks
  - btrfs
  - ext4
  - fiemap
  - cli
featured: false
language: en
---

> **TL;DR.** `rdc repo diff` shows the file-level difference between two forked repositories in `git status --short` grammar (A/M/D/R), and it never decrypts either one.
>
> - It compares the two LUKS image files at the block level with the FIEMAP ioctl, which reads extent-map metadata only. No key is loaded, no plaintext is read.
> - aes-xts is length-preserving and encrypts each 512-byte sector independently, so a changed plaintext sector is a changed ciphertext sector at the same offset (shifted by the 16 MiB LUKS data offset). Subtract the offset, map device ranges to file names through the ext4 extent map, and you have a file list.
> - Cost tracks the number of changed blocks, not repository size. A 1 GB fork and a 100 GB fork diff in the same milliseconds, because the compare is metadata-only.

A fork in Rediacc is `cp --reflink=always` of a repository's LUKS image. It is constant-time and size-independent: a 100 GB repo forks as fast as a 1 GB repo, because btrfs copies the extent map and shares the underlying blocks copy-on-write. We lean on this hard. Forks are the per-test isolation unit, the throwaway branch, the staging copy you destroy when you are done.

What we did not have was a cheap answer to the obvious next question: what did this fork actually change relative to its parent. The naive route is to mount the fork, unlock the LUKS container, walk the inner ext4, and hash every file against the parent. That is O(repository size) in both reads and decryption, it needs the keys live on the diff path, and it throws away the one thing the storage layer already knows for free, which is exactly which blocks diverged. `rdc repo diff` takes the other route. It is O(changed blocks), it loads no key, and it gets its file list by diffing the two encrypted images.

## The stack you are diffing

It helps to be precise about what "two repositories" means physically, because the whole trick depends on it. From the bottom up: an SSD, the host filesystem, a btrfs pool, a single LUKS2 image file per repository, the dm-crypt device that LUKS presents when unlocked, and the ext4 filesystem inside that the containers actually use. One repository is one file on the btrfs pool.

A fork is a reflink of that file. Right after the fork, the two image files are byte-identical and share every physical extent. The parent and the fork are not two copies of the data, they are two extent maps pointing at the same blocks. When something writes inside the fork, copy-on-write allocates a fresh physical extent for the changed region and rewrites only that fork's extent map to point at it. The parent's blocks are untouched.

So "diff two repositories" reduces to "diff two files that share most of their extents." That is a question the kernel can already answer without anyone reading a single byte of either file.

## FIEMAP: asking the kernel what changed without reading it

The FIEMAP ioctl returns a file's extent map: the list of (logical offset, physical offset, length) tuples that say where each region of the file lives on disk. It is pure filesystem metadata. It does not read file data, and for an encrypted image it does not need a key, because the ciphertext is just bytes the kernel never has to interpret.

Diff the two extent maps. Any logical range where both forks point at the same physical extent is shared, and shared means identical, because that is literally the same block on the device. The ranges where the fork has its own private physical extent are precisely the regions copy-on-write allocated for the fork's writes. Those are the changed blocks, and we got them out of metadata that the storage layer maintains anyway.

This is where the cost story comes from. The FIEMAP compare reads extent records, not data, so its work scales with how many extents changed, not with how big the repository is. The 1 GB fork and the 100 GB fork return the same short list of private extents in the same milliseconds if they changed the same files. The honest caveat is that extent-walk time scales with image fragmentation rather than size: a copy-on-write image under heavy random writes accumulates extents, and on the worst-fragmented production image I measured the full `filefrag` walk took 3.19 seconds (see the fragmentation benchmark post). That is the ceiling on the metadata side, and it touches a background-style scan, not a data read.

## From a changed block to a file name, through two encrypted layers

A list of changed byte ranges in the encrypted image is not yet useful. The ranges are positions in the ciphertext, and the names you want live two layers up in the inner ext4. The bridge between them is address arithmetic, not decryption.

LUKS encrypts with aes-xts, which is length-preserving and encrypts each 512-byte sector independently. A changed plaintext sector produces a changed ciphertext sector at the same sector offset. The only displacement is the LUKS data offset, the 16 MiB of header and keyslots that sit in front of the encrypted payload. Subtract that offset from each changed image range and you have the corresponding range on the dm-crypt device, which is the block device the inner ext4 sits on. No key was used to compute that. It is subtraction.

Now map device ranges to files. ext4 keeps an extent map per inode too, the same kind of (logical, physical, length) structure, reachable through FIEMAP on the mounted inner filesystem. Walk the inodes once to build a block-to-file index, then look up each changed device range in that index. The range that overlaps inode 1234's data extents belongs to whatever path inode 1234 occupies. That is the file that changed.

State plainly what this never does: it never derives plaintext from the changed image. It reads filesystem structure at known offsets, on both the encrypted and the decrypted side, and joins the two by address. The block filter says which device regions moved; the ext4 extent map says which file owns each region. Neither step inspects the contents of a changed block to decide it changed.

## Adds, deletes, and renames: the inode-identity walk

Modifications fall out of the block compare directly. Adds, deletes, and renames need one more observation, which the reflink gives us for free: a fork preserves inode numbers. Reflinking the whole image clones the entire inner filesystem byte for byte before any divergence, so an inode that existed in the parent has the same inode number in the fork.

That makes identity a set comparison. An inode present on both sides with a different path is a rename. An inode present only on the new side is an add. An inode present only on the old side is a delete. A rename is confirmed by device-extent overlap: the renamed file's data blocks sit at identical device offsets on both forks, because the two forks share one coordinate system, and that overlap also rules out the coincidence of an inode number getting reused for unrelated data. A pure rename therefore shows up with the file's data blocks unchanged and only the directory entry moved.

Here is the default name-status form, the same A/M/D/R grammar you already read from `git status --short`:

```
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

One modified file in a 1 GB repository, reported from a block compare that read no file data and unlocked nothing.

The default does one more thing for correctness. The block filter is a superset, because a btrfs copy-on-write extent can cover more than the bytes that actually changed, so a write to one file can flag a neighbor that happens to share an extent. To avoid reporting a file that did not change, the default confirms each block-flagged candidate by hashing only that file on both sides. It hashes the candidates, not the repository, so the confirmation cost still tracks the change set. `--fast` trusts the block filter and skips the confirmation when you would rather have the answer immediately and tolerate the occasional false positive.

## Why an AI agent needs this

The reason this command exists at all is the agent workflow. An AI agent can fork production in constant time, run a risky change inside the isolated fork, and then needs to know exactly what it touched before promoting anything back. Fork is the branch. Diff is the review.

The agent does not read name-status, it reads `--json`:

```
$ rdc repo diff --name prod:experiment --json -m hostinger
```

The structured output gives the agent a precise change set it can reason about: which paths it modified, which it created, which it deleted, and with `--stat` the per-file change magnitude in bytes and blocks. An agent that can see its own diff before it promotes is an agent you can let near production, because the blast radius is inspectable rather than asserted. The other modes serve the same review loop: `--name-only` for a bare path list, `--content <path>` for a unified text diff of a single file (text only; a binary file reports `Binary files differ`), and `--stat` when the agent needs to know not just what changed but how much.

## Why DR testing needs it

The same primitive answers a disaster-recovery question that was previously awkward to ask without risk. Fork production, restore a backup into the fork, and diff the fork against production. The diff tells you whether the restore reproduced the file set you expected, and it does this without taking production down and without decrypting anything on the diff path.

That is a rehearsal you can run on a schedule. The restore lands in an isolated fork, the diff reports the delta in git grammar, and a clean rehearsal is one where the changed set matches what the backup was supposed to contain. You are validating recovery against live production, on a copy that costs nothing to make and nothing to throw away.

## Honest limits

The content diff is text only. `--content` produces a unified diff for text files and reports `Binary files differ` for everything else, the same way git does, because a line-oriented diff of an encrypted-then-compressed blob is noise.

It diffs related forks, not arbitrary repositories. The whole mechanism rests on a shared coordinate system: shared extents that prove equality, preserved inode numbers that anchor identity, a common data offset. Two repositories that were never forked from a common ancestor share none of that, and there is no cheap diff between them. This is feature, not bug, in the same way `git diff` between two unrelated histories is not meaningful.

Rename detection is inode-based. It is exact for the renames a filesystem actually records as renames. A delete-then-create of identical content under a new name is two operations to the inode table, so it reports as one delete and one add, not a rename. git's content-similarity rename heuristic would call that a rename; the inode walk will not, and that is the correct answer about what the filesystem did even if it is not the answer about what a human intended.

And the metadata walk scales with fragmentation. On a heavily fragmented image the extent enumeration is seconds, not milliseconds. It is still independent of repository size and still free of any data read, but it is not literally instant on the worst-fragmented images.

## The takeaway

`rdc repo diff` puts version-control ergonomics on encrypted, running infrastructure. The interface is deliberately git, A/M/D/R and unified diffs and `--stat`, so there is nothing new to learn: if you can read `git status --short`, you can read a diff between two LUKS images. The engineering underneath is the part worth caring about, and it amounts to two refusals. It never decrypts, because aes-xts lets a block-level FIEMAP compare locate every changed sector by address. And it never pays for data that did not change, because copy-on-write already recorded exactly which blocks diverged. Fork is the branch, diff is the review, and the review costs what the change costs, not what the repository weighs.
