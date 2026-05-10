---
title: "Working with Your Repo"
description: "Tunnel a port to your browser, run commands inside the sandbox, and sync files between your laptop and the repo."
category: "Tutorials"
subcategory: essentials
order: 6
language: en
---

# Working with Your Repo

Your app is running, but so far you've only seen it through `docker ps`. Three commands cover the daily workflow: **tunnel** to see the app in a browser, **term** to run commands inside the sandbox, **sync** to move files between your laptop and the repo.

## Watch the tutorial

![Tutorial: Working with your repo](/assets/tutorials/tutorial-work-with-repo.cast)

## The daily three

![Tunnel, term, sync](/img/tutorials/tutorial-work-with-repo/slide-1.svg)

1. **Tunnel**: open your app in a browser.
2. **Term**: run a command inside the sandbox.
3. **Sync**: move files in and out.

## Tunnel: see your app in a browser

The app runs on the server, not your laptop. Forward a container's port over SSH:

```bash
rdc repo tunnel -m my-server -r my-app -c app
```

Open `localhost` in your browser. Your app is right there. Press `Ctrl+C` when you're done.

For a different container, swap `-c` and pick the port:

```bash
rdc repo tunnel -m my-server -r my-app -c db --port 5432
```

## Term: run commands inside the repo

Skip VS Code when you just need a shell:

```bash
rdc term connect -m my-server -r my-app
```

You're now inside the repo's sandbox. Try it:

```bash
time docker ps
```

You see only `my-app`'s containers, the same view you'd see in VS Code.

For one-off commands, use `-c` and skip the interactive shell:

```bash
time rdc term connect -m my-server -r my-app -c "df -h ."
```

## Sync: move files between laptop and repo

Push a folder from your laptop into the repo:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src
```

Pull files back:

```bash
time rdc repo sync download -m my-server -r my-app --local ./backup
```

Preview first if you're unsure. `--dry-run` shows what would change without actually copying:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src --dry-run
```

Tunnel, term, sync. Three commands cover the daily loop.

---

Next: [Forking a Repository](/en/docs/tutorial-forking).
