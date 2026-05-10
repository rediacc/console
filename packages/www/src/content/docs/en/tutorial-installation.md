---
title: "Installation"
description: "Install the rdc CLI on your laptop with a single command and verify it with rdc doctor."
category: "Tutorials"
subcategory: essentials
order: 1
language: en
---

# Installation

Installing `rdc` is three steps: open the install page, pick your operating system, paste the command into your terminal. The whole thing usually finishes in a minute or two.

## Watch the tutorial

![Tutorial: Installation](/assets/tutorials/tutorial-installation.cast)

## The three steps

![Three steps overview](/img/tutorials/tutorial-installation/slide-1.svg)

1. Open the [installation page](/en/install).
2. Pick your operating system.
3. Copy the install command and paste it into your terminal.

## Install on your platform

The installation page generates the right command for you, but here are the canonical one-liners.

**Linux / macOS:**

```bash
time curl -fsSL https://www.rediacc.com/install.sh | bash
```

**Windows (PowerShell):**

```powershell
iwr -useb https://www.rediacc.com/install.ps1 | iex
```

> The `time` prefix is a shell trick that prints how long a command took. We use it across this series so you can see the real speed of every step. It's optional. Drop it if you don't want it.

## Verify the install

Once the script finishes, check that everything `rdc` needs is present:

```bash
time rdc doctor
```

`rdc doctor` walks through Node, SSH, and the rest of `rdc`'s dependencies and reports any gaps.

## Why `rdc` lives on your laptop

![rdc on your laptop, renet on the server](/img/tutorials/tutorial-installation/slide-2.svg)

`rdc` is the CLI on your laptop. The server runs a separate component called `renet`, which `rdc` provisions and drives over SSH. You never need to SSH into a server manually. `rdc` does it for you.

We'll set that up properly in the next two tutorials.

---

Next: [SSH Key Configuration](/en/docs/tutorial-ssh-keys).
