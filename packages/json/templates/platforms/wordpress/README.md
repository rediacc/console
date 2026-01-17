# WordPress Template

Full WordPress installation with MySQL database.

## Features
- Latest WordPress version with MySQL 8.0 backend
- Persistent storage for content, uploads, and database
- Auto-restart on failure for reliability
- Simple setup with guided installation wizard

## Usage
```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start WordPress and MySQL
down  # Stop and cleanup
```

## Configuration
Edit `.env` to customize:
- `REDIACC_SDK_REPO_INIT_SIZE`: Initial repository size (default: 1G)
- `REDIACC_SDK_REPO_RESIZE_SIZE`: Resize amount when full (default: empty)

Database credentials are configured in `docker-compose.yaml`:
- Database name: `exampledb`
- Database user: `exampleuser`
- Database password: `examplepass`

## Access
- **Port**: 80 (Docker auto-assigns host port)
- **Credentials**: Complete installation wizard on first visit
- **Find assigned port**: `docker compose ps`

Visit the assigned port and follow the WordPress installation wizard to set up your admin account.

## Resources
- [Official Docker Hub](https://hub.docker.com/_/wordpress)
- [Official Documentation](https://wordpress.org/support/)