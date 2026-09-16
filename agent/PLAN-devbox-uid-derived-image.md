# Devbox: apply the operator's uid at image build, not at every container start

Status: draft
Written: 2026-09-07, by a Plan agent, on the operator's instruction: "7111 is not
needed for dockerfile (user) actually. let's employ a planning agent to have the
same user id automatically for who ever runs ./run.sh setup. So, not statically
1000 which is current I guess."

## Why

`.devcontainer/Dockerfile` bakes the `vscode` account at 7111 and chowns the image
to it. `.devcontainer/devbox-entrypoint.sh` then renumbers that account to the
host's ids and re-chowns three trees on EVERY container start, before it execs
openvscode-server.

### The measurement, which is the whole argument

A real `./run.sh devbox up` on this host, `docker logs -t`, with both of the
2026-09-07 entrypoint fixes already in the tree:

```
12:25:23.845 [devbox] remapping vscode from 7111:7111 to 1000:1000
12:25:24.031 [devbox] chown /home/vscode
12:28:33.143 [devbox] chown /opt/openvscode-server          189.1s in /home/vscode
12:29:18.530 [devbox] chown /go                              45.4s in /opt
12:32:45.068 [devbox] starting openvscode-server on :17940  206.5s in /go
```

**441.2 seconds** between container start and the server being exec'd, against the
60-second probe budget at `.ci/lib/devbox.sh:773`. A synthetic run of the same
work in a throwaway container measured 7m27.8s, agreeing to within 1.5 percent.

| Fact | Value |
|---|---|
| Entries owned by 7111 in the published image | 81,881 |
| Bytes behind them | 1800.35 MiB |
| `/home/vscode` | 869M / 27,863 entries |
| `/go` | 595M / 46,172 entries |
| `/opt/openvscode-server` | 358M / 7,844 entries |
| What it is bound on | overlayfs copy-up, not CPU |

`/go` is the most expensive tree, not `/home/vscode`, tracking file COUNT rather
than bytes. Any future "just skip /go" skips the largest half of the work.

### The correction this plan records

Two real defects were found and fixed in the entrypoint on 2026-09-07: `usermod
-u` doing its own unscopeable recursive chown of a home directory holding a 3.9 GB
bind-mounted `~/.claude`, and a `chown -R ... 2>/dev/null || true` that crossed
those mounts and silenced its own errors.

**Both were necessary. NEITHER WAS SUFFICIENT, and it would have been easy to
believe otherwise.** After both fixes the walk is in its optimal form (`-xdev`,
an id predicate, no home recursion) and still costs 441 seconds, because the
residue is 1.8 GiB of overlayfs copy-up, which is a property of chowning files
that live in a lower layer rather than of the loop. The
`Devbox started but nothing is listening on 17940 after 60s` message is therefore
NOT a flake and was not fixed by them: it is reporting a container that is still
chowning. It is honest, and it stays until the renumber leaves container start.

## The design

Split the image in two.

1. A **uid-agnostic published base**. Delete the static renumber at
   `.devcontainer/Dockerfile:47-55`, so `ghcr.io/rediacc/devcontainer:latest`
   ships whatever uid the upstream devcontainers base gives `vscode`: a
   placeholder no code reads, not a promise.
2. A **thin, local, per-operator derived layer**. `devbox_ensure_image`
   (`.ci/lib/devbox.sh:363`), which both `./run.sh setup`
   (`.ci/legacy/run-legacy.sh:687`) and `./run.sh devbox up`
   (`.ci/lib/devbox.sh:507`) already funnel through, obtains the base exactly as
   today (pull, falling back to a local build) and then derives
   `rediacc/devbox:uid<UID>-gid<GID>-<base-image-id12>` from a new tracked
   `.devcontainer/Dockerfile.uid` whose single `RUN` does the usermod/groupmod
   plus one `find / -xdev ... -exec chown` at BUILD time, into a layer, once per
   operator per base image.

