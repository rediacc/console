# PostgreSQL Template

High-performance PostgreSQL setup with benchmarking and automated configuration.

## Features
- Auto-detected container and dynamic port assignment
- CPU-optimized threading (auto-detects cores, max 8)
- Sysbench integration for OLTP performance testing
- Bulk data generation for custom tables
- One-command host setup for required tools

## Usage
```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start PostgreSQL
down  # Stop and cleanup
```

### Benchmarking
```bash
# Install sysbench and PostgreSQL client
./postgres.sh host_setup

# Initialize database and run benchmarks
source ./postgres.sh
./postgres.sh create_database
./postgres.sh initialize_sysbench    # Load 8×1M tables
./postgres.sh benchmark_qps          # Run QPS test
./postgres.sh cleanup_sysbench       # Remove test data
```

## Configuration
Edit `.env` to customize:
- `PGUSER`: PostgreSQL username (default: postgres)
- `PGPASSWORD`: Database password (default: mysecretpassword)
- `DBNAME`: Database name for benchmarks (default: sysbench_test)
- `TABLES`: Number of sysbench tables (default: 8)
- `TABLE_SIZE`: Rows per sysbench table (default: 1000000)

Container name and port are auto-detected. Threads auto-set to CPU cores (max 8).

## Access
- **Port**: 5432 (Docker auto-assigns host port)
- **Credentials**: Check `.env` file
- **Find assigned port**: `docker compose ps`
- **Connect**: `psql -h 127.0.0.1 -p <host-port> -U postgres`

## Resources
- [Official Docker Hub](https://hub.docker.com/_/postgres)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Sysbench Documentation](https://github.com/akopytov/sysbench)