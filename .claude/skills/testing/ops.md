# Ops — VM provisioning, `ci-ops-test.yml`

For `rdc ops`, KVM/qemu provisioning, the base-image cache, eBPF socket
isolation, platform checks.

## THE LEAST PROTECTED SURFACE

Nothing enforces that an ops behaviour has a test. E2E has
`check-e2e-coverage.sh` in both directions; hooks have the orphan gate; ops has
neither. A regression here returns silently, so an ops fix deserves a case more
than any other surface, not less.

## Where the case goes

A step in `.github/workflows/ci-ops-test.yml`, inside one of:

- `ops-vm-provision` — the matrix job, real KVM, builds renet and the CLI first
- `ops-qemu-provision` — qemu path
- `ops-platform-check` — platform preconditions

Steps are named `"Test: <what>"`. They invoke the built CLI bundle with `node`
directly, because the job has already built it and `./rdc.sh` would rebuild.
That form is blocked in an interactive shell by a pre-bash hook; inside the
workflow it is correct. Locally, use `./rdc.sh` instead.

## Running it locally

`./rdc.sh ops up` (or `up --basic`) brings the fleet up; `ops status`, `ops down`.
The build-first trap: ops fails before touching a VM if renet or the CLI is not
built. See the `ops-vms` agent for the RAM/disk cost and which operations are
agent-blocked.

## Proof

- the step exists in the job that runs on this event, not in a job gated off
- the `ops-tests` job green on the PR head
- **plant it**: break the thing locally and watch the step fail before fixing
