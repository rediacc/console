# Apache CouchDB Database Template

NoSQL document database with HTTP JSON API, multi-master replication, and optional web-based admin interface (Fauxton).

## Features

- CouchDB 3.x with built-in Fauxton web UI
- RESTful HTTP/JSON API for documents
- Admin authentication and cluster-ready setup
- Health checks and persistent data storage
- Multi-master replication support

## Usage

```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start CouchDB
down  # Stop and cleanup
```

## Configuration

Edit `.env` to customize:
- `CONTAINER_NAME`: Container name (default: couchdb-server)
- `COUCHDB_USER`: Admin username (default: admin)
- `COUCHDB_PASSWORD`: Admin password (required)
- `COUCHDB_SECRET`: Cluster authentication secret (auto-generated)

## Access

- **Port**: 5984 (Docker auto-assigns host port)
- **Web UI**: http://localhost:5984/_utils (Fauxton)
- **Credentials**: See `.env` for username/password
- **Find assigned port**: `docker compose ps` or `docker port couchdb-server 5984`

**Quick API Test:**
```bash
# Check server status
curl http://localhost:5984/

# Create database (use credentials from .env)
curl -X PUT http://admin:yourPassword@localhost:5984/mydb
```

## Resources

- [CouchDB Docker Hub](https://hub.docker.com/_/couchdb)
- [Official CouchDB Documentation](https://docs.couchdb.org/)
- [HTTP API Guide](https://docs.couchdb.org/en/stable/api/index.html)
- [Fauxton Interface](https://docs.couchdb.org/en/stable/fauxton/index.html)
