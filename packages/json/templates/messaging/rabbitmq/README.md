# RabbitMQ Message Queue Template

Advanced message queuing protocol (AMQP) broker with management interface.

## Features

- RabbitMQ 3 with management plugin and web UI
- Persistent message storage with health checks
- Configurable memory limits and virtual hosts
- Alpine-based lightweight image
- Pre-configured admin credentials

## Usage

```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start RabbitMQ server
down  # Stop and cleanup
```

## Configuration

Edit `.env` to customize:

- `CONTAINER_NAME`: Container name (default: rabbitmq-server)
- `RABBITMQ_PORT`: AMQP port (default: 5672)
- `RABBITMQ_MANAGEMENT_PORT`: Management UI port (default: 15672)
- `RABBITMQ_DEFAULT_USER`: Admin username (default: admin)
- `RABBITMQ_DEFAULT_PASS`: Admin password (default: adminPassword123!)
- `RABBITMQ_DEFAULT_VHOST`: Default virtual host (default: /)
- `RABBITMQ_MEMORY_LIMIT`: Memory high watermark (default: 0.4)

## Access

- **Management UI**: Port 15672 (Docker auto-assigns host port)
- **AMQP Port**: Port 5672 (Docker auto-assigns host port)
- **Default Credentials**: admin / adminPassword123! (set in `.env`)
- **Find assigned ports**: `docker compose ps`

### Quick Connection Example

```python
import pika

credentials = pika.PlainCredentials('admin', 'adminPassword123!')
connection = pika.BlockingConnection(
    pika.ConnectionParameters('localhost', 5672, '/', credentials)
)
```

### Common Commands

```bash
# Check status
docker exec -it rabbitmq-server rabbitmqctl status

# List queues
docker exec -it rabbitmq-server rabbitmqctl list_queues

# Create user
docker exec -it rabbitmq-server rabbitmqctl add_user myuser mypass
docker exec -it rabbitmq-server rabbitmqctl set_permissions -p / myuser ".*" ".*" ".*"
```

## Resources

- [Official Docker Hub](https://hub.docker.com/_/rabbitmq)
- [RabbitMQ Documentation](https://www.rabbitmq.com/documentation.html)
- [AMQP Protocol Specification](https://www.rabbitmq.com/protocols.html)