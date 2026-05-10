---
title: "Managing Secrets"
description: "Put deploy-time credentials in a place forks can't reach. Write-only by design."
category: "Tutorials"
subcategory: advanced
order: 8
language: en
---

# Managing Secrets

Real apps need real credentials: a Stripe live key, a database password, an API token. The wrong place to put them is in the repo, because a fork inherits whatever's inside the encrypted image. Suddenly your sandbox is charging real customer cards.

The right place is `rdc repo secret`. Two delivery modes, write-only by design, and the fork starts with nothing.

## Watch the tutorial

![Tutorial: Managing secrets](/assets/tutorials/tutorial-managing-secrets.cast)

## The trap: `.env` in the repo

![A .env file inside the repo image gets cloned by every fork](/img/tutorials/tutorial-managing-secrets/slide-1.svg)

Most teams put `.env` in the repo. It's the obvious move.

Then they fork.

The fork is a byte-for-byte copy of the parent's image. Whatever's in `.env` is in the fork's `.env`. The fork's containers boot. They read the same Stripe key. They call the same Stripe API with production credentials. From Stripe's side, that call is *you*.

That's a bad day.

## Set a secret

The fix is `rdc repo secret`. Set one in `env` mode. It lands as an environment variable in the container:

```bash
time rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
```

Two things to notice:

- `--mode env`. The value lands as an environment variable.
- `--current ""`. Empty string. We're declaring this is a brand-new secret with no prior value.

Set another, in `file` mode, for anything sensitive:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

`file` mode never puts the value in the container's environment. It writes it to `/run/secrets/stripe_key` instead, using Docker's standard mechanism.

List what you have:

```bash
time rdc repo secret list --name my-app
```

You see names and modes. **No values.** The list never shows values.

## Wire it into compose

Open `docker-compose.yml`. Reference both modes:

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

`${REDIACC_SECRET_DB_HOST}` is `env` mode: `renet`'s compose wrapper expands it from your secret store at deploy time.

The `secrets:` block is `file` mode, using Docker's standard mechanism. The host path uses `${REDIACC_NETWORK_ID}` so the same compose works for parents and forks. Each fork has its own network ID.

Deploy:

```bash
time rdc repo up --name my-app -m my-server
```

## Verify in the container

Both modes should be inside the container now. Check the env-mode secret:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
```

`postgres.internal`. The env-mode secret reached the container's environment.

Now the file-mode one:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
```

`sk_test_xxx`. The file is mounted via Docker's standard secrets mechanism.

## You can never read it back

![Write-only model: get returns a digest, never the value](/img/tutorials/tutorial-managing-secrets/slide-2.svg)

Now the part that surprises people:

```bash
time rdc repo secret get --name my-app --key STRIPE_KEY
```

You get a digest. **Not the value.** There's no flag that makes it return the value. There's no command anywhere that will give you the plaintext back.

That's the GitHub Actions model: write-only. You can prove you know what a secret is by passing `--current <value>` and watching the precondition pass. You can't ask Rediacc to tell you what it is.

Lost the value? **Don't peek. Rotate.**

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --rotate-secret
```

`--rotate-secret` skips the precondition. The audit log marks it as a rotation: loud, deliberate.

If you do remember the old value, prove it instead:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --current sk_test_xxx
```

That's the safer path. It catches the "I'm in the wrong terminal" mistake.

## The fork punchline

![After fork, the secrets list is empty](/img/tutorials/tutorial-managing-secrets/slide-3.svg)

Remember the trap? Fork the repo and look:

```bash
time rdc repo fork --parent my-app --tag test -m my-server
time rdc repo secret list --name my-app:test
```

**Empty.**

The fork has no Stripe key. No database password. No API token. Containers in the fork can't interpolate `${REDIACC_SECRET_STRIPE_KEY}`. The file at `/var/run/rediacc/secrets/<fork-id>/STRIPE_KEY` doesn't exist.

The fork can't pretend to be you.

If you want secrets in the fork for testing, set them on the fork explicitly with sandbox values:

```bash
time rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

Now the fork talks to the Stripe sandbox. Production credentials never left production.

## Summary

- `rdc repo secret` puts your credentials outside the repo image.
- The fork can't reach them.
- `get` returns a digest, never the value.
- Rotate when you forget. Don't peek.

Secrets the fork can't follow.

---

Next: [Networking & Domains](/en/docs/tutorial-networking).
