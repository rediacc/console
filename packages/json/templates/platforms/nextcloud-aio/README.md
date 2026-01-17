# Nextcloud All-in-One

Official Nextcloud All-in-One deployment with master container orchestration for complete self-hosted cloud platform.

## Features
- Master container manages entire Nextcloud stack (web, database, cache, optional services)
- Built-in PostgreSQL, Redis, Apache with optimized PHP configuration
- Automatic HTTPS with Let's Encrypt certificate management
- Optional components: Collabora Office, Talk, ClamAV, Full-text Search
- Web-based management interface with backup/restore capabilities

## Usage
```bash
source Rediaccfile
prep  # Pull master container image
up    # Start Nextcloud AIO
down  # Stop Nextcloud AIO
```

## Configuration
Edit `.env` to customize:
- `DOCKER_HOST`: Docker socket path (default: `/var/run/docker.sock`)
  - Use custom path for systems with per-repository Docker instances
- `NEXTCLOUD_DATADIR`: Custom data directory location (optional)
- `APACHE_PORT`: Custom Apache port binding (default: auto-assigned)
- `APACHE_IP_BINDING`: IP address binding for reverse proxy setups (optional)

## Access
- **Management Interface**: Auto-assigned port (find with `docker compose ps`)
  - Default: `https://localhost:<port>` (self-signed certificate)
- **Initial Setup**: Follow web interface wizard to configure domain, admin account, and optional services
- **Nextcloud Access**: Port 443 (HTTPS) after configuration via management interface

## Important Notes
- **Docker Socket**: This template requires Docker socket access for the master container to orchestrate other containers
  - Configurable via `DOCKER_HOST` environment variable
  - Defaults to `/var/run/docker.sock` for standard Docker installations
- **Single Domain**: AIO requires one domain for all services (simplifies SSL/TLS management)
- **Volume Requirements**: Uses named volume with local bind driver pointing to `./aio-config` for portability
- **First Run**: Complete setup via web interface - configuration is managed through UI, not environment variables

## Resources
- [Official Documentation](https://github.com/nextcloud/all-in-one)
- [Docker Hub](https://github.com/nextcloud/all-in-one/pkgs/container/all-in-one)
- [Nextcloud Homepage](https://nextcloud.com)
