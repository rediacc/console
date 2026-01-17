# Microsoft SQL Server Template

Quick deployment of Microsoft SQL Server 2022 using Docker.

## Features
- SQL Server 2022 Developer Edition with SQL Server Agent
- Persistent storage for data, logs, and secrets
- Configurable SA password and security settings
- Health check monitoring included

## Usage
```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start SQL Server
down  # Stop and cleanup
```

## Configuration
Edit `.env` to customize:
- `MSSQL_SA_PASSWORD`: SA account password (default: yourStrong(!)Password)
- `ACCEPT_EULA`: Accept MSSQL EULA (default: Y)
- `MSSQL_PID`: Product ID/Edition (default: Developer)

## Access
- **Port**: 1433 (Docker auto-assigns host port)
- **Credentials**: SA user with password from `.env`
- **Find assigned port**: `docker compose ps`
- **Connect**: `sqlcmd -S localhost,<port> -U sa -P '<password>'`

## Resources
- [Official Docker Hub](https://hub.docker.com/_/microsoft-mssql-server)
- [Official Documentation](https://learn.microsoft.com/en-us/sql/linux/sql-server-linux-overview)