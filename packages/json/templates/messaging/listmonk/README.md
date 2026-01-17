# Listmonk Newsletter Manager

Self-hosted newsletter and mailing list management platform for email campaigns and subscriber management.

## Features
- Newsletter and email campaign management with scheduling
- Subscriber lists with segmentation and custom attributes
- Rich template editor (WYSIWYG and HTML)
- Analytics, bounce tracking, and RESTful API
- Self-hosted with full privacy and data ownership

## Usage
```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start Listmonk (initializes database on first run)
down  # Stop and cleanup
```

### First Run - Initial Setup
On first run, the database is automatically initialized:
- **Database Setup**: Tables and schema created automatically (idempotent)
- **Admin Account**: You will be prompted to create admin account on first visit
- **One-Time Setup**: Visit `/admin` path to complete setup

**Important**: Create a strong admin password during first-time setup!

## Configuration
Edit `.env` to customize:
- `POSTGRES_USER`: Database username (default: listmonk)
- `POSTGRES_PASSWORD`: Database password (default: listmonk)
- `TZ`: Timezone for scheduled campaigns (default: Etc/UTC)
- `LISTMONK_PORT`: Container port (default: 9000)

## Access
- **Web Interface**: Auto-assigned port (find with `docker compose ps`)
  - Admin panel: `http://localhost:<port>/admin`
  - Public archive: `http://localhost:<port>/`
- **Find Port**: Run `docker compose ps` and look for mapped port
- **First Visit**: Visit `/admin` to create your admin account
- **Startup Time**: Allow ~30 seconds for initialization

## SMTP Configuration (Required!)
**Critical**: Listmonk requires an external SMTP server to send emails.

### Setup Steps:
1. **Login** to Listmonk web interface
2. **Navigate** to Settings → SMTP
3. **Add SMTP** provider with these details:
   - Host, Port, Username, Password
   - TLS/SSL settings
   - From email address
4. **Test** the connection before creating campaigns

### Supported SMTP Providers:
- **Gmail**: smtp.gmail.com:587 (requires App Password)
- **SendGrid**: smtp.sendgrid.net:587 (API key as password)
- **Mailgun**: smtp.mailgun.org:587
- **Amazon SES**: email-smtp.[region].amazonaws.com:587
- **Self-hosted**: Your own SMTP server
- See `.env` file for detailed provider configurations

## Campaign Management
1. **Lists**: Create subscriber lists (Lists → New List)
2. **Subscribers**: Import CSV (email, name, attributes)
3. **Templates**: Design email templates
4. **Campaign**: Create, test, then schedule or send
5. **Analytics**: Track opens, clicks, and bounces

## Production Setup

1. **Security**
   - Change admin password immediately after first login
   - Manage users via Settings → Users

2. **SMTP Configuration**
   - Use reliable provider (see .env for options)
   - Configure bounce handling
   - Test before bulk sends

3. **Email Deliverability**
   - Set up DNS records (SPF, DKIM, DMARC)
   - Use dedicated sending domain
   - Configure rate limiting (Settings → Performance)

4. **Backups**
   - Regular PostgreSQL backups essential
   - Data in `./postgres-data/` (subscribers, campaigns, analytics)

## Important Notes
- **SMTP Required**: Listmonk cannot send emails without SMTP configuration
- **First-Time Setup**: Admin account created through web interface on first visit to `/admin`
- **Data Persistence**: Subscriber data and campaigns in `./postgres-data/`
- **Uploads**: Custom files and images stored in `./uploads/`
- **Port Assignment**: Container-only port (Docker assigns random host port to avoid conflicts)
- **Idempotent Setup**: Safe to restart - database won't be recreated

## Resources
- [Official Documentation](https://listmonk.app/docs/)
- [Docker Installation Guide](https://listmonk.app/docs/installation/)
- [API Documentation](https://listmonk.app/docs/apis/)
- [GitHub Repository](https://github.com/knadh/listmonk)
