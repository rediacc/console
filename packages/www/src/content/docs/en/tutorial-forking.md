---
title: "Forking a Repository"
description: "Clone an entire repository (app, database, files) in seconds. Any size. Zero extra disk."
category: "Tutorials"
subcategory: advanced
order: 7
language: en
---

# Forking a Repository

This is the killer feature: clone an entire production environment (the app, the database, the config files) in seconds. Any size. Zero extra disk. Fork as many times as you want.

The tagline: **clone production, break nothing.**

## Watch the tutorial

![Tutorial: Forking a repository](/assets/tutorials/tutorial-forking.cast)

## Set up something to lose

First, give the running app a file so you can prove the fork's isolation. Open the repo in VS Code:

```bash
rdc vscode connect -m my-server -r my-app
```

Inside the repo, create a marker file:

```bash
time echo "Hello from production" > index.html
```

Now fork it.

## Fork

```bash
time rdc repo fork --parent my-app -m my-server --tag experiment --up
```

![Parent fans out into independent clones](/img/tutorials/tutorial-forking/slide-1.svg)

One command. It cloned everything (the app, the database, the config files) and it happened in seconds. Run it again and you get another independent clone.

## Why is it so fast?

![Sharing a folder link is the same speed regardless of the folder's size](/img/tutorials/tutorial-forking/slide-2.svg)

Imagine sharing a folder link. The link is the same whether the folder is small or huge. The folder is heavy, the link is light.

![1 GB, 100 GB, 1 TB. Same time, every time.](/img/tutorials/tutorial-forking/slide-3.svg)

Forking works the same way. 1 GB, 100 GB, 1 TB. Same time, every time.

## What's shared, what's yours

![Many mirrors, one sun: shared base, your changes are yours](/img/tutorials/tutorial-forking/slide-4.svg)

Think of the parent repo as the sun. You can't hold the sun, but you can hold a mirror that catches it. That mirror is your fork. Paint on the mirror, and your drawings are yours. The sun stays the same, no matter how many mirrors face it.

> You can't hold the sun, but you can hold it in a mirror.

## What if the parent changes later?

![A fork is a frozen photograph; the parent keeps flowing like a river](/img/tutorials/tutorial-forking/slide-5.svg)

Now think of a river. The water keeps flowing. Every moment, it's different. When you fork, you take a photograph of the river, frozen at that moment. The river keeps flowing. Your photograph doesn't.

If the parent repo changes later, your fork stays where it was.

> You can't hold a river, but you can hold it in a photo.

## Disk usage stays flat

![Five forks of a 100 GB repo, still about 100 GB total](/img/tutorials/tutorial-forking/slide-6.svg)

That's why your disk doesn't blow up. Five forks of a 100 GB repo? Still about 100 GB total. You only pay disk for what you change in each fork.

> Fork five times if you want. Your disk won't even notice.

## What forks do *not* inherit: secrets

There's one thing the fork deliberately doesn't follow: secrets. A fork starts with no API keys, no database passwords, no Stripe tokens. That's why "clone production, break nothing" actually works. Your sandbox can't bill real customers because it can't pretend to be you. We set this up properly in the [Managing Secrets](/en/docs/tutorial-managing-secrets) tutorial.

## Verify the isolation

List both repos side by side:

```bash
time rdc repo list -m my-server
```

You'll see `my-app` and `my-app:experiment` running concurrently.

In the original repo, check what's running:

```bash
time docker ps
```

Note the uptime. These are the original containers. Now switch to the fork:

```bash
rdc vscode connect -m my-server -r my-app:experiment
```

```bash
time docker ps
```

Same images, but the uptime is fresh. These started when the fork did.

Make the difference even more obvious. Add a container only to the fork:

```bash
time docker run --rm -it -d nginx
time docker ps
```

Nginx is running, but only inside this fork.

Try something destructive:

```bash
time rm index.html
```

Gone here. Now jump back to the original:

```bash
rdc vscode connect -m my-server -r my-app
time docker ps
```

No nginx. The fork's containers stayed in the fork. And `index.html` is still here, untouched. The original never knew anything happened. Same images, separate Docker daemons, separate filesystems.

## Clean up

When you're done, just delete the fork:

```bash
time rdc repo delete --name my-app:experiment -m my-server
```

The original stays exactly as it was. **Fork, experiment, break things, delete.** No risk.

---

Next: [Managing Secrets](/en/docs/tutorial-managing-secrets).