When the base's ids already equal `id -u`/`id -g`, the derive is skipped entirely
and the base is used as is. The entrypoint's renumber block
(`.devcontainer/devbox-entrypoint.sh:89-136`) is deleted and replaced by an
assertion that fails loudly if the ids disagree.

Keying the derived tag on the base IMAGE ID is what keeps the existing rebuild
recipe true: a new base id means a tag that is not present, so it re-derives
automatically.

## Why not the alternatives

1. **`--build-arg DEVBOX_UID` on the base build.** Fails the DEFAULT path:
   `devbox_ensure_image` PULLS first (`:373-375`) and only builds when the pull is
   denied (`:382-386`), so on a real machine the build arg never runs. It also
   makes one tag name two different images, and `devbox_image_digest`
   (`:357-361`) reads `RepoDigests`, which a locally built image lacks, so
   provenance silently becomes `unknown`.
2. **`docker run --user $(id -u)`.** Two independent failures. Ownership: 81,881
   files stay at the baked id, so extension installs, `go install` into `/go` and
   the Playwright cache all EACCES (already recorded at
   `.devcontainer/devbox-entrypoint.sh:9-13`). Identity: an id with no `/etc/passwd` entry has
   no name and no home, breaking `sudo` (used by `start-kvm.sh`), `whoami`,
   `$HOME` and git, and forcing `devbox_exec` back to a numeric `-u`, which
   `check-devbox-exec.sh` assertion B2 exists to forbid.
3. **Keep the renumber, make it fast.** Nothing left to make fast: 441s IS the
   optimal form. The residue is copy-up, not loop overhead.
4. **Docker userns-remap.** Daemon-wide, so it changes traefik, rustfs and
   anything renet starts through the bound socket, and it shifts ids on the repo
   bind-mounted at its identical host path by design (`:626-628`).
5. **Bake `chmod -R a+rwX`.** Same 1.8 GiB copy-up, but in the PUBLISHED image, so
   every operator pays it instead of one operator locally. Also permanently
   world-writable `/go` and `/opt/openvscode-server`.
6. **Raise the 60s probe.** The wait is the symptom, not the defect.

## File set

- `.devcontainer/Dockerfile`: delete `47-55`. Nothing else names 7111; `181`,
  `271-273`, `693`, `715` are by NAME and stay correct. Line 55's
  `2>/dev/null || true` is the same error-swallowing shape fixed in the entrypoint
  on 2026-09-07; deleting it closes the sibling.
- `.devcontainer/Dockerfile.uid` (new, tracked): `ARG BASE_IMAGE`/`FROM`, ids as
  ARGs guarded with the `: "${X:?...}"` idiom already at `Dockerfile:363-369`,
  old ids read from the account itself, the gid-collision branch carried over from
  `.devcontainer/devbox-entrypoint.sh:95-100`, and a chown with NO `2>/dev/null` and NO
  `|| true`. Its comment must record that at build time there are no bind mounts,
  so `usermod -u`'s own recursive home chown is bounded and correct here, and the
  `mktemp -d` trick at `.devcontainer/devbox-entrypoint.sh:101-124` is deliberately NOT needed.
- `.ci/config/constants.sh:131`: `DEVBOX_IMAGE` becomes `DEVBOX_BASE_IMAGE`; add
  `DEVBOX_UID_IMAGE_REPO="rediacc/devbox"`, deliberately not a `ghcr.io/` name so
  a derived tag can never be mistaken for something publishable.
- `.ci/lib/devbox.sh`: new `devbox_base_user_ids`, `devbox_uid_image`,
  `devbox_ensure_uid_image`; `:760` uses the derived tag; a
  `com.rediacc.devbox.uid` label beside `DEVBOX_SLUG_LABEL_KEY` (`:31`); the
  rehost-on-drift block (`463-491`) extended with an ids-label check so a
  container from the previous scheme is recreated once, automatically.
- `.devcontainer/devbox-entrypoint.sh`: delete `89-136`, replace with a loud
  assertion; rewrite the header archaeology; keep `141-150`, `169-170`,
  `205-218`, `221-230`.
