# Apache Cassandra Database Template

Distributed NoSQL database designed for handling large amounts of data with high availability and no single point of failure.

## Features

- Apache Cassandra 5.0 with authentication enabled
- Persistent data storage with automatic initialization
- CQL shell access and client connectivity
- Health checks for container readiness
- Sample keyspace and schema included

## Usage

```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start Cassandra
down  # Stop and cleanup
```

## Configuration

Edit `.env` to customize:
- `CONTAINER_NAME`: Container name (default: cassandra-db)
- `CASSANDRA_CLUSTER_NAME`: Cluster name (default: MyCluster)
- `CASSANDRA_DC`: Datacenter name (default: datacenter1)
- `CASSANDRA_RACK`: Rack name (default: rack1)
- `CASSANDRA_ENDPOINT_SNITCH`: Snitch implementation (default: GossipingPropertyFileSnitch)
- `CASSANDRA_NUM_TOKENS`: Number of tokens (default: 256)
- `CASSANDRA_AUTHENTICATOR`: Authentication method (default: PasswordAuthenticator)
- `CASSANDRA_AUTHORIZER`: Authorization method (default: CassandraAuthorizer)

**Default credentials:** Username `cassandra`, Password `cassandra` (change in production)

## Access

**Port:** 9042 (Docker auto-assigns host port)

**Find assigned port:**
```bash
docker compose ps
```

**CQL Shell:**
```bash
docker exec -it cassandra-db cqlsh -u cassandra -p cassandra
```

**Connection details:**
- Host: localhost
- Username: cassandra
- Password: cassandra
- Datacenter: datacenter1
- Keyspace: myapp (pre-created)

**Check cluster status:**
```bash
docker exec -it cassandra-db nodetool status
```

**Note:** Cassandra takes 30-60 seconds to fully start. Wait for "Created default superuser role" in logs.

## Resources

- [Official Docker Hub](https://hub.docker.com/_/cassandra)
- [Official Documentation](https://cassandra.apache.org/doc/latest/)
- [CQL Reference](https://cassandra.apache.org/doc/latest/cassandra/cql/)
- [DataStax Drivers](https://docs.datastax.com/en/driver-matrix/docs/index.html)
