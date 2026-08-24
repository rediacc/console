# Install and update — `ct-install-methods.yml`

For the install script, the linux packages, the SEA binary, auto-update, and
`rdc.sh`'s own environment resolution.

## Where the case goes

`.ci/scripts/test/` — the scripts are already there and the workflow calls them:

| what changed | script |
|---|---|
| install.sh, any install path | `test-install-methods.sh`, `test-install-script.sh` |
| the config `install.sh` writes | `test-install-sh-config.sh` |
| deb/rpm packaging | `test-linux-packages.sh` |
| `./rdc.sh` flags and env (`--dev`, `--native`, `--config`) | `test-rdc-sh-env.sh` |
| the updater, channel resolution, binary swap | `test-rdc-update.sh` |

Add a case to the script that already owns that surface. A new script needs the
workflow step too, or it joins the orphans.

## The thing this surface exists to catch

Install validation runs **pre-publish**, against R2 staging artifacts, on six
platforms. It is the last point where a broken artifact is still cheap. A fix to
packaging that is only unit-tested has not been tested at all: the failure is
always in the interaction with a real package manager on a real distro.

## Proof

- the case runs inside a script the workflow calls, not a new orphan
- `validate-install` green on the PR head
- **plant it**: corrupt the artifact the way the bug did and require a red

## Local

The scripts run standalone. `test-rdc-sh-env.sh` needs no VM and is the fast one;
the package tests want a container per distro.
