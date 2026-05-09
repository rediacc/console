---
title: "Adding Your First Server"
description: "Register your first server with rdc, provision it, and understand the rdc + renet architecture."
category: "Tutorials"
subcategory: essentials
order: 3
language: en
---

# Adding Your First Server

Before adding a server, it helps to understand how `rdc` works. Rediacc has a two-tool architecture: `rdc` on your laptop, `renet` on the server.

## Watch the tutorial

![Tutorial: Adding your first server](/assets/tutorials/tutorial-add-server.cast)

## Why two tools?

![rdc on laptop, renet on server, SSH between](/img/tutorials/tutorial-add-server/slide-1.svg)

- **`rdc`** is the CLI on your laptop. You type commands here.
- **`renet`** is the orchestrator on the server. It manages encryption, Docker, and isolation.

When you run a command locally, `rdc` connects over SSH and executes `renet` on the server. You never SSH into your servers manually. `rdc` does it for you.

## Step 1: Register the server

Tell `rdc` about the server. Replace the name, IP, and user with your own.

```bash
time rdc config machine add --name my-server --ip 192.168.1.100 --user deploy
```

## Step 2: Provision it

Setup installs `renet` and creates the encrypted datastore on the server.

```bash
time rdc config machine setup --name my-server
```

When it completes, your server is ready to host repositories.

## Where the config lives

Verify what `rdc` knows about your setup:

```bash
time rdc config show
```

Or open the raw JSON file directly:

```bash
vim ~/.config/rediacc/rediacc.json
```

This single file holds everything: machines, repos, SSH key, encryption credentials. Copy it to another laptop and you're ready to go from that machine too.

---

Next: [Creating Your First Repository](/en/docs/tutorial-create-repo).
