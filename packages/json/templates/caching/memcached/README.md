# Memcached Template

High-performance distributed memory caching system for speeding up dynamic web applications.

## Features

- In-memory caching with configurable memory allocation
- Multi-threaded support for high concurrency
- Connection limit control and health monitoring
- LRU eviction policy for automatic memory management
- Lightweight and fast with no persistent storage

## Usage

```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start Memcached
down  # Stop and cleanup
```

## Configuration

Edit `.env` to customize:

- `CONTAINER_NAME`: Container name (default: memcached-server)
- `MEMCACHED_MEMORY`: Memory limit in MB (default: 64)
- `MEMCACHED_THREADS`: Number of threads (default: 4)
- `MEMCACHED_MAX_CONN`: Maximum connections (default: 1024)
- `MEMCACHED_VERBOSITY`: Verbosity level, use "v" or "vv" for verbose (default: empty)

## Access

- **Port**: 11211 (Docker auto-assigns host port)
- **Protocol**: TCP/UDP
- **Find assigned port**: `docker compose ps`

### Testing Connection

```bash
# Using docker exec
docker exec memcached-server sh -c 'echo "stats" | nc localhost 11211'

# Using telnet (replace <port> with assigned port)
telnet localhost <port>
stats
quit
```

### Common Commands

```bash
# Get server statistics
docker exec memcached-server sh -c 'echo "stats" | nc localhost 11211'

# Flush all data
docker exec memcached-server sh -c 'echo "flush_all" | nc localhost 11211'

# Monitor logs
docker logs -f memcached-server
```

## Resources

- [Official Docker Hub](https://hub.docker.com/_/memcached)
- [Memcached Documentation](https://memcached.org/)
- [Memcached Wiki](https://github.com/memcached/memcached/wiki)
