# ArangoDB Multi-Model Database

A native multi-model database with flexible data models for documents, graphs, and key-value pairs. Build high-performance applications using a convenient SQL-like query language or JavaScript extensions.

## Features

- Multi-model support (document, graph, key-value)
- Built-in web interface for administration
- AQL query language (SQL-like)
- Authentication enabled by default
- Persistent data storage with health checks

## Usage

```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start ArangoDB
down  # Stop and cleanup
```

## Configuration

Edit `.env` to customize:
- `CONTAINER_NAME`: Container name (default: arangodb-server)
- `ARANGO_ROOT_PASSWORD`: Root password for database access (required)
- `ARANGODB_OVERRIDE_DETECTED_TOTAL_MEMORY`: Memory limit (default: auto-detect)
- `ARANGODB_OVERRIDE_DETECTED_NUMBER_OF_CORES`: CPU cores limit (default: auto-detect)

## Access

- **Port**: 8529 (Docker auto-assigns host port)
- **Web Interface**: Access via assigned port with username `root`
- **Password**: Check `ARANGO_ROOT_PASSWORD` in `.env`
- **Find assigned port**: `docker compose ps`

### CLI Access
```bash
# Access ArangoDB shell
docker exec -it arangodb-server arangosh --server.password yourRootPassword123!

# Connection string for applications
http://root:yourRootPassword123!@localhost:8529
```

### Quick AQL Examples
```javascript
// Create database and collection
db._createDatabase("myapp");
db._useDatabase("myapp");
db._create("users");

// Query with AQL
db._query('FOR user IN users FILTER user.age >= 18 RETURN user');
```

## Resources

- [Official Docker Hub](https://hub.docker.com/_/arangodb)
- [Official Documentation](https://docs.arangodb.com/)
- [AQL Tutorial](https://docs.arangodb.com/stable/aql/)
