---
title: "Creating Your First Repository"
description: "Create an encrypted repository on your server and open it in VS Code."
category: "Tutorials"
subcategory: essentials
order: 4
language: en
---

# Creating Your First Repository

A Rediacc repository is a single encrypted file on your server. When mounted, it becomes a folder with its own Docker daemon and its own application data: completely isolated, completely portable.

Think of it like a USB drive for production: a file at rest, a server at run.

## Watch the tutorial

![Tutorial: Creating your first repository](/assets/tutorials/tutorial-create-repo.cast)

## File on disk, environment when mounted

![Encrypted file mounts as an isolated folder](/img/tutorials/tutorial-create-repo/slide-1.svg)

The on-disk form is a single encrypted image. When it mounts, you get:

- A dedicated Docker daemon (separate from the host's)
- Application data inside the encrypted volume
- Loopback IPs that don't collide with anything else on the box

Repositories are portable. You can move one between machines, back it up, or fork it instantly. Every repo is isolated from every other repo on the same server.

## Create one

```bash
time rdc repo create --name my-app -m my-server --size 2G
```

This creates a 2 GB encrypted repository on `my-server`. Verify it:

```bash
time rdc repo list -m my-server
```

## Open it in VS Code

```bash
rdc vscode connect -m my-server -r my-app
```

VS Code opens directly inside the repository. Notice the workspace is empty. This is your isolated environment. Everything you create here lives inside the encrypted volume, invisible to any other repo on the same server.

---

Next: [Deploying Your First App](/en/docs/tutorial-deploy-app).
