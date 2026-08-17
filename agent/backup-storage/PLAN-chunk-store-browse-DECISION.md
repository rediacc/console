# Chunk-store browse: synthesis and recommendation

Two plans were commissioned on deliberately opposite angles, engine-first
(`PLAN-chunk-store-browse-engine.md`) and server-first
(`PLAN-chunk-store-browse-server.md`). They were written independently and they
**converge**, which is the main reason to trust the answer below.

## The finding both reached, and it decides the shape

**A file listing is not derivable from a chunk-store manifest at any cost.** The
manifest is a grid of cell hashes over the repository's LUKS *ciphertext*
(`private/renet/pkg/chunkstore/grid.go`). It carries no filesystem information,
not even indirectly. So browse cannot be a read-side feature added to what is
already stored. It needs a **new artifact produced at snapshot time**, while the
plaintext filesystem is still reachable.

That single fact kills the cheapest imaginable version of this feature. Worth
stating plainly, because "just list the manifest" is what anyone would try first.

## The security answer, which the server-first plan reached against its own interest

I asked the server-first agent to argue the server-side case and to say so if its
own angle turned out wrong. It did. A plaintext table of contents stored
server-side would let the server read filenames it currently cannot, which is a
**privacy regression** against the zero-knowledge story the product sells. It
refused to design that and landed on an **encrypted TOC written at snapshot time
and served opaquely** - the same artifact the engine plan proposes, reached from
the other direction.

Consequences that follow and are not negotiable:
- The server stores and serves an opaque blob. It never learns filenames.
- `--path` filtering happens **client-side after decryption**. A server cannot
  filter a blob it cannot read, and pretending otherwise would reintroduce the
  regression while looking like a feature.
- The residual leak is blob length. Bounded, and named rather than hidden.

## Recommendation: ship Stage 1 now, Stage 2/3 with the cutover

**Stage 1 - local read-only browse. Build this first, and soon.**
`renet backup browse` opens a LUKS image read-only, walks its ext4, prints a
listing, unmounts. Sources: the live repository, the anchor reflink (the last
committed snapshot), or an arbitrary image path.

Why it is the right first slice:
- **No format change, no server change, no credentials, no egress.**
- Near-pure reuse: `openRepoReadOnly` (`repodiff/mountset.go:52-131`) already does
  the LUKS open, mapper handling, temp mount and LIFO cleanup; `walkMount`
  (`repodiff/walk.go:30-70`) already produces the node records.
- **It is CI-testable and tutorial-able**, which nothing else here is. That
  matters right now: the backup-restore tutorial is being rewritten and its
  hardest constraint is that the harness has no account credentials. Both plans
  independently concluded browse belongs in that tutorial, and Stage 1 is the leg
  that can actually run in it.

What it honestly does not answer: "is my file in last Tuesday's backup" without
restoring Tuesday first.

**Stage 2 - the writer.** During `backup snapshot`, walk the **staged reflink**,
not the live mount. The reflink is the exact bytes the manifest describes, so the
index cannot skew from the snapshot it claims to describe. Walking the live mount
would produce an index that disagrees with its own snapshot by whatever changed
during the run - the one lie a browse feature must not tell. Compress, encrypt
client-side, upload under a new key, reference from D1 at commit. Cost is
O(files), riding an O(image) rehash, so relatively cheap - **to be measured, not
assumed.**

**Stage 3 - remote browse.** `--at <snapshot>` mints a restore-intent session,
fetches only the index object, decrypts, prints. One small GET, no chunk traffic.

Pre-Stage-2 snapshots have no index. They must **say so and name the escape
hatch** (restore, then browse locally) rather than print an empty listing. Per the
clean-break rule there is no backfill command and no dual path; old snapshots age
out under retention and the gap closes itself.

## Shape, agreed by both plans

```
rdc backup browse <repo-ref> [--at <snapshot>] [--path <subdir>] [--depth <n>]
                             [--limit <n>] [--long]
```

- Positional ref, house convention, machine derived.
- `--at` mirrors `backup restore --at` exactly.
- Columns `name, type, size, modified` reproduce the retired `storage browse`
  output byte-for-byte, so an operator who lost that verb gets the shape back.
- Resolve with **`resolveRepoRefLocal`** (config-only), never `resolveRepoRef`
  (resolves a machine). Browse must work when the machine is gone. The server
  plan calls this "the difference between a DR tool and a convenience" and it is
  right.
- Command plane `other`. Declaring `machine` would fail
  `check:ci-command-planes` Rule 3.
- **Do not** extend `rdc storage browse` - that is a live rclone-remote browser
  and stays. One noun, one storage system.
- **Do not** add a second `backup` listing verb (an `ls` beside `browse`); the
  repo already refused to grow one verb per route rather than per concept.

Every result, table and JSON, must state its source and that source's timestamp.
A listing that does not say what it is a listing OF is how someone restores the
wrong snapshot.

## Rejected, and why it is still worth knowing

Sparse on-demand ext4 reads: aes-xts is length-preserving and sector-local, so a
holder of the repo credential can decrypt individual cells and walk the namespace
without downloading the image - no snapshot-time cost, no new object, no
upload-path change. **Rejected for v1** because it needs a correct ext4 reader.
Named as the upgrade path rather than buried.

## What I have not verified

These are plans, not findings. I confirmed the load-bearing gap myself (no browse
exists; `backup manifests` lists snapshots via the account API at
`backup.ts:362`) and the citations above are the agents'. Before implementing,
the manifest-carries-no-filesystem-data claim and the `repodiff` reuse claim
should each be checked against the code, because they are what the whole design
rests on.

## The decision I need

Stage 1 is small, credential-free, and unblocks the tutorial. I recommend
building it now. Stage 2 and 3 change the upload path and add a stored object,
so they belong with the cutover work rather than ahead of it.

## Follow-up: the tutorial leg, deliberately NOT taken in this wave

`rdc backup browse` is shipped and tested but is NOT demonstrated in
`tutorial-backup-restore`. Both browse plans recommend it belongs there, and it
is the natural strengthening of step 7 ("prove the data survived"): instead of
only `cat orders.txt`, browse can show the file is present in the restored
repository without opening it.

**Why it was not added:** the cast had just been re-recorded to 8 markers, and a
9th step means re-recording again plus redoing the storyboard, transcript, mdx
and 12 locales, then a fresh narration pass. Per CLAUDE.md the 13-locale
re-narration chain costs real TTS GPU time, so this is a spend decision rather
than a code one, and the feature is fully shipped either way. The operator was
asked and the default (wait) executed unanswered.

**The trigger:** fold this in at the NEXT re-record of `tutorial-backup-restore`,
whatever causes it. Concretely, add a step running

    rdc backup browse my-app

after the restore is proven, and let the existing 8-step structure become 9.

**What NOT to do:** do not add the step without re-recording. The storyboard is
compared against the cast marker-for-marker (`check-tutorial-parity.ts:203`), so
a 9th card against an 8-marker cast fails parity in a way that reads like a docs
defect rather than a missing recording.
