# GitLab CE (Community Edition) Template

Self-hosted Git repository manager with CI/CD, issue tracking, and more.

## Features
- Web-based Git repository management with built-in CI/CD pipelines
- Issue tracking, project management, and wiki documentation
- Container registry and merge request workflows
- Persistent storage for repositories, configs, and logs
- Minimum 4GB RAM required (8GB recommended)

## Usage
```bash
source Rediaccfile
prep  # Pull images and create directories
up    # Start GitLab CE
down  # Stop and cleanup
```

**Initial Setup:**
1. Wait 5-10 minutes for first-time initialization
2. Get root password: `docker exec -it gitlab grep 'Password:' /etc/gitlab/initial_root_password`
3. Login at http://localhost with username `root`
4. Change password immediately

## Configuration
Edit `.env` to customize:
- `CONTAINER_NAME`: Container name (default: gitlab)
- `GITLAB_HOSTNAME`: Hostname for GitLab (default: localhost)
- `GITLAB_HTTP_PORT`: HTTP port (default: 80)
- `GITLAB_HTTPS_PORT`: HTTPS port (default: 443)
- `GITLAB_SSH_PORT`: SSH port for Git operations (default: 2222)
- `GITLAB_OMNIBUS_CONFIG`: Additional Omnibus configuration (see docs)

**Common Configuration Examples:**
```bash
# Enable container registry
GITLAB_OMNIBUS_CONFIG="registry_external_url 'http://localhost:5000'; gitlab_rails['registry_enabled'] = true;"

# Reduce memory usage
GITLAB_OMNIBUS_CONFIG="postgresql['shared_buffers'] = '256MB'; sidekiq['concurrency'] = 5; prometheus_monitoring['enable'] = false;"
```

## Access
- **Web Interface**: http://localhost (or configured HTTP port)
- **Default username**: root
- **Initial password**: See `./config/initial_root_password` or extract via docker exec
- **Git SSH**: `git clone ssh://git@localhost:2222/username/project.git`
- **Git HTTP**: `git clone http://localhost/username/project.git`
- **Find ports**: `docker compose ps`

**Quick Commands:**
```bash
# Create backup
docker exec -t gitlab gitlab-backup create

# Monitor logs
docker logs -f gitlab

# Access GitLab Rails console
docker exec -it gitlab gitlab-rails console
```

## Resources
- [Official Docker Hub](https://hub.docker.com/r/gitlab/gitlab-ce)
- [Official Documentation](https://docs.gitlab.com/ee/install/docker.html)
- [GitLab Runner Setup](https://docs.gitlab.com/runner/install/docker.html)
- [Omnibus Configuration](https://docs.gitlab.com/omnibus/settings/)