- `.ci/legacy/run-legacy.sh:775-781`: the `--check` `image` row reports base AND
  derived tag (present / would be built / not needed).

Prose that becomes false and must move in the same change:
`docs/agent-reference/local-env.md:71-79`, `.ci/lib/devbox.sh:1060-1067`,
`check-devbox-exec.sh` plus its twin `.ci/rediacc_ci/quality/devbox_exec.py:31-32`,
and the drifting line references in
`.claude/rediacc_hooks/guards/block_host_toolchain_run.py:470-478, 505-509` and
`.claude/oracles/pre-bash/block-host-toolchain-run.sh:301, 332`.

## Gates, in the same change (invariant 1)

1. `.ci/scripts/quality/check-setup-idempotency.sh`: assertion A's table at
   `80-95` gains a row for the new build with its guard, plus its constructed
   control. Without it, a `docker build` on the setup path with no presence guard
   is caught by nothing.
2. A NEW gate, proposed name check-ci-devbox-uid (written without the colon on purpose: it does not exist yet, and the colon form is what the citation gate reads as a claim that it does), control-first and hermetic, because nothing
   today can see the regression this change prevents: no recursive chown or
   `usermod -u` in the entrypoint; no numeric `usermod -u`/`groupmod -g` literal
   in the Dockerfile; `Dockerfile.uid` takes ids as guarded ARGs and its chown
   does not end `2>/dev/null` or `|| true`; the `docker run` names the derived
   image. Registration is part of the same change: gate header, `package.json`,
   `npm run gen:gates-lock`, `npx tsx scripts/gen-docs.ts --write`.
3. Comment parity: `check-devbox-exec.sh` and `.ci/rediacc_ci/quality/devbox_exec.py:31-32` state the
   entrypoint-renumber rationale for B2 and must move together;
   `test_twin_parity.py` drives the pair.
4. Re-run and re-read (do not edit): `check:ci-devcontainer-scripts`,
   `check:ci-unverified-downloads`, `check:ci-docker-npm-pins`,
   `check:ci-dockerfile-mirror-resilience`. The last three enumerate tracked
   Dockerfiles by glob and carry anti-vacuity FLOORS, so `Dockerfile.uid` enters
   their denominators and the floors deserve one honest look after it lands.

## Proof

The single clearest before/after: `docker logs -t <container>` shows NO
`remapping` and NO `chown` lines, and `starting openvscode-server` within about a
second of container start, with the `nothing is listening` line gone.

Then: `docker exec <c> id vscode` prints the operator's ids; `-u vscode whoami`
prints `vscode`; `-u vscode sudo -n true` exits 0 (this is what alternative 2
breaks); writes into `/go/bin` and `/opt/openvscode-server/extensions` succeed;
`git status --porcelain` produces no `dubious ownership`.

On THIS host the derive must not happen at all (`id -u` is 1000 and the base
ships `vscode` at 1000 once the 7111 block is gone), so `docker image ls` shows
no `rediacc/devbox:*`. The different-uid case is provable here without a second
machine by building `Dockerfile.uid` with `DEVBOX_UID=1001` and asserting
`find / -xdev \( -uid 1000 -o -gid 1000 \) | wc -l` is 0.

## Unverified, named rather than asserted

- The on-disk size of the derived layer: 1800.35 MiB of file bytes and 1.93 GB of
  container block writes were measured, but the image was not built.
- That the upstream `mcr.microsoft.com/devcontainers/base:ubuntu-24.04` ships
  `vscode` at 1000. Inferred from this repo's own predicate at
  `.devcontainer/Dockerfile:55`, not from the upstream image. Nothing breaks if it
  differs: the derive compares live ids and the fast path simply does not fire.
- macOS (uid 501) and WSL2 behaviour of the derived image. No such host here.
- Whether any private submodule expects the devbox user to be 7111. Grep finds
  7111 only in renet's host-side universal user and account course content,
  neither of which reads this image, but renet's system tests were not run.
- arm64: the single `RUN` is arch-neutral but was not built there.
