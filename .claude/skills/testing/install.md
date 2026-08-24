# Install, update and `rdc.sh` env

For the install script, the linux packages, the SEA binary, auto-update, and
`rdc.sh`'s own environment resolution.

## FOUR different jobs, not one

This was wrong here until 2026-08-24 and it would have sent you to watch a job
that never moves. There is no single "install workflow": each script has its own
home, and the job you watch depends on which script you touched.

| what changed | script in `.ci/scripts/test/` | job to watch |
|---|---|---|
| install.sh across the platform matrix | `test-install-methods.sh` | `validate-install` (`ci.yml:1270`) |
| install.sh itself | `test-install-script.sh` | `quality-static` (`ci-quality.yml:331`) |
| the config install.sh writes | `test-install-sh-config.sh` | `quality-static` (`ci-quality.yml:338`) |
| `./rdc.sh` flags and env (`--dev`, `--native`, `--config`) | `test-rdc-sh-env.sh` | `quality-static` (`ci-quality.yml:345`) |
| deb/rpm packaging | `test-linux-packages.sh` | `package-tests` (`ci.yml:753`) |
| the updater, channels, binary swap | `test-rdc-update.sh` | `update-flow-test` (`ct-update-flow.yml:63`) |

Add a case to the script that already owns that surface. A NEW script needs its
workflow step too, or it joins the orphans.

## The thing this surface exists to catch

Install validation runs **pre-publish**, against R2 staging artifacts, on six
platforms. It is the last point where a broken artifact is still cheap. A fix to
packaging that is only unit-tested has not been tested at all: the failure is
always in the interaction with a real package manager on a real distro.

## Proof

- the case runs inside a script the table above names, not a new orphan
- **that script's own job** green on the PR head, from the table
- **plant it**: corrupt the artifact the way the bug did and require a red

## Local

All six run standalone. `test-rdc-sh-env.sh` needs no VM and is the fast one;
the package tests want a container per distro.
