# Docker Mailserver

Production-ready fullstack mail server with SMTP, IMAP, anti-spam, and anti-virus protection using configuration files.

## Features
- Complete mail stack: Postfix (SMTP), Dovecot (IMAP), Rspamd (anti-spam), ClamAV (anti-virus)
- File-based configuration with no database required
- Built-in Fail2Ban for brute-force protection
- SSL/TLS encryption support
- LDAP authentication support (optional)

## Usage
```bash
source Rediaccfile
prep  # Pull image and create directories
up    # Start mail server (auto-creates admin account on first run)
down  # Stop and cleanup
```

### First Run - Automatic Admin Account
On first run, an admin mail account is automatically created:
- **Email**: `admin@your-domain.com` (based on HOSTNAME in .env)
- **Password**: Random 16-character password
- **Credentials**: Saved to `./docker-data/dms/admin-credentials.txt`

**Important**: Change this password after first login for security!

## Configuration
Edit `.env` to customize:
- `HOSTNAME`: Your mail server hostname (required - e.g., mail.example.com)
- Security features enabled by default (Rspamd, ClamAV, Fail2Ban)

## Access
- **SMTP Ports**: 25, 465, 587 (standard mail ports - fixed)
- **IMAP Port**: 993 (IMAPS)
- **Note**: Standard mail protocol ports are fixed and cannot be changed

## Important Setup Requirements
Before using in production:
1. **Configure hostname** in `.env` to match your domain (e.g., mail.example.com)
2. **Start the server** - Admin account is auto-created on first run
3. **Change default password** - Find credentials in `./docker-data/dms/admin-credentials.txt`
4. **Setup DNS records**: SPF, DKIM, DMARC for your domain
5. **Configure SSL/TLS certificates** for secure mail delivery
6. **Generate DKIM keys** for email authentication

### Managing Mail Accounts

**Quick Management with tool.sh:**
```bash
# View auto-generated admin credentials
cat ./docker-data/dms/admin-credentials.txt

# Add additional mail accounts
./tool.sh email add user@example.com password123

# Change a password
./tool.sh email update admin@example.com newpassword

# List all accounts
./tool.sh email list

# Delete an account
./tool.sh email del user@example.com

# Add email alias
./tool.sh alias add info@example.com admin@example.com

# Set mailbox quota
./tool.sh quota set user@example.com 2G

# Generate DKIM keys (required for production)
./tool.sh config dkim

# Show all available commands
./tool.sh help
```

**Alternative - Direct docker exec:**
```bash
docker exec -it mailserver setup email add user@example.com
docker exec -it mailserver setup email list
docker exec -it mailserver setup config dkim
```

## Important Notes
- **Auto-Generated Admin**: First run creates `admin@your-domain.com` with random password
- **Credentials File**: `./docker-data/dms/admin-credentials.txt` (change password after first login!)
- **Fixed Ports**: Mail protocols require standard ports (25, 465, 587, 993)
- **One Instance Per Machine**: Due to port requirements, only one mail server can run per machine
- **NET_ADMIN Capability**: Required for Fail2Ban functionality
- **Data Persistence**: All mail data, state, logs, and config stored in `./docker-data/dms/`
- **Production Deployment**: Requires proper DNS, SSL/TLS, and configuration - see official docs

## Resources
- [Official Documentation](https://docker-mailserver.github.io/docker-mailserver/latest/)
- [Basic Installation Guide](https://docker-mailserver.github.io/docker-mailserver/latest/examples/tutorials/basic-installation/)
- [Docker Hub](https://hub.docker.com/r/mailserver/docker-mailserver)
