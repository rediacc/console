# Devbox: apply the operator's uid at image build, not at every container start
Status: compacted
First-Seen: 2026-09-20
Full-Text-Blob: 5a48f54ad9b4a491828ee44e7c03922c334c05d2
Record-Sig: 1b0f4e5a

## Why
The devbox container startup renumbers the `vscode` user from a static 7111 (baked at image build) to the host's uid on every start, costing 441 seconds due to overlayfs copy-up of 1.8 GiB across 81,881 files. Two fixes to the entrypoint in 2026-09-07 (stopping recursive `usermod` chown and removing error swallowing) were necessary but insufficient; the residual cost is inherent to
chowning files in a lower layer, not loop overhead.

## Outcome
Plan drafted 2026-09-07 on operator instruction. Proposes a two-layer approach: uid-agnostic published base + thin per-operator derived layer baked at image build via `Dockerfile.uid`. Design includes file edits, new gates, and proof strategy. Status: design complete, not yet implemented.

## Lessons
- Two necessary fixes can remain insufficient when the residual is a property of the system (overlayfs copy-up), not of the loop. Performance bottleneck must be moved, not optimized in place.
- Keying derived image tags on base image ID ensures automatic rebuild on upstream changes without explicit versioning logic.
- The fast path (skip derive when ids already match) requires measurement; it works on this host but was unverified on macOS (uid 501) and WSL2.
- Five alternatives rejected with specific failure modes; 'make it fast' was the only one with no alternative—the 441s is the optimal form, proving the architecture must change.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: d778be9d
Compacted-At: 2026-09-20T17:54:59Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: .ci/lib/devbox.sh, .ci/legacy/run-legacy.sh, .devcontainer/devbox-entrypoint.sh, .ci/config/constants.sh, docs/agent-reference/local-env.md, .ci/rediacc_ci/quality/devbox_exec.py, .claude/rediacc_hooks/guards/block_host_toolchain_run.py, .claude/oracles/pre-bash/block-host-toolchain-run.sh
Gates: check:ci-devcontainer-scripts, check:ci-docker-npm-pins, check:ci-dockerfile-mirror-resilience, check:ci-unverified-downloads
Why-Source: model
Read-History: `git show 5a48f54ad9b4a491828ee44e7c03922c334c05d2` recovers the text; `git log --find-object=5a48f54ad9b4a491828ee44e7c03922c334c05d2 --all` names the commit

## History
- 2026-09-20T17:54:59Z compacted by d778be9d from `draft` (record-sig 1b0f4e5a)
