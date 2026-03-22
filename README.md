# Observability Stack with Grafana Alloy

Modern observability stack using the latest stable versions of Grafana ecosystem components.

## Components

- **Grafana Alloy v1.10.1** - Data collection and processing
- **Prometheus v3.5.0** - Metrics storage (LTS release)
- **Grafana 12.1.1** - Visualization dashboard
- **Loki 3.5.5** - Log aggregation
- **Tempo 2.8.2** - Distributed tracing

## Architecture

```
Data Sources → Grafana Alloy → Prometheus/Loki/Tempo → Grafana Dashboard
```

## Quick Start

1. Start the stack:
```bash
cd observability-stack
docker-compose up -d
```

2. Access services:
- **Grafana**: http://localhost:3000 (admin/admin)
- **Alloy UI**: http://localhost:12345
- **Prometheus**: http://localhost:9090
- **Loki**: http://localhost:3100
- **Tempo**: http://localhost:3200

## Data Ingestion Endpoints

- **OTLP gRPC**: localhost:4317
- **OTLP HTTP**: localhost:4318
- **Prometheus metrics**: localhost:9090/api/v1/write
- **Loki logs**: localhost:3100/loki/api/v1/push

## Configuration

All configurations are in the `config/` directory:
- `alloy/config.alloy` - Data collection rules
- `prometheus/prometheus.yml` - Metrics scraping
- `grafana/` - Dashboard and datasource provisioning
- `loki/local-config.yaml` - Log aggregation settings
- `tempo/tempo.yaml` - Tracing configuration

## Data Retention

- **Prometheus**: 30 days / 50GB
- **Loki**: 30 days
- **Tempo**: 30 days (720 hours)

## Integration with Existing Infrastructure

To integrate with your existing nginx-ssl proxy:

1. Add to your main docker-compose.yml:
```yaml
  observability-stack:
    extends:
      file: ./observability-stack/docker-compose.yml
      service: grafana
    networks:
      - rediacc_intranet
```

2. Update nginx configuration to proxy `obs.rediacc.com` to `rediacc-grafana:3000`

## Monitoring

The stack includes self-monitoring:
- All components expose metrics to Prometheus
- Service discovery for Docker containers
- Pre-configured Grafana datasources
