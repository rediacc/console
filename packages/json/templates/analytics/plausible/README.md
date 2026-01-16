# Plausible Community Edition

Lightweight, privacy-focused web analytics platform that respects user privacy while providing valuable insights.

## Features
- Privacy-first analytics (GDPR, CCPA compliant, no cookies)
- Lightweight tracking script (<1KB)
- Real-time visitor statistics and pageview tracking
- Self-hosted with full data ownership
- Beautiful, simple dashboard interface
- Built on PostgreSQL and ClickHouse for performance

## Usage
```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start Plausible (auto-generates secret key on first run)
down  # Stop and cleanup
```

### First Run - Auto-Configuration
On first run, a secret key is automatically generated:
- **SECRET_KEY_BASE**: 64-byte encryption key for data security
- **Secret File**: Saved to `./plausible-secret.txt`
- **Initialization**: Database creation and migrations run automatically (~60 seconds)
- **Admin Account**: Create on first visit to web interface

**Important**: Keep the secret file secure - required for encryption!

## Configuration
Edit `.env` to customize:
- `BASE_URL`: Your domain (default: http://localhost:8000)
- `HTTP_PORT`: Container port (default: 8000)
- `DISABLE_REGISTRATION`: Registration mode (default: invite_only)
- `POSTGRES_PASSWORD`: Database password (default: postgres)

### Email Configuration (Optional)
For user invites and password resets, configure SMTP in `.env`:
- Uncomment and set `SMTP_HOST_ADDR`, `SMTP_HOST_PORT`, etc.
- Or use third-party services (Postmark, Mailgun, SendGrid)

## Access
- **Web Interface**: Auto-assigned port (find with `docker compose ps`)
  - Example: `http://localhost:<port>`
- **Find Port**: Run `docker compose ps` and look for mapped port
- **First Visit**: Create your admin account
- **Startup Time**: Allow ~60 seconds for database initialization

## Website Integration
After setting up Plausible:

1. **Create Site**: Add your website in the Plausible dashboard
2. **Add Tracking Script**: Insert in your website's `<head>`:
   ```html
   <script defer data-domain="yourdomain.com" src="http://your-plausible-url/js/script.js"></script>
   ```
3. **Verify**: Visit your site and check the Plausible dashboard

## Production Setup
For production deployments:

1. **Domain Configuration**
   - Set `BASE_URL` to your actual domain (e.g., https://analytics.example.com)
   - Configure reverse proxy (Nginx/Caddy) with SSL/TLS

2. **Email Setup**
   - Configure SMTP for user invites and password resets
   - Required for team collaboration features

3. **Registration Mode**
   - Set `DISABLE_REGISTRATION=true` after creating admin account
   - Use invite-only mode for team members

4. **Resource Requirements**
   - Minimum 2GB RAM recommended
   - CPU must support SSE 4.2 or NEON (ClickHouse requirement)

## Important Notes
- **SECRET_KEY_BASE**: Auto-generated on first run, stored in `./plausible-secret.txt`
- **Data Persistence**: PostgreSQL data in `./postgres-data/`, ClickHouse in `./clickhouse-data/`
- **Initialization**: First startup takes ~60 seconds for database setup
- **BASE_URL**: Must match your actual domain for proper operation
- **Port Assignment**: Container-only port (Docker assigns random host port to avoid conflicts)

## Resources
- [Official Documentation](https://plausible.io/docs/self-hosting)
- [Docker Setup Guide](https://github.com/plausible/community-edition)
- [Plausible Community](https://plausible.io/community)
- [Integration Guides](https://plausible.io/docs/integration-guides)
