# Percona Server for MySQL

Enterprise-ready MySQL database server with enhanced performance, scalability, and diagnostics features.

## Features
- Drop-in replacement for MySQL with enterprise-grade enhancements
- Superior performance and scalability over standard MySQL
- Advanced diagnostics and monitoring capabilities
- Full MySQL compatibility with zero application changes
- Persistent storage with bind mounts

## Usage
```bash
source Rediaccfile
prep  # Pull image and create data directory
up    # Start Percona Server
down  # Stop and cleanup
```

## Configuration
Edit `.env` to customize:
- `MYSQL_ROOT_PASSWORD`: Root user password (default: notSecureChangeMe)
- `MYSQL_DATABASE`: Database to create on first start (optional)
- `MYSQL_USER`: Additional user to create (optional)
- `MYSQL_PASSWORD`: Password for additional user (optional)

**Security:** Change default passwords before deployment. Use `MYSQL_RANDOM_ROOT_PASSWORD=yes` for production.

## Access
- **Port**: 3306 (Docker auto-assigns host port)
- **Credentials**: Check `.env` file
- **Find assigned port**: `docker compose ps`
- **Connect**: `mysql -h 127.0.0.1 -P <mapped-port> -u root -p`

## Resources
- [Official Docker Hub](https://hub.docker.com/_/percona)
- [Percona Server Documentation](https://docs.percona.com/percona-server/8.0/)
- [Feature Comparison](https://www.percona.com/software/mysql-database/percona-server)
