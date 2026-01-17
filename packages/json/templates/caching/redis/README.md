# Redis Cache Template

High-performance, in-memory data structure store used as a database, cache, and message broker.

## Features

- Redis 7 Alpine (lightweight and fast)
- Password authentication with configurable credentials
- Configurable memory limits with LRU eviction policy
- Persistent data storage with health checks
- Isolated network for security

## Usage

```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start Redis server
down  # Stop and cleanup
```

## Configuration

Edit `.env` to customize:

- `CONTAINER_NAME`: Container name (default: redis-server)
- `REDIS_PORT`: Port mapping (default: 6379)
- `REDIS_PASSWORD`: Authentication password (required)
- `REDIS_MAXMEMORY`: Memory limit (default: 256mb)
- `REDIS_MAXMEMORY_POLICY`: Eviction policy (default: allkeys-lru)

## Access

- **Port**: 6379 (Docker auto-assigns host port)
- **Password**: Set in `.env` file (`REDIS_PASSWORD`)
- **Find assigned port**: `docker compose ps`

Connect using redis-cli:
```bash
# Using redis-cli
redis-cli -h localhost -p 6379 -a yourPassword

# Using Docker exec
docker exec -it redis-server redis-cli -a yourPassword
```

## Resources

- [Official Docker Hub](https://hub.docker.com/_/redis)
- [Official Documentation](https://redis.io/docs/)