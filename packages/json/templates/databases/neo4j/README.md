# Neo4j Graph Database

A powerful graph database platform for connected data with a built-in web interface (Neo4j Browser) for querying and visualization.

## Features

- Neo4j Community Edition 5.x with Neo4j Browser web interface
- APOC plugin pre-installed for extended functionality
- Cypher query language with relationship traversal
- Persistent data, logs, configuration, and plugins storage
- Authentication enabled with configurable memory settings

## Usage

```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start Neo4j
down  # Stop and cleanup
```

## Configuration

Edit `.env` to customize:

- `CONTAINER_NAME`: Container name (default: neo4j-server)
- `NEO4J_AUTH`: Username/password (default: neo4j/changeme123!)
- `NEO4J_PLUGINS`: Additional plugins (default: ["apoc"])
- `NEO4J_server_memory_heap_initial__size`: Initial heap size (default: 512M)
- `NEO4J_server_memory_heap_max__size`: Maximum heap size (default: 1G)
- `NEO4J_server_memory_pagecache_size`: Page cache size (default: 512M)

## Access

- **Neo4j Browser**: Port 7474 (Docker auto-assigns host port)
- **Bolt Protocol**: Port 7687 for application connections
- **Credentials**: Check `.env` file (default: neo4j/changeme123!)
- **Find assigned ports**: `docker compose ps` or `docker port neo4j-server 7474`
- **Cypher shell**: `docker exec -it neo4j-server cypher-shell -u neo4j -p changeme123!`

## Resources

- [Official Docker Hub](https://hub.docker.com/_/neo4j)
- [Neo4j Documentation](https://neo4j.com/docs/)
- [Cypher Query Language](https://neo4j.com/docs/cypher-manual/current/)
- [APOC Documentation](https://neo4j.com/labs/apoc/)
