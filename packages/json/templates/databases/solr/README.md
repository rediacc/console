# Apache Solr Search Platform

Enterprise search platform built on Apache Lucene with powerful full-text search, faceting, real-time indexing, and RESTful APIs.

## Features

- Apache Solr 9.x with built-in Admin UI
- Full-text search with faceting and highlighting
- RESTful HTTP/JSON API
- Configurable cores with managed schema
- Persistent data storage with health checks

## Usage

```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start Solr
down  # Stop and cleanup
```

## Configuration

Edit `.env` to customize:
- `CONTAINER_NAME`: Container name (default: solr-server)
- `SOLR_HEAP`: JVM heap size (default: 512m)
- `SOLR_JAVA_MEM`: Java memory settings (default: -Xms512m -Xmx512m)
- `SOLR_CORE_NAME`: Default core name (default: mycore)

## Access

- **Port**: 8983 (Docker auto-assigns host port)
- **Admin UI**: http://localhost:[assigned-port]/solr
- **Find assigned port**: `docker compose ps` or `docker port solr-server 8983`

### Quick Start Examples

```bash
# Create a core
curl "http://localhost:8983/solr/admin/cores?action=CREATE&name=products&configSet=_default"

# Index a document
curl -X POST http://localhost:8983/solr/mycore/update?commit=true \
  -H "Content-Type: application/json" \
  -d '[{"id":"1","title":"Product Name","description":"Product description"}]'

# Search documents
curl "http://localhost:8983/solr/mycore/select?q=*:*&rows=10"

# Using container CLI
docker exec -it solr-server solr status
docker exec -it solr-server solr create_core -c products
```

### Data Persistence

- **Data Directory**: `./data` - All cores, indexes, and configurations
- Data persists across container restarts in the repository directory

## Resources

- [Docker Hub - Solr](https://hub.docker.com/_/solr)
- [Official Solr Documentation](https://solr.apache.org/guide/solr/latest/)
- [Solr Docker Guide](https://solr.apache.org/guide/solr/latest/deployment-guide/solr-in-docker.html)
- [Query Syntax Guide](https://solr.apache.org/guide/solr/latest/query-guide/query-syntax-and-parsers.html)
