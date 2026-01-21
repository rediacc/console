# Rediacc Plugins

Official plugin system for extending Rediacc infrastructure with web-based tools. These Docker-based plugins integrate seamlessly with Rediacc repositories via Unix sockets.

## Available Plugins

### Browser Plugin
Web-based file browser powered by [FileBrowser](https://filebrowser.org/). Provides a modern interface for browsing and managing repository files through your web browser.

**Features:**
- Clean, intuitive file management UI
- Disabled execution for security
- No authentication required (secured by Rediacc)
- Socket-based communication

**Image:** `rediacc/plugin-browser`

### Terminal Plugin
Web-based terminal emulator powered by [ttyd](https://github.com/tsl0922/ttyd). Access your repository environment directly from the browser with a full bash terminal.

**Features:**
- Full terminal access to repository environment
- Writable terminal with complete shell functionality
- Real-time terminal streaming
- Socket-based communication

**Image:** `rediacc/plugin-terminal`

## Architecture

All plugins follow a consistent architecture:
- **Base Image**: Configurable via `ARG BASE_IMAGE` (default: `ubuntu:24.04`)
- **Working Directory**: `/repo` (repository root)
- **Communication**: Unix sockets in `/sockets` directory
- **Socket Naming**: `${SOCKET_DIR}/${PLUGIN_NAME}.sock`

## Building Plugins

### Local Build (Development)

Build all plugins locally without pushing:

```bash
./build-local.sh
```

Optional environment variables:
```bash
# Use custom base image
export SYSTEM_BASE_IMAGE=ubuntu:24.04

# Use custom registry
export DOCKER_REGISTRY=registry.example.com

./build-local.sh
```

### CI Build

The CI workflow automatically builds and pushes plugins on:
- Push to main branch
- Version tags (e.g., `1.2.3`)

Images are pushed to Docker Hub with tags:
- `latest` - Always updated
- `YYYY-MM-DD` - Date-based tag
- `vX.Y.Z` - Version tag (on release tags)

## Creating New Plugins

To create a new plugin:

1. Create a new directory with the plugin name
2. Add a `Dockerfile` with this structure:

```dockerfile
ARG BASE_IMAGE=ubuntu:24.04
FROM ${BASE_IMAGE}
LABEL com.rediacc.base-image="${BASE_IMAGE}"

WORKDIR /repo

# Install your plugin software
RUN apt-get update && apt-get install -y your-tool && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Socket configuration
ENV SOCKET_DIR=/sockets
ENV PLUGIN_NAME=YourPluginName

ENTRYPOINT ["/bin/bash", "-c"]

CMD ["your-plugin-command --socket ${SOCKET_DIR}/${PLUGIN_NAME}.sock"]
```

3. Build with `./build-local.sh` to test locally

## Plugin Guidelines

**Security:**
- Plugins should not require authentication (handled by Rediacc)
- Use Unix sockets for communication (not network ports)
- Minimize attack surface by disabling unnecessary features
- Clean up temporary files and package caches

**Performance:**
- Keep images small by cleaning apt caches
- Use multi-stage builds if needed
- Optimize for startup time

**Compatibility:**
- Support configurable base images
- Follow Rediacc labeling conventions
- Use `/repo` as working directory
- Use standard socket directory `/sockets`

## Integration with Rediacc

Plugins are automatically discovered and integrated into Rediacc repositories. Each plugin becomes accessible through the Rediacc console via proxy routing to the Unix socket.

**Socket Permissions:** Plugins use mode `384` (0600) for socket files, ensuring only the owner can read/write.
