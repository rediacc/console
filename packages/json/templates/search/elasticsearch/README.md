# Elasticsearch Search Engine Template

Full-text search and analytics engine with Kibana visualization interface.

## Features

- Elasticsearch 8.11.0 with single-node development setup
- Kibana 8.11.0 web UI for data visualization and management
- Configurable JVM heap size and cluster settings
- Persistent data storage with health checks
- Security disabled by default for easy local development

## Usage

```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start Elasticsearch and Kibana
down  # Stop and cleanup
```

## Configuration

Edit `.env` to customize:
- `CONTAINER_NAME`: Container name (default: elasticsearch)
- `ES_PORT`: HTTP API port (default: 9200)
- `ES_TRANSPORT_PORT`: Transport port (default: 9300)
- `ES_CLUSTER_NAME`: Cluster name (default: docker-cluster)
- `ES_HEAP_SIZE`: JVM heap size (default: 512m)
- `ES_SECURITY_ENABLED`: Enable security (default: false)
- `KIBANA_PORT`: Web UI port (default: 5601)
- `KIBANA_SERVER_NAME`: Server name (default: kibana)

## Access

**Elasticsearch API**: `http://localhost:9200`
```bash
# Check cluster health
curl http://localhost:9200/_cluster/health?pretty

# Index a document
curl -X POST "localhost:9200/my-index/_doc" -H 'Content-Type: application/json' -d'
{
  "title": "Sample Document",
  "content": "This is a test document"
}'

# Search documents
curl -X GET "localhost:9200/my-index/_search?q=test&pretty"
```

**Kibana Web Interface**: `http://localhost:5601`
- No authentication required (security disabled)

**Find assigned ports**: `docker compose ps`

## Resources

- [Elasticsearch Docker Hub](https://hub.docker.com/_/elasticsearch)
- [Elasticsearch Documentation](https://www.elastic.co/guide/en/elasticsearch/reference/current/index.html)
- [Kibana Documentation](https://www.elastic.co/guide/en/kibana/current/index.html)