---
title: "git diff for Encrypted Disk Images: Diffing Forks Without Decrypting Them"
description: "rdc repo diff compares encrypted images at the block level and reports A/M/D/R. No key touched. Cost tracks changed blocks, not repo size."
author: Rediacc
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

So, a fork in Rediacc is `cp --reflink=always` of a repo's LUKS image. Instant, and it does not care about size. A 100 GB repo forks as fast as a 1 GB repo. I know that sounds like marketing, but it is just how reflinks work: btrfs copies the extent map and shares the blocks underneath. We lean on this hard. Forks are the test sandbox, the throwaway branch, the staging copy you trash when you are done.

What we did not have was a cheap answer to the obvious next question: what did this fork actually change. The naive route: mount the fork, unlock the LUKS container, walk the inner ext4, hash every file against the parent. That scales with repo size in both reads and decryption. It needs the keys live on the diff path. And it throws away the one thing the storage layer already knows for free: which blocks diverged. `rdc repo diff` takes the other route. It scales with changed blocks. It loads no key. It gets its file list by diffing the two encrypted images.

## The stack you are diffing

Let me be precise about what "two repositories" means on disk. The whole trick depends on it. Bottom up: an SSD, the host storage, a btrfs pool. On top of that, one LUKS2 image file per repo. Unlock it and you get a dm-crypt device. Inside that lives the ext4 filesystem the containers use. One repo is one file on the btrfs pool.

A fork is a reflink of that file. Right after the fork, the two image files are byte-identical. They share every physical block. The parent and the fork are not two copies of the data. They are two extent maps pointing at the same blocks. When you write inside the fork, the storage layer allocates a fresh block for the changed region. Only that fork's extent map gets rewritten. The parent's blocks stay untouched.

So "diff two repositories" reduces to "diff two files that share most of their extents." The kernel can already answer that. Nobody needs to read a single byte of either file.

## FIEMAP: asking the kernel what changed without reading it

The FIEMAP ioctl returns a file's extent map: a list of (logical offset, physical offset, length) tuples. Each tuple says where one part of the file lives on disk. It is pure filesystem metadata. It does not read file data. For an encrypted image it needs no key. The ciphertext is just bytes the kernel never has to interpret.

Diff the two extent maps. Any logical range where both forks point at the same physical block is shared. Shared means identical, because it is literally the same block on the device. The ranges where the fork has its own private block are the writes. Those are the changed blocks. We got them from metadata the storage layer keeps anyway.

Here is where the cost story comes from. The FIEMAP compare reads extent records, not data. Its work scales with how many extents changed, not repo size. The 1 GB fork and the 100 GB fork return the same short list of private extents. Same milliseconds, if they changed the same files. Honest caveat: extent-walk time scales with image fragmentation, not size. A copy-on-write image under heavy random writes piles up extents. The full `filefrag` walk took 3.19 seconds on the worst-fragmented production image I measured. See the fragmentation benchmark post. That is the ceiling on the metadata side. It is a background scan, not a data read.

## From a changed block to a file name, through two encrypted layers

A list of changed byte ranges in the encrypted image is not useful yet. The ranges are positions in the ciphertext. The names you want live two layers up, in the inner ext4. The bridge between them is address arithmetic, not decryption.

LUKS encrypts with aes-xts. It is length-preserving and encrypts each 512-byte sector on its own. A changed plaintext sector produces a changed ciphertext sector at the same offset. The only shift is the LUKS data offset. That is the 16 MiB of header and keyslots in front of the encrypted payload. Subtract that offset from each changed image range. Now you have the matching range on the dm-crypt device. That is the block device the inner ext4 sits on. No key was used. It is subtraction.

Now map device ranges to files. ext4 keeps an extent map per inode too. Same (logical, physical, length) structure. You reach it through FIEMAP on the mounted inner filesystem. Walk the inodes once to build a block-to-file index. Then look up each changed device range in that index. A range that overlaps inode 1234's data extents belongs to that inode's path. That path is the file that changed.

Let me state plainly what this never does. It never derives plaintext from the changed image. It reads filesystem structure at known offsets. It does this on both the encrypted side and the decrypted side. Then it joins the two by address. The block filter says which device regions moved. The ext4 extent map says which file owns each region. Neither step inspects the contents of a changed block to decide it changed.

## Adds, deletes, and renames: the inode-identity walk

