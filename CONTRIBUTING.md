# Contributing

## New machine

```bash
git clone https://github.com/rediacc/console.git && cd console
./run.sh setup
```

`setup` installs Docker (official repo, not `docker.io`), pulls the devcontainer
image, and starts a browser VS Code for this checkout. It is idempotent — run it
again any time. `./run.sh setup --check` reports what is missing and changes
nothing.

Four things `setup` cannot do for you:

| One-time | Command | Why |
|---|---|---|
| Git identity | `git config --global user.name "…"` and `user.email "…"` | Commits fail without it, and the error names neither |
| GitHub auth | `gh auth login` — the token needs `repo`, `workflow`, `read:org`, `read:packages` | `read:packages` is what lets the devcontainer image *pull* instead of building locally (~35 min) |
| ~~Docker group~~ | nothing — handled | `setup` adds you to the `docker` group and re-execs itself under `sg` so it applies immediately; new login shells get it anyway |
| Submodules | `.devcontainer/init-submodules.sh` | Run by `setup`; re-run it alone if a submodule was added |

## Daily

```bash
./run.sh devbox status      # the URLs for this worktree
./run.sh devbox shell       # a shell inside it
./run.sh account dev        # gateway + portal + www; prints fresh credentials
./run.sh account db         # browse the dev database (sqlite-web; --studio for Drizzle)
./run.sh dev                # www marketing site only
```

Everything is reached through one port via hostnames named after the worktree:

| URL | Service |
|---|---|
| `http://<worktree>.localhost:8090` | VS Code |
| `http://<worktree>-account.localhost:8090` | the app (after `account dev`): marketing at `/`, portal at `/account/`, API at `/account/api/` |
| `http://<worktree>-db.localhost:8090` | database browser (after `account db`) |

**On ChromeOS forward exactly one port — 8090 — in Settings → Linux → Port
forwarding.** Chrome resolves `*.localhost` itself, so that single forward covers
every worktree and every service. `./run.sh devbox proxy status` checks the proxy.

Work **inside the devbox**. It carries the pinned toolchain (Node 22, Go, Playwright
deps); the host does not. `node_modules` is not shared between the two — the glibc
versions differ and native modules are built against whichever side installed them.

## Worktrees

Each worktree gets its own container and its own stable port block, derived from its
path. Ask the operator to create one (`git worktree add` is hook-blocked for agents),
then run `./run.sh setup` inside it.

## Before you push

```bash
npm run ci        # what CI runs
```

Use **npm 10**, which is what CI pins. On npm 11 the workspace install resolves the
wrong `zod` and `packages/shared` fails to compile; `ensure_deps` now falls back to
`npx -y npm@10` automatically, but a hand-run `npm install` will not.

`npm install` never runs dependency scripts (`.npmrc` sets `ignore-scripts`), so
follow it with `npm run install:natives`.

## Gotchas that cost real time

- **`./run.sh account reset` deletes `private/account/account.db`.** Anything you were
  reading in Studio is gone.
- **`tsx` does not hot-reload.** Restart `account dev` after editing
  `private/account/src`, and re-read the credentials it prints — they are random per
  start.
- **Ports are never hardcoded.** Read them from the startup output, `.account-state`,
  or `./run.sh devbox status`.
- **On ChromeOS**, the browser lives outside the Linux VM. The proxy hostnames
  above are the ONLY way in — devbox containers publish no ports of their own.
- **A 502 means "nothing is listening behind that route yet"**, not that the proxy
  is broken. `./run.sh devbox status` probes each route and says which. The usual
  cause is running `account dev` on the host instead of inside the devbox.

## Conventions

- Version comes from git tags; `package.json` files stay at `0.0.0-dev`.
- English is the source of truth for i18n; read `docs/i18n/CONVENTIONS.md` before
  touching any translation.
- Never suppress a quality gate to get past it. See
  `docs/agent-reference/suppressions.md`.

Agents: `CLAUDE.md` is the operating manual and takes precedence over this file.
