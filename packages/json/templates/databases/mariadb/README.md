# MariaDB Database Server

Production-ready MariaDB database server with persistent storage and automatic configuration.

## Features
- Persistent data storage with bind mounts
- Health check monitoring
- Initialization script support for automated schema setup
- Custom configuration support via `.cnf` files
- Optimized for production workloads

## Usage
```bash
source Rediaccfile
prep  # Pull MariaDB image and create directories
up    # Start MariaDB server
down  # Stop and cleanup
```

## Configuration
Edit `.env` to customize:
- `MARIADB_ROOT_PASSWORD`: Root user password (default: changeme)
- `MARIADB_DATABASE`: Initial database name (default: appdb)
- `MARIADB_USER`: Application user name (default: appuser)
- `MARIADB_PASSWORD`: Application user password (default: changeme)

**Custom Configuration**: Place `.cnf` files in `./config/` directory
**Initialization Scripts**: Place SQL or shell scripts in `./init/` directory (executed alphabetically on first startup)

## Access
- **Port**: 3306 (Docker auto-assigns host port)
- **Find assigned port**: `docker compose ps`
- **Connect**: `mysql -h 127.0.0.1 -P <assigned-port> -u root -p`

## Backup
```bash
# Full backup
docker compose exec db mariadb-dump -u root -p --all-databases > backup.sql

# Restore
docker compose exec -T db mariadb -u root -p < backup.sql
```

## Resources
- [Official Docker Hub](https://hub.docker.com/_/mariadb)
- [Official Documentation](https://mariadb.com/kb/en/documentation/)
- [Environment Variables](https://mariadb.com/kb/en/mariadb-docker-environment-variables/)
