# CLI reference for agents

What used to live inline in CLAUDE.md under `## CLI (`packages/cli/`)`: the everyday `rdc` invocations and the shape of `packages/cli/src/`. It moved here to keep CLAUDE.md inside its size budget (`agent/PLAN-tooling-transformation.md`, box W11 P5b); the machine-readable truth is `packages/cli/scripts/command-tree.json` and `rdc --help`, and this file only carries the examples that
are worth reading before guessing.

## Common commands

The thing a command acts on is a **positional ref**, not a `--name` flag. A repo ref is `name`, `name:tag` for a fork, and optionally `name@machine` to assert placement. The machine is derived from the ref, so `-m/--machine` is gone from most repo commands (it survives where there is nothing to derive from, e.g. `repo create`, or as a batch filter, e.g. `repo up --all -m
<machine>`).

```bash
# Full machine status (SSH + renet list all)
rdc machine status <machine>

# Filter by section: --system --containers --services --repositories --network --block-devices
rdc machine status <machine> --containers

# SSH terminal: one positional target, a machine name or a repo ref
# (a repo ref sets DOCKER_HOST and the working dir); -c runs one command
rdc term connect <machine>
rdc term connect <repo>
rdc term connect <machine> -c "command"

# Deploy/update a repository (machine derived from the ref)
rdc repo up <repo>

# File sync: a directory, or one file with --remote-file
rdc repo sync upload <repo> --local ./local-path
rdc repo sync download <repo> --local ./out --remote-file etc/config.toml

# Container logs / exec
rdc repo logs <repo> -c <container> --lines 50
rdc repo exec <repo> -c <container> -- <command>

# VS Code remote (one positional target, like term)
rdc vscode connect <repo>
```

## CLI code structure

`packages/cli/src/` splits four ways, and the split is the thing to know rather than the file list, which `ls` derives and a pasted tree does not:

- `commands/` hand-registered Commander subtrees, one file or directory per command
- `remote/` SSH, SFTP, rsync, terminal, VS Code server modules (this was `shared-desktop/`)
- `services/` business logic grouped by domain, concrete modules with no barrels: `account/`,
`backup/`, `config/`, `core/`, `executor/`, `machine/`, `provision/`, `renet/`, `repo/`, `telemetry/`, `update/`, `tofu/` (the OpenTofu cloud-VM provisioning engine, reached from `commands/machine/provision.ts`), plus `state.ts` for `getStateProvider()`
- `utils/` cross-command helpers (command policy, agent guard, config schema, errors, platform, repo classify/target/executor)

Unit tests are central under `services/__tests__/`, mirroring `commands/__tests__/`.
