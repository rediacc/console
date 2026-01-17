# Nginx Template

Minimal Nginx web server deployment.

## Features
- Latest Nginx stable release
- Single command deployment
- Lightweight and fast HTTP server
- Auto-cleanup on container stop

## Usage
```bash
source Rediaccfile
prep  # Pull Nginx image
up    # Start Nginx server
down  # Stop and cleanup
```

## Configuration
This template uses a minimal configuration:
- **Port**: 80 (Docker auto-assigns host port)
- **Container**: Runs in detached mode with auto-removal

## Access
- **Port**: 80 (Docker auto-assigns host port)
- **Find assigned port**: `docker ps | grep rediacc-nginx`
- **Default page**: Access via `http://localhost:[assigned-port]`

## Resources
- [Official Docker Hub](https://hub.docker.com/_/nginx)
- [Official Documentation](https://nginx.org/en/docs/)