Modifications fall out of the block compare directly. Adds, deletes, and renames need one more observation. The reflink gives it to us for free: a fork preserves inode numbers. Reflinking the whole image clones the entire inner filesystem byte for byte before anything diverges. So an inode that existed in the parent has the same number in the fork.

That makes identity a set comparison. An inode on both sides with a different path is a rename. An inode only on the new side is an add. An inode only on the old side is a delete. A rename is confirmed by device-extent overlap. The renamed file's data blocks sit at the same device offsets on both forks. The two forks share one coordinate system. That overlap also rules out an inode number getting reused for unrelated data. A pure rename then shows up with the file's data blocks unchanged. Only the directory entry moved.

Here is the default name-status form, the same A/M/D/R grammar you already read from `git status --short`:

```
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

One modified file in a 1 GB repository. Reported from a block compare that read no file data. Nothing was unlocked.

The default does one more thing for correctness. The block filter is a superset. A btrfs extent can cover more than the bytes that actually changed. So a write to one file can flag a neighbor that shares an extent. To avoid reporting a file that did not change, the default confirms each block-flagged candidate. It hashes only that file on both sides. It hashes the candidates, not the repo. So confirmation cost still tracks the change set. `--fast` trusts the block filter and skips the confirmation. Use it when you want the answer fast and tolerate the odd false positive.

## Why an AI agent needs this

The reason this command exists at all is the agent workflow. I kept watching agents fork production, run changes, and then have no clean way to report what they actually touched. An AI agent can fork production instantly. It runs a risky change inside the isolated fork. Then it needs to know exactly what it touched before promoting anything back. Fork is the branch. Diff is the review.

The agent does not read name-status, it reads `--json`:

```
$ rdc repo diff --name prod:experiment --json -m hostinger
```

The structured output gives the agent a precise change set. Which paths it modified, created, deleted. With `--stat`, the per-file change size in bytes and blocks. An agent that sees its diff before it promotes is one you can let near production. The blast radius is inspectable, not asserted. Other modes serve the same review loop. `--name-only` for a bare path list. `--content <path>` for a unified text diff of one file (text only; a binary file reports `Binary files differ`). `--stat` when the agent needs to know what changed and how much.

## Why DR testing needs it

The same primitive answers a DR question that used to be awkward to ask without risk. Fork production. Restore a backup into the fork. Diff the fork against production. The diff tells you whether the restore reproduced the file set you expected. It does this without taking production down. And it never decrypts anything on the diff path.

That is a rehearsal you can run on a schedule. The restore lands in an isolated fork. The diff reports the delta in git grammar. A clean rehearsal: the changed set matches what the backup was supposed to contain. You are validating recovery against live production. The copy costs nothing to make and nothing to throw away.

## Honest limits

The content diff is text only. `--content` produces a unified diff for text files. For everything else it reports `Binary files differ`, the same way git does. A line-oriented diff of an encrypted-then-compressed blob is noise.

It diffs related forks, not arbitrary repositories. The whole mechanism rests on a shared coordinate system. Shared extents prove equality. Preserved inode numbers anchor identity. A common data offset ties it together. Two repos that were never forked from a common ancestor share none of that. There is no cheap diff between them. This is feature, not bug. The same way `git diff` between two unrelated histories is not meaningful.

Rename detection is inode-based. It is exact for the renames a filesystem actually records as renames. A delete-then-create of identical content under a new name? Two operations to the inode table. So it reports as one delete and one add, not a rename. git's content-similarity heuristic would call that a rename. The inode walk will not. That is the correct answer about what the filesystem did. Even if it is not the answer about what a human intended.

And the metadata walk scales with fragmentation. On a heavily fragmented image the extent enumeration is seconds, not milliseconds. It is still independent of repo size. It is still free of any data read. But it is not literally instant on the worst-fragmented images.

## The takeaway

`rdc repo diff` puts version-control ergonomics on encrypted, running infrastructure. The interface is deliberately git. A/M/D/R, unified diffs, `--stat`. Nothing new to learn. If you can read `git status --short`, you can read a diff between two LUKS images. The engineering underneath is the part worth caring about. It amounts to two refusals. It never decrypts. aes-xts lets a block-level FIEMAP compare locate every changed sector by address. And it never pays for data that did not change. The storage layer already recorded which blocks diverged. Fork is the branch. Diff is the review. The review costs what the change costs, not what the repo weighs.
