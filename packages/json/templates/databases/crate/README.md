# CrateDB

A distributed SQL database designed for containerized environments with real-time analytics and scalability.

## Features
- PostgreSQL wire protocol compatible for easy integration
- Optimized for time-series data and real-time analytics
- Built-in web admin UI for management and queries
- Single-node mode for development and testing
- Automatic port assignment to avoid conflicts

## Usage
```bash
source Rediaccfile
prep  # Pull image and create data directory
up    # Start CrateDB server
down  # Stop and cleanup
```

## Configuration
Edit `.env` to customize:
- `CONTAINER_NAME`: Container name (default: cratedb-server)
- `CRATE_HEAP_SIZE`: JVM heap size, set to ~50% of container memory (default: 1g)
- `CLUSTER_NAME`: Cluster identifier (default: crate-docker-cluster)

Data persists in `./data` directory.

## Access
- **Admin UI**: Port 4200 (Docker auto-assigns host port)
- **PostgreSQL Protocol**: Port 5432 (Docker auto-assigns host port)
- **HTTP API**: Port 4200 (same as Admin UI)
- **Find assigned port**: `docker compose ps`

Connect via PostgreSQL client:
```bash
psql -h localhost -p <assigned-port> -U crate
```

Access Admin UI at `http://localhost:<assigned-port>`

## Resources
- [Official Docker Hub](https://hub.docker.com/_/crate)
- [Official Documentation](https://cratedb.com/docs)
- [SQL Reference](https://cratedb.com/docs/crate/reference/en/latest/sql/index.html)
- [PostgreSQL Compatibility](https://cratedb.com/docs/crate/reference/en/latest/interfaces/postgres.html)
