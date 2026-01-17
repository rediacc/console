# RethinkDB

RethinkDB is an open-source, distributed JSON database designed for real-time applications. Built for modern web and mobile apps, it delivers real-time updates through push architecture and offers an intuitive query language with a powerful administration interface.

## Features

- **Real-time Push Architecture**: Automatically pushes data changes to applications in real-time
- **JSON Document Store**: Schema-free, stores JSON documents natively with powerful ReQL query language
- **Web-based Admin Interface**: Built-in administration console with Data Explorer and monitoring
- **Geospatial Support**: Built-in geospatial indexing and queries for location-based applications
- **Multi-language Drivers**: Official drivers for JavaScript, Python, Ruby, Java, and more

## Usage

```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start RethinkDB
down  # Stop and cleanup
```

## Configuration

Edit `.env` to customize:
- `CONTAINER_NAME`: Container name (default: rethinkdb)
- `RETHINKDB_CACHE_SIZE`: Cache size in MB (default: 512)

Data is stored in `./data` directory and persists across container restarts.

## Access

- **Web Admin**: Port 8080 (Docker auto-assigns host port)
- **Client Driver**: Port 28015 (for application connections)
- **Cluster Port**: Port 29015 (for cluster setups)
- **Find assigned ports**: `docker compose ps`

### Connection Examples

```javascript
// Node.js
const r = require('rethinkdb');
const conn = await r.connect({ host: 'localhost', port: 28015, db: 'test' });
```

```python
# Python
import rethinkdb as r
conn = r.connect(host='localhost', port=28015, db='test')
```

### Quick Start with Data Explorer

```javascript
// Create database and table using web interface or driver
r.dbCreate('myapp').run(conn);
r.db('myapp').tableCreate('users').run(conn);

// Insert data
r.db('myapp').table('users').insert({
  name: 'John Doe',
  email: 'john@example.com',
  created: r.now()
}).run(conn);

// Real-time updates
r.db('myapp').table('users').changes().run(conn, (err, cursor) => {
  cursor.each(console.log);  // Prints changes as they happen
});
```

## Backup and Restore

```bash
# Backup
docker exec rethinkdb rethinkdb dump -f backup.tar.gz

# Restore
docker exec rethinkdb rethinkdb restore backup.tar.gz
```

## Resources

- [Official Docker Hub](https://hub.docker.com/_/rethinkdb)
- [Official Documentation](https://rethinkdb.com/docs/)
- [Ten-minute Guide](https://rethinkdb.com/docs/guide/javascript/)
- [API Reference](https://rethinkdb.com/api/javascript/)
