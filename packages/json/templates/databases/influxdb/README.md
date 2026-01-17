# InfluxDB Time Series Database

High-performance time series database optimized for fast, high-availability storage and retrieval of time series data.

## Features

- InfluxDB 2.7 with built-in web UI and API
- Automated initial setup with authentication
- Flux query language for data analysis
- Persistent data storage in local directories
- Optimized for IoT, metrics, and monitoring data

## Usage

```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start InfluxDB
down  # Stop and cleanup
```

## Configuration

Edit `.env` to customize:

- `CONTAINER_NAME`: Container name (default: influxdb-server)
- `INFLUXDB_INIT_USERNAME`: Admin username (default: admin)
- `INFLUXDB_INIT_PASSWORD`: Admin password (default: influxPassword123!)
- `INFLUXDB_INIT_ORG`: Organization name (default: myorg)
- `INFLUXDB_INIT_BUCKET`: Default bucket name (default: mybucket)
- `INFLUXDB_INIT_RETENTION`: Data retention period (default: 0 - infinite)
- `INFLUXDB_INIT_ADMIN_TOKEN`: API admin token (auto-generated if not set)

## Access

**Web Interface:**
- **Port**: 8086 (Docker auto-assigns host port)
- **Credentials**: Check `.env` file for username/password
- **Find assigned port**: `docker compose ps`

**API Access:**
```bash
# Retrieve admin token from logs
docker logs influxdb-server 2>&1 | grep "token"

# Write data
curl -X POST http://localhost:8086/api/v2/write?org=myorg&bucket=mybucket \
  -H "Authorization: Token YOUR_ADMIN_TOKEN" \
  -H "Content-Type: text/plain" \
  --data-raw "temperature,location=room1 value=23.5"

# Query data using Flux
curl -X POST http://localhost:8086/api/v2/query?org=myorg \
  -H "Authorization: Token YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/vnd.flux" \
  --data 'from(bucket:"mybucket") |> range(start:-1h)'
```

**CLI Access:**
```bash
docker exec -it influxdb-server influx bucket list
docker exec -it influxdb-server influx query 'from(bucket:"mybucket") |> range(start:-1h)'
```

## Resources

- [Official Docker Hub](https://hub.docker.com/_/influxdb)
- [Official Documentation](https://docs.influxdata.com/influxdb/v2/)
- [Flux Query Language Guide](https://docs.influxdata.com/flux/v0/)
- [Migration from v1.x](https://docs.influxdata.com/influxdb/v2/upgrade/v1-to-v2/)
