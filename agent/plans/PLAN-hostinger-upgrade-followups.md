# PLAN: product follow-ups from the 2026-10-22/23 hostinger CVE response: Traefik v3.7.16, two template fixes, and the /run docker.sock isolation write-up

Status: in-progress
Owner: 5008cebe
First-Seen: 2026-10-23
Priority: P1 -- asked by the operator 2026-10-23. The production proxy image `traefik:v3.6` was built with go1.25.7 (before the CVE-2026-111943 crypto/x509 eMudhra denylist in go1.26.10/1.27.3), the v3.6 line no longer gets releases, and v3.7.16 (2026-10-20) also fixes GHSA-hrpp-p4fc-wwf8.
Concurrency: parallel
Owns: private/renet/proxy/docker-compose.yml, private/renet/scripts/ci-test.sh, .ci/config/constants.sh (DEVBOX_PROXY_IMAGE only), .ci/rediacc_ci/core/devbox.py (DEVBOX_PROXY_IMAGE only), docs/agent-reference/local-env.md (the traefik tag only), packages/json/templates/monitoring/heartbeat/docker-compose.yaml, packages/json/templates/platforms/nextcloud-aio/docker-compose.yaml, agent/plans/PLAN-renet-run-docker-sock-isolation.md (new)
Worklist: (the lead adds this with worklist.py --add)

## Context

During the hostinger upgrade (PHP php2shell, Node.js, GitLab CVE-2026-110264, NGINX, Go, eMudhra), every repo on the machine moved to pinned current versions. Three product-side gaps surfaced that belong in this repository rather than on the server:

1. The `rediacc-proxy` Traefik pin is `traefik:v3.6` (`private/renet/proxy/docker-compose.yml:21`). The compose file is embedded into renet at build time (`private/renet/build.sh` `embed_proxy` -> `pkg/embed/embed.go` `//go:embed proxy/*`) and written to `/opt/rediacc/proxy` by `rdc machine setup`, so a pin bump needs a renet build and a machine setup to roll out.
2. Two catalog templates are stale or broken:
   - `monitoring/heartbeat` runs `node:20-alpine`. Node 20 is end-of-life and will get no fix for the October 2026 Node.js CVEs.
   - `platforms/nextcloud-aio` binds `${DOCKER_HOST:-/var/run/docker.sock}`. Under renet, `DOCKER_HOST` carries a `unix://` prefix, so it is not a valid bind source, and `/var/run/docker.sock` does not exist inside the per-repo dockerd sandbox (an empty directory appears instead; this is what broke Alloy on hostinger). renet injects `DOCKER_SOCKET` (`private/renet/pkg/orchestration/up_down_workflows.go:224,360,479`), the pattern the Hub docs use.
3. An isolation gap, recorded for a proper fix: see `agent/plans/PLAN-renet-run-docker-sock-isolation.md`.

## Tasks

- [ ] T1 [lead] Traefik v3.6 -> v3.7.16:
  - `private/renet/proxy/docker-compose.yml:21` and `private/renet/scripts/ci-test.sh:333` (renet submodule commit);
  - `.ci/config/constants.sh:177`, `.ci/rediacc_ci/core/devbox.py:153`, `docs/agent-reference/local-env.md:26` (console commit).
  - Verify: the renet build embeds the new tag (`grep traefik: pkg/embed/proxy/docker-compose.yml` after `build.sh`), and the CI python tests that read `DEVBOX_PROXY_IMAGE` pass.
  - Roll out with `rdc machine setup hostinger` after the renet pointer lands, then check `docker inspect rediacc-proxy` and the hostinger endpoints.
- [ ] T2 [lead] Template fixes:
  - heartbeat `node:20-alpine` -> `node:24-alpine`;
  - nextcloud-aio `${DOCKER_HOST:-/var/run/docker.sock}` -> `${DOCKER_SOCKET}`.
  - Verify: `npm run build -w packages/json` (catalog generation) and the template lint/test gates exit 0.
- [ ] T3 [lead] Write `agent/plans/PLAN-renet-run-docker-sock-isolation.md` (write-up only, no fix; operator decision 2026-10-23).
