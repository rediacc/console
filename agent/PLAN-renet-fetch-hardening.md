# PLAN: renet fetch hardening (remaining sweep from closed renet PR #96)
Status: compacted
Owner: housekeeping writer agent, branch main
Full-Text: f7a5351a9 agent/PLAN-renet-fetch-hardening.md
Full-Text-Blob: 0f714f0ac7271327eb51438deb66d7250cb4b174
Record-Sig: 4cca6f4a

## Why
renet PR #96 was closed without merging, and its closing comment was the only
surviving record of an eight-site inventory of unretried network fetches (apt,
curl, `docker pull`) that flake provisioning and CI. This file exists to keep
that inventory somewhere a future session will actually find it.

## Outcome
NOT SHIPPED, and this is the honest reading rather than the header's. Measured
2026-09-06 in the renet submodule at its current pointer: exactly 1 of the 8
sites is hardened, and that one, the Docker GPG key fetch (now a five-attempt
loop plus a post-loop non-empty assertion), landed BEFORE this plan file entered
the tree. This plan therefore produced zero commits. All seven remaining sites
are present and unretried: both rsync tarball curls in the Dockerfile, the Ceph
prerequisites apt and the cephadm bootstrap, the two bare apt sites in the
fork-dest prep and the worker service, `curl get.docker.com | sh` on both the
apt and dnf branches, and the build and CI `docker pull`s. Site 6 was rewritten
by the rclone decommission's fallout for a distro-packaging reason, not
hardened; its apt path still has no retry loop.

## Lessons
- The plan's own 2026-08-18 warning that its file:line inventory had drifted a
  second time is confirmed a THIRD time: every line number in it is now off. An
  inventory keyed to line numbers decays. Key it to function names.
- THIS RECORD IS `compacted` AND ITS WORK IS NOT. `--park` only parks a plan
  whose `n_open` box count is non-zero, and this plan carries no checkbox boxes
  at all, so the tool has no state for "unfinished, no boxes" and the record
  takes the housekeeping exemption it has not earned. Seven sites are open.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:08:53Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: none
Gates: check:ci-external-links
Why-Source: author
Read-History: `git show 0f714f0ac7271327eb51438deb66d7250cb4b174` recovers the text; `git log --find-object=0f714f0ac7271327eb51438deb66d7250cb4b174 --all` names the commit

## History
- 2026-09-06T17:08:53Z compacted by 8f55d4f0 from `draft` (record-sig 4cca6f4a)
