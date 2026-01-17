# Prometheus + Grafana Monitoring Template

Complete monitoring stack with Prometheus metrics collection and Grafana visualization.

## Features

- Prometheus time-series database with configurable retention
- Grafana visualization with pre-configured Prometheus data source
- Node Exporter for system-level metrics (CPU, memory, disk)
- Persistent data storage with automatic provisioning
- Ready to add custom application metrics

## Usage

```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start monitoring stack
down  # Stop and cleanup
```

## Configuration

Edit `.env` to customize:

**Prometheus Settings:**
- `PROMETHEUS_PORT`: Web UI port (default: 9090)
- `PROMETHEUS_RETENTION`: Data retention period (default: 15d)

**Grafana Settings:**
- `GRAFANA_PORT`: Web UI port (default: 3000)
- `GRAFANA_ADMIN_USER`: Admin username (default: admin)
- `GRAFANA_ADMIN_PASSWORD`: Admin password (default: admin)
- `GRAFANA_ALLOW_SIGN_UP`: Allow user registration (default: false)
- `GRAFANA_PLUGINS`: Comma-separated plugin list (optional)

**Node Exporter:**
- `NODE_EXPORTER_PORT`: Metrics endpoint port (default: 9100)

## Access

**Prometheus:**
- Port: 9090 (Docker auto-assigns host port)
- No authentication required
- Find assigned port: `docker compose ps`

**Grafana:**
- Port: 3000 (Docker auto-assigns host port)
- Default credentials: admin/admin (change on first login)
- Prometheus data source pre-configured

**Node Exporter:**
- Port: 9100 (metrics endpoint)
- Access metrics at: http://localhost:9100/metrics

To add custom metrics, edit `prometheus/prometheus.yml` to add scrape targets, then reload config with `curl -X POST http://localhost:9090/-/reload`.

## Resources

- [Prometheus on Docker Hub](https://hub.docker.com/r/prom/prometheus)
- [Grafana on Docker Hub](https://hub.docker.com/r/grafana/grafana)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Node Exporter Documentation](https://github.com/prometheus/node_exporter)