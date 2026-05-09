---
title: "Deploying Your First App"
description: "Deploy a containerized app from a built-in template using renet dev up."
category: "Tutorials"
subcategory: essentials
order: 5
language: en
---

# Deploying Your First App

You have an empty repository. `rdc` ships built-in templates so you can spin up real apps without writing a `docker-compose` from scratch. Three steps: pick a template, apply it, run it.

## Watch the tutorial

![Tutorial: Deploying your first app](/assets/tutorials/tutorial-deploy-app.cast)

## Pick · Apply · Run

![Pick a template, apply it, run it](/img/tutorials/tutorial-deploy-app/slide-1.svg)

## Step 1: Pick

Browse the available templates:

```bash
time rdc repo template list
```

You'll see ready-made setups for common apps: Postgres, Redis, web servers, and more.

## Step 2: Apply

Drop the template into your repo. We'll use `app-postgres`:

```bash
time rdc repo template apply --name app-postgres -m my-server -r my-app
```

Two new files appear in the repo: `docker-compose.yml` and `Rediaccfile`. The compose file describes the containers; the `Rediaccfile` defines what happens when the app starts and stops (its `up` and `down` lifecycle hooks).

## Step 3: Run

You're already inside the repo's sandbox (via the VS Code connection from the previous tutorial), so use `renet` directly:

```bash
time renet dev up
```

That's it. Your app is running. Verify it:

```bash
time docker ps
```

`docker ps` here lists only this repo's containers. Other repos on the same server have their own Docker daemons and are completely invisible from this one.

---

Next: [Working with Your Repo](/en/docs/tutorial-work-with-repo).
