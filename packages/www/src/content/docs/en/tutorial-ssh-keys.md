---
title: "SSH Key Configuration"
description: "Configure your SSH key so rdc can connect to your servers without passwords."
category: "Tutorials"
subcategory: essentials
order: 2
language: en
---

# SSH Key Configuration

`rdc` connects to your servers over SSH, so each server needs to trust your SSH key. Three steps total. Two are one-time setup, and one repeats for every new server you add.

## Watch the tutorial

![Tutorial: SSH key configuration](/assets/tutorials/tutorial-ssh-keys.cast)

## The three steps

![Generate, copy, register](/img/tutorials/tutorial-ssh-keys/slide-1.svg)

1. **Generate** an SSH key on your laptop. Once, ever.
2. **Copy** it to your server. Repeat for every new server.
3. **Register** the key with `rdc`. Once, ever.

## Step 1: Generate a key

If you already have a key you want to use, skip ahead. Otherwise:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

`ed25519` is the modern default: small, fast, and well-supported.

## Step 2: Copy it to your server

```bash
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip
```

Replace `user` and `your-server-ip` with the SSH user and IP of your server. You'll be prompted for your server password one last time. After this, password authentication is no longer required.

## Step 3: Register the key with `rdc`

```bash
time rdc config ssh set --key ~/.ssh/id_ed25519
```

That's it. From here on, every `rdc` command authenticates with this key. No more passwords, no more interactive prompts.

---

Next: [Adding Your First Server](/en/docs/tutorial-add-server).
