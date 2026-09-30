# PLAN: every npm install -g honours the release-age window
Status: done
Owner: d778be9d
Updated: 2026-09-30
Depends-On: no-dep -- rediacc_ci.core.release_age and .ci/config/release-age.json exist
Priority: P1 -- a live supply-chain gap; CI installed a three-minute-old package
Concurrency: parallel -- disjoint from the in-flight writers' files
Owns: .ci/rediacc_ci/core/release_age.py, .ci/rediacc_ci/setup/install_cli_global.py, .ci/rediacc_ci/security/audit.py, .ci/rediacc_ci/quality/lockfile.py, .github/actions/setup-node-npm/action.yml, .github/workflows/ct-tests.yml, .github/workflows/cd-deploy-account.yml, .github/workflows/ci-quality.yml, Dockerfile, workers/proxy/Dockerfile, .devcontainer/Dockerfile, .ci/docker/web/Dockerfile, .ci/scripts/test/test-install-methods.sh

## 1. Problem, measured
- `npm install -g <spec>` resolves every transitive dependency fresh from the registry. The lockfile does not apply, and npm does not enforce `minimum_release_age_minutes` (.ci/config/release-age.json says so itself).
- PR #591 run 36724524175: E2E probe jobs 109920400852, 109920400971 and 109920400956 died in "Install CLI Globally" (`.ci/rediacc_ci/setup/install_cli_global.py:200`) with `npm error 404 ... source-map-js-1.2.2.tgz`. source-map-js 1.2.2 was published 2026-09-30T14:08:09Z; the jobs fetched at 14:11. package-lock.json pins 1.2.1. The 404 was CDN lag; the exposure is that a working CDN would have installed it.
- Sites: install_cli_global.py:200; ct-tests.yml:179 and cd-deploy-account.yml:262 (wrangler); ci-quality.yml:1711 (agent-browser); .github/actions/setup-node-npm/action.yml:37 and security/audit.py:1159 (npm itself); Dockerfile:52, workers/proxy/Dockerfile:19, .devcontainer/Dockerfile:313, :481, :647, .ci/docker/web/Dockerfile:46; .ci/scripts/test/test-install-methods.sh.

## 2. Design
- `release_age.npm_before(now=None)`: ISO-8601 UTC of now minus the window, and a CLI verb `npm-before` printing it. One implementation; every site asks it.
- Python and workflow sites pass `--before "$(PYTHONPATH=.ci python3 -m rediacc_ci.core.release_age npm-before)"` (Python sites call the function).
- Dockerfiles take `ARG NPM_BEFORE` and pass `--before "${NPM_BEFORE}"`; an empty ARG fails the RUN loudly (`: "${NPM_BEFORE:?...}"`), never installs unwindowed. Every build site that builds these images passes the build-arg from the same verb (grep the workflows and scripts for each Dockerfile's build).
- A pinned exact version newer than the cutoff then fails with ETARGET, which is correct: the pin freshness gates already require pins older than the window.
- Gate: `check:ci-lockfile` (.ci/rediacc_ci/quality/lockfile.py already tokenizes `npm install -g` at :358) gains a property: every `npm install -g` / `npm i -g` in workflows, composite actions, Dockerfiles and .ci scripts carries `--before`. A finding names file:line.

## 3. Tests, each with a control
- release_age: npm_before at a fixed now equals now - window, ISO with Z; CONTROL a window override moves it.
- install_cli_global: the npm argv carries --before and the computed value (fake npm records argv); CONTROL without the flag the new assertion fails.
- lockfile property: a planted `npm install -g foo@1` line in a fixture workflow and Dockerfile fires; the same line with `--before "$X"` is silent; the existing property-D fixtures still pass.
- A live check: `npm install -g <tarball> --before <cutoff>` in a scratch prefix resolves source-map-js 1.2.1, not 1.2.2.

## Tasks
- [x] T1 release_age.npm_before + CLI verb + tests
    (ticked) 2026-09-30T15:16:56Z by d778be9d: verified by commit b5eb1c5ae: npm_before returns UTC midnight minus the window and the npm-before verb prints it; tests pin same-day stability and the day step
- [x] T2 Python and workflow sites (install_cli_global, audit, setup-node-npm, ct-tests, cd-deploy-account, ci-quality) + tests
    (ticked) 2026-09-30T15:16:57Z by d778be9d: verified by commit b5eb1c5ae: install_cli_global and the wrangler, agent-browser and install-methods sites pass --before; npm self-installs are exempt because npm bundles its 65 dependencies
- [x] T3 Dockerfile ARG NPM_BEFORE at every global install and every build site passing it
    (ticked) 2026-09-30T15:17:21Z by d778be9d: verified by commit b5eb1c5ae: the devcontainer and web Dockerfiles take ARG NPM_BEFORE and refuse an empty value; ci-build-docker, devbox and run_in_image pass it
- [x] T4 check:ci-lockfile property: every global install carries --before, with fixtures both ways
    (ticked) 2026-09-30T15:16:58Z by d778be9d: verified by commit b5eb1c5ae: property E refuses a global install without --before outside the npm self-install exemption; 60 selftest controls and three live mutants
