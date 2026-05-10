---
title: "Production Mode"
description: "Run your app detached from your laptop and survive server reboots with autostart."
category: "Tutorials"
subcategory: advanced
order: 10
language: en
---

# Production Mode

So far you've been running the app with `renet dev up` from inside the repo. That's great for development. For production, you manage everything from your laptop with `rdc`. Close your laptop and the app keeps running.

## Watch the tutorial

![Tutorial: Production mode](/assets/tutorials/tutorial-production-mode.cast)

## Dev vs prod

The difference is simple:

- `renet dev up` runs **inside the repo**. You need to be connected.
- `rdc repo up` runs **from your laptop**. No connection needed after that.

Three actions take you from dev to prod:

![Stop, start, autostart](/img/tutorials/tutorial-production-mode/slide-1.svg)

## Step 1: Stop the dev session

Connect to the repo and bring it down:

```bash
rdc vscode connect -m my-server -r my-app
time renet dev down
```

## Step 2: Start in production mode

From your laptop's terminal:

```bash
time rdc repo up --name my-app -m my-server
```

That's it. Your app is running, and you can close your laptop. The `Rediaccfile` handles everything. `rdc repo up` calls the same `up` function `renet dev up` did. Same `Rediaccfile`, different way to invoke it.

## Step 3: Survive server reboots

Make sure your app comes back automatically when the server restarts:

```bash
time rdc repo autostart enable --name my-app -m my-server
```

Verify which repos have autostart enabled:

```bash
time rdc repo autostart list -m my-server
```

## Stopping in production

When you need to stop your app:

```bash
time rdc repo down --name my-app -m my-server
```

One command up, one command down. All from your laptop.

---

Next: [Backup & Restore](/en/docs/tutorial-backup-restore).
