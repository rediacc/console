---
title: "Managing Secrets"
description: "Set per-repo secrets, wire them into compose, verify they reach the container, rotate them, and confirm forks inherit none."
category: "Tutorials"
order: 7
language: en
---

# How To Manage Per-Repo Secrets with Rediacc

Real applications need credentials: a Stripe live key, a database password, an API token. The wrong place to put them is inside the repository. A fork inherits whatever lives in the encrypted image, and the fork's containers boot identifying themselves as the parent against external services. The right place is `rdc repo secret`. Values land outside the encrypted image, so forks start with an empty secrets map.

In this tutorial you set both modes of secret, wire them into a compose file, verify they reach the container, rotate one, and confirm a fork inherits nothing.

## Prerequisites

- The `rdc` CLI installed with a config initialized
- A provisioned machine and a created repository (see [Tutorial: Repository Lifecycle](/en/docs/tutorial-repos))
- A `Rediaccfile` and `docker-compose.yml` you can edit

## Step 1: Set a secret

Two delivery modes are available. `env` exports the value as `REDIACC_SECRET_<KEY>` for compose `${...}` interpolation. `file` writes the value to a host-side tmpfs file at `/var/run/rediacc/secrets/<networkID>/<KEY>` for use with Docker compose's `secrets:` block. Use `file` for anything sensitive. Values in env-mode show up in `docker inspect` and `/proc/<pid>/environ`.

For first-write of a brand-new key, pass `--current ""` (empty) to acknowledge there's no previous value.

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

## Step 2: List what's there

```bash
rdc repo secret list --name my-app
```

The output is JSON with each secret's name and mode. Values never appear in the listing. They're not even fetched from disk.

```json
{
  "repository": "my-app:latest",
  "secrets": [
    { "key": "DB_HOST", "mode": "env" },
    { "key": "STRIPE_KEY", "mode": "file" }
  ]
}
```

## Step 3: Wire into compose

Both modes get referenced from the same `docker-compose.yml`:

```yaml
services:
  api:
    image: myapp:latest
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_key

secrets:
  stripe_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_KEY
```

The lowercase `stripe_key` on the service is the in-container `/run/secrets/<name>` filename. The uppercase `STRIPE_KEY` in the host path matches the `--key` you set. `${REDIACC_NETWORK_ID}` is interpolated by `renet compose` automatically. That's important because the network ID is per-fork, so the same compose file works in the parent and in any fork (where, as you'll see in step 6, the file simply won't exist).

> **Cross-repo isolation enforced.** renet's compose validator rejects any `secrets: file:` (or `configs: file:`, or `env_file:`) path that targets another repo's network ID. The literal `${REDIACC_NETWORK_ID}` token (or your own network's int) is the only accepted form, and `--unsafe` does NOT override it. The Landlock sandbox around the Rediaccfile bash subprocess also scopes filesystem reads to your own network's secrets directory. So even a malicious `cat /var/run/rediacc/secrets/<other>/X` from a Rediaccfile fails with EACCES at the kernel layer. You don't need to do anything to opt in; the protection is on by default.

## Step 4: Deploy and verify

```bash
rdc repo up --name my-app -m server-1
```

After the deploy, exec into the container to confirm both modes landed:

```bash
# env-mode reaches the container's environment
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
# → postgres.internal

# file-mode reaches /run/secrets/ inside the container
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
# → sk_test_xxx
```

If you want to inspect the host-side tmpfs file directly:

```bash
rdc term connect -m server-1 -c 'sudo ls -la /var/run/rediacc/secrets/<networkID>/'
# → -r--r--r-- 1 root root 11 May  4 12:01 STRIPE_KEY
# parent dir is mode 0700 root:root; per-file mode 0444. The dir is the security gate.
```

## Step 5: Rotate without knowing the prior value

You can read a digest with `rdc repo secret get`, but never the plaintext value. That's the write-only model. If you need to verify a stored value matches what you have, pass it via `--current` and watch the precondition pass or fail:

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --current postgres.internal
```

If you've forgotten the prior value entirely (your password manager lost it, or you inherited the repo), use `--rotate-secret` to skip the precondition. The audit log records this loudly as a rotation:

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --rotate-secret
```

`--current` and `--rotate-secret` are mutually exclusive. Pick one.

## Step 6: Confirm forks inherit nothing

The whole point: fork the repo and check the fork's secrets list:

```bash
rdc repo fork --parent my-app --tag test -m server-1
rdc repo secret list --name my-app:test
```

```json
{
  "repository": "my-app:test",
  "secrets": []
}
```

Empty. The fork's containers cannot interpolate `${REDIACC_SECRET_DB_HOST}` (the variable is unset → empty string), and the file at `/var/run/rediacc/secrets/<fork-networkID>/STRIPE_KEY` simply doesn't exist. If the fork's `repo up` tries to mount it via the compose `secrets:` block, the deploy will fail with a clear error. Exactly the failure mode you want, because it means the sandbox cannot pretend to be production against external services.

To use secrets in the fork, set them on the fork explicitly with sandbox-scoped values:

```bash
rdc repo secret set --name my-app:test --key DB_HOST --value postgres-test.internal --mode env --current ""
rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

Now the fork talks to a test database and a Stripe sandbox account. The parent's production credentials never leave the parent.

## Cleanup

```bash
rdc repo secret unset --name my-app --key STRIPE_KEY --current sk_test_xxx
rdc repo delete --name my-app:test -m server-1
```

## See also

- [Repositories § Secrets](/en/docs/repositories#secrets). The full reference
- [RDC CLI Cheat Sheet § Per-repo Secrets](/en/docs/rdc-cheat-sheet#per-repo-secrets). Command quick-reference
- [AI Agent Safety](/en/docs/ai-agents-safety). The symmetric mutation gate and structured `next` action hints in error envelopes
- [Services § Using per-repo secrets in compose](/en/docs/services#using-per-repo-secrets-in-compose). Compose pattern reference
