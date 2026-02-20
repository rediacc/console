---
title: "rdc vs renet"
description: "When to use rdc and when to use renet."
category: "Guides"
order: 1
language: en
---

# rdc vs renet

Rediacc uses two binaries:

- `rdc` is the user-facing CLI you run on your workstation.
- `renet` is the remote, low-level system binary that runs on servers.

For almost all day-to-day operations, use `rdc`.

## Mental Model

Think of `rdc` as the control plane and `renet` as the data plane.

`rdc`:
- Reads your local context and machine mappings
- Connects to servers over SSH
- Provisions/updates `renet` when needed
- Executes the right remote operation for you

`renet`:
- Runs with elevated privileges on the server
- Manages datastore, LUKS volumes, mounts, and isolated Docker daemons
- Performs low-level repository and system operations

## What to Use in Practice

### Use `rdc` (default)

Use `rdc` for normal workflows:

```bash
rdc context setup-machine server-1
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount
rdc repo down my-app -m server-1
rdc machine status server-1
```

### Use `renet` (advanced / remote-side)

Use direct `renet` only when you intentionally need low-level remote control, such as:

- Emergency debugging directly on the server
- Host-level maintenance and recovery
- Verifying internals not exposed by a higher-level `rdc` command

Most users should not need to invoke `renet` directly during routine operations.

## Rediaccfile Note

You may see `renet compose -- ...` inside a `Rediaccfile`. That is expected: Rediaccfile functions execute on the remote side where `renet` is available.

From your workstation, you still typically start/stop workloads with `rdc repo up` and `rdc repo down`.
