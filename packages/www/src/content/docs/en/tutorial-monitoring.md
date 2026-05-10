---
title: "Monitoring"
description: "Check the health of your servers and repos from your laptop with rdc machine commands."
category: "Tutorials"
subcategory: advanced
order: 12
language: en
---

# Monitoring

Your app is deployed, live, and backed up. Now make sure everything stays healthy. `rdc` gives you a full picture of any server (health, containers, repos) from your laptop.

## Watch the tutorial

![Tutorial: Monitoring](/assets/tutorials/tutorial-monitoring.cast)

## Three things you can check

![Health, containers, repos](/img/tutorials/tutorial-monitoring/slide-1.svg)

## Health: system info

Start with the system view:

```bash
time rdc machine query --name my-server --system
```

This shows system uptime, disk usage, and storage status. If something is wrong, it tells you.

## Containers

To see all running containers across every repo on the machine:

```bash
time rdc machine query --name my-server --containers
```

You get name, status, health, CPU, and memory for each container, plus which repo owns it.

## Repos

To check your repositories:

```bash
time rdc machine query --name my-server --repositories
```

This shows every repo with its size, mount status, Docker status, and disk usage.

## Everything in one shot

```bash
time rdc machine query --name my-server
```

System info, repos, containers, all in one command. The same `query` command with no filters returns the full picture; with `--system`, `--containers`, `--repositories`, `--services`, `--network`, or `--block-devices` it narrows to just that section.

## Local sanity check

`rdc doctor` checks your local setup (Node, SSH key, `renet`, Docker), independent of any specific server:

```bash
time rdc doctor
```

## You're done

That's the full series. You can now install, configure, deploy, fork, go live, autostart, back up, and monitor. All from your terminal, all on your own servers.
