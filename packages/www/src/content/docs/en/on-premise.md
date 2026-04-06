---
title: "On-Premise Installation"
description: "Running the account server and CLI distribution on your own infrastructure."
category: "Guides"
order: 5
language: en
---

Rediacc can run entirely on your own infrastructure. The standalone Docker image includes the account server, web portal, marketing site, and CLI distribution endpoint. No external dependencies on Rediacc's hosted services are required.

## Docker Image

Pull the standalone image:

```bash
docker pull ghcr.io/rediacc/elite/web:stable
```

Run with default settings:

```bash
docker run -p 80:80 -p 443:443 ghcr.io/rediacc/elite/web:stable
```

The image serves:
- Account API at `/account/api/v1/`
- Web portal at `/account/`
- Marketing site at `/`
- CLI artifacts at `/releases/`
- Renet binaries at `/bin/`

## Installing the CLI from Your Server

Users can install the CLI directly from your on-premise server. The install script auto-detects the update channel and configures the CLI to check your server for updates.

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com bash
```

This single command:
1. Downloads the CLI binary from your server's `/releases/` endpoint
2. Queries `/account/api/v1/.well-known/server-info` to discover the update channel
3. Writes `server.json` with your server URL, update channel, and encryption keys
4. Configures `rdc update` to check your server for future updates

No `REDIACC_CHANNEL` variable is needed. The install script reads the channel from your server's configuration automatically.

## CLI Configuration with Named Configs

For users who connect to multiple servers (on-premise, production, edge), named configs keep each environment isolated:

```bash
# Create a config for your on-premise server
rdc config init --name myserver --server https://account.example.com

# Log in using that config
rdc --config myserver subscription login

# All commands with --config use the on-premise server
rdc --config myserver machine query --name prod-1
```

Each named config stores its own account server URL and subscription token. Switching configs switches the entire server context.

## Air-Gapped Environments

For environments without internet access, set both the server URL and a custom releases URL:

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com \
  REDIACC_RELEASES_URL=https://account.example.com/releases \
  bash
```

The CLI will check `account.example.com/releases/cli/stable/manifest.json` for updates instead of the public releases CDN.

If the server is completely offline, install the CLI via npm from the bundled tarball:

```bash
npm install -g https://account.example.com/npm/rediacc-cli-latest.tgz
```

## Environment Variables Reference

| Variable | Used by | Purpose |
|---|---|---|
| `REDIACC_SERVER_URL` | Install script | Account server URL. Auto-discovers channel and encryption keys. |
| `REDIACC_RELEASES_URL` | Install script, CLI updater | Custom releases endpoint for CLI binaries. Default: `https://releases.rediacc.com` |
| `REDIACC_CHANNEL` | Install script | Override the update channel. Auto-detected from server if not set. |
| `REDIACC_ACCOUNT_SERVER` | CLI runtime | Override account server URL for all CLI commands. |
| `RDC_UPDATE_CHANNEL` | CLI runtime | Override update channel for `rdc update`. |

## Server Configuration

The on-premise Docker image uses the same `ENVIRONMENT` variable as the hosted service. Set it in your Docker environment or orchestration config:

- `ENVIRONMENT=production` (default): standard limits, stable update channel recommended to clients
- `ENVIRONMENT=edge`: 2X Community limits, edge update channel recommended to clients

See [Release Channels](/en/docs/release-channels) for details on what each environment provides.

## What the Server Tells the CLI

When the CLI connects to your server, it queries `/.well-known/server-info` to discover:

- **E2E encryption public key**: for zero-knowledge config storage
- **Minimum CLI version**: blocks outdated CLIs from connecting
- **Update channel**: tells the CLI which release channel to use for updates
- **Environment**: whether this is a production or edge deployment

This auto-configuration means users only need the server URL. Everything else is discovered automatically.
