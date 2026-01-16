# MySQL/MariaDB Template

MariaDB database with phpMyAdmin web interface.

## Features
- MariaDB 10.3 database server
- phpMyAdmin for web-based administration
- Persistent data storage with bind mounts
- Isolated Docker network

## Usage
```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start MariaDB and phpMyAdmin
down  # Stop and cleanup
```

## Configuration
Edit `.env` to customize:
- `MYSQL_ROOT_PASSWORD`: Root user password (default: rootpassword)
- `MYSQL_DATABASE`: Initial database name (default: myapp)
- `MYSQL_USER`: Application user (default: user)
- `MYSQL_PASSWORD`: Application password (default: password)

## Access
- **MySQL Port**: 3306 (Docker auto-assigns host port)
- **phpMyAdmin**: Port 8080 (Docker auto-assigns host port)
- **Credentials**: Check `.env` file
- **Find assigned port**: `docker compose ps`

## Connect
```bash
# Connect via MySQL client
mysql -h localhost -P 3306 -u root -p

# Or use phpMyAdmin web interface
docker compose ps  # Find phpMyAdmin port
```

## Resources
- [Official Docker Hub - MariaDB](https://hub.docker.com/_/mariadb)
- [Official Docker Hub - phpMyAdmin](https://hub.docker.com/_/phpmyadmin)
- [MariaDB Documentation](https://mariadb.com/kb/en/documentation/)
- [MySQL Documentation](https://dev.mysql.com/doc/)