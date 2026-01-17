# n8n Workflow Automation

Fair-code workflow automation tool for connecting apps and services with a visual interface.

## Features
- Visual workflow editor with 400+ integrations
- Self-hosted with full data control
- SQLite database (default) or PostgreSQL for production
- Webhook support for external triggers
- Scheduled workflow execution
- Built-in error handling and debugging

## Usage
```bash
source Rediaccfile
prep  # Pull image and create directory
up    # Start n8n (auto-generates encryption key on first run)
down  # Stop and cleanup
```

### First Run - Auto-Configuration
On first run, an encryption key is automatically generated:
- **Encryption Key**: Random 32-character key for credential security
- **Credentials File**: Saved to `./n8n-data/encryption-key.txt`
- **Admin Access**: Default username/password (see .env file)

**Important**: Change the default admin password after first login!

## Configuration
Edit `.env` to customize:
- `N8N_BASIC_AUTH_USER`: Admin username (default: admin)
- `N8N_BASIC_AUTH_PASSWORD`: Admin password (default: change me!)
- `GENERIC_TIMEZONE`: Timezone for workflow scheduling (default: UTC)
- `N8N_PORT`: Container port (default: 5678)

## Access
- **Web Interface**: Auto-assigned port (find with `docker compose ps`)
  - Example: `http://localhost:<port>`
- **Default Credentials**: Check `.env` file (admin / changeme)
- **Find Port**: Run `docker compose ps` and look for mapped port

## Workflow Management
- **Create**: Access web interface, click "+" to create new workflow
- **Backup**: Data stored in `./n8n-data/` directory
- **Import/Export**: Use web interface Tools → Import/Export
- **Persistence**: All workflows saved automatically to local volume

## Production Setup (Optional)
For production deployments, consider:

1. **PostgreSQL Database** (better performance, scalability)
   - Add PostgreSQL service to docker-compose.yaml
   - Set `DB_TYPE=postgresdb` in environment

2. **Redis Queue Mode** (for distributed execution)
   - Add Redis service
   - Set `EXECUTIONS_MODE=queue` and Redis connection details

3. **Reverse Proxy** (SSL/TLS, custom domain)
   - Configure Nginx/Caddy with Let's Encrypt
   - Set `N8N_PROTOCOL=https` and `WEBHOOK_URL`

4. **Resource Limits**
   - Increase memory to 2-4GB for heavy workflows
   - Add CPU limits in docker-compose.yaml

## Important Notes
- **Encryption Key**: Auto-generated on first run, stored in `./n8n-data/encryption-key.txt`
- **Credentials File**: Keep this secure - required for n8n to decrypt stored credentials
- **SQLite Database**: Default database, stored in `./n8n-data/database.sqlite`
- **Data Persistence**: All workflows, credentials, and settings in `./n8n-data/`
- **Port Assignment**: Container-only port (Docker assigns random host port to avoid conflicts)

## Resources
- [Official Documentation](https://docs.n8n.io/)
- [Docker Installation Guide](https://docs.n8n.io/hosting/installation/docker/)
- [n8n Community](https://community.n8n.io/)
- [Workflow Templates](https://n8n.io/workflows/)
