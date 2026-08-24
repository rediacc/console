# Ops — VM provisioning

For `rdc ops`, KVM/qemu provisioning, the base-image cache, eBPF socket
isolation, platform checks.

## Two places, and they are not interchangeable

- **`.github/workflows/ci-ops-test.yml`** — `ops-vm-provision` (matrix, real
  KVM), `ops-qemu-provision`, `ops-platform-check`. Steps named `"Test: <what>"`,
  invoking the built CLI bundle directly because the job has already built it.
  This is where a PROVISIONING behaviour is asserted: does the fleet come up,
  is the image cache honoured, does eBPF isolation hold.
- **The E2E suites (Tests + Infra)** — the same VMs, exercised by
  `packages/e2e-tests/tests/`. Anything that happens ON a provisioned machine is
  covered here, not in the ops workflow, and `check-e2e-coverage.sh` enforces it
  in both directions. See [e2e.md](e2e.md).

So the routing question is narrow: **did provisioning break, or did something on
the machine break?** The first is an ops step; the second is an E2E case, and
the E2E surface is the one with a coverage gate behind it.

## Running it locally

`./rdc.sh ops up` (or `up --basic`) brings the fleet up; `ops status`, `ops down`.
The build-first trap: ops fails before touching a VM if renet or the CLI is not
built. See the `ops-vms` agent for the RAM/disk cost and which operations are
agent-blocked.

## Proof

- the step exists in the job that runs on this event, not in a job gated off
- the `ops-tests` job green on the PR head, or the E2E job if the case landed
  there instead
- **plant it**: break the thing locally and watch the step fail before fixing
