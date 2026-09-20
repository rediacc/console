# Chunk-store browse: synthesis and recommendation
Status: compacted
Owner: 8f55d4f0
Full-Text-Blob: e796b714f8f97399dbb122b10d0e684836a93c3d
Record-Sig: 7a76ed95

## Why
Whether chunk-store browse (file listing from backups) was feasible and what shape it should take. Two independent commissioned plans reached the same core finding: a manifest of LUKS-encrypted cells carries no filesystem information and cannot produce a file listing at any cost. This ruled out the cheapest approaches and forced a new artifact decision.

## Outcome
Stage 1 (local read-only browse) shipped in the private/renet submodule. Evidence: three commits in that submodule's history explicitly name browse—one fixing help text, one shipping the fourteen raw strings through i18n, one adding the license tier. A feature does not acquire translations and a tier unless it exists. The core design (encrypted TOC produced at snapshot time, client-side decryption, opaque server storage) was converged independently by two agents, one arguing engine-first and one server-first; both rejected the zero-knowledge regression that a plaintext server-side TOC would have introduced.

## Lessons
- A manifest grid of hashes over ciphertext is pure metadata; it reveals nothing about the filesystem even indirectly—walk-time answers are non-negotiable.
- Two plans written independently on opposite angles, both reaching the same constraint, supplies much higher confidence than one plan alone. Use this pattern deliberately for load-bearing decisions.
- Deferring Stage 2/3 and server integration was the right call: Stage 1 is tutorial-testable and credential-free, it unblocks the backup-restore harness, and the upload-path changes belong with the cutover work.
- The tutorial integration was a spend decision (re-record cost: 8→9 steps = 12 locale re-narrations + GPU TTS time), not a technical defect. Record the trigger explicitly: fold it in at the NEXT re-record of that video, whenever it happens.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T12:25:32Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: none
Gates: check:ci-command-planes, check:ci-plan-citations
Why-Source: model
Read-History: `git show e796b714f8f97399dbb122b10d0e684836a93c3d` recovers the text; `git log --find-object=e796b714f8f97399dbb122b10d0e684836a93c3d --all` names the commit

## History
- 2026-09-20T12:25:32Z compacted by d778be9d from `done` (record-sig 7a76ed95)
