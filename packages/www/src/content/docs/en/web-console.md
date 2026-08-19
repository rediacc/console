---
title: Web Console
description: Run the entire rdc CLI from your browser with forms, resource pickers, and run history
category: Guides
tags:
  - cli
  - account
order: 8
language: en
---

# Web Console

The web console is a browser UI over the entire `rdc` CLI. Every CLI command appears in the console with a form, validation, resource pickers, and a Run button. There is no separate "web feature set": the console is generated from the CLI contract, so any command the CLI has, the console has too, and new commands show up automatically.

It lives in the web portal at `/account/console`.

## Availability

The web console is a paid feature. It is included in paid plans and hidden on the Community plan. Access is also role-gated, so an organization admin can control who sees it.

## How it relates to config storage

The console reads your resources (machines, repositories, and so on) from your encrypted config store, and it decrypts that config in the browser only. That means:

- **While locked**, you can still browse the full command catalog, open any command's form, and read its parameters. This works without any setup.
- **To run commands and use pickers**, you unlock your config store first (passkey, master password, or recovery code, see [Config Storage](/en/docs/config-storage)). Run buttons, resource pages, and resource pickers all gate on the unlocked session.

The decrypted key stays in browser memory only. Refreshing the page locks the console again, and 30 minutes of inactivity auto-locks it.

## Resource pickers

Once unlocked, command forms replace free-text fields with pickers fed from your decrypted config: machines, repositories, datastores, storages, clusters, cloud providers, and backup strategies. Some pickers are resolved live instead, by running a command, for example containers on a machine or snapshots in a datastore.

Pickers filter dependently: pick a machine and the repository picker narrows to that machine. For repository references, a ref builder composes the full `name:tag@machine` form from individual picks. Pickers are hints, not constraints, and you can always type a value manually.

## Running commands

The browser never holds an SSH key or a machine address. When you click Run, the console sends only the command intent, which command and which parameters, and an executor resolves everything else and runs it. See [Proxy and Executor](/en/docs/proxy-and-executor) for how this works and which commands can run this way.

Commands that only edit your config (for example creating a machine entry) do not run remotely at all. The console routes them to the built-in config editor, where the change is encrypted and pushed like any other config edit.

Each form also shows the equivalent CLI command line, so anything you set up in the console can be copied straight into a terminal or a script.

## Finding your way around

- **Resource pages**: machines, repositories, and jobs each have list and detail pages, with the relevant commands attached as actions.
- **Command palette**: press Cmd-K (Ctrl-K) to jump to any command or resource by name.
- **Run history**: past runs are kept per session so you can review output and re-run with the same parameters.

## Related

- [Config Storage](/en/docs/config-storage), setting up and unlocking the encrypted config store
- [Proxy and Executor](/en/docs/proxy-and-executor), the execution model behind the Run button
