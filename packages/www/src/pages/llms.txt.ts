import type { APIRoute } from 'astro';

export const GET: APIRoute = () => {
  const content = `# Rediacc

> Self-hosted infrastructure platform with encrypted repositories, container isolation, and automated disaster recovery.

Rediacc enables you to deploy and manage isolated, encrypted application environments on your own servers. Each repository gets its own Docker daemon, network namespace, and encrypted storage.

## Docs

- [Quick Start](https://www.rediacc.com/en/docs/quick-start.txt): Deploy encrypted infrastructure on your servers in 5 minutes
- [Requirements](https://www.rediacc.com/en/docs/requirements.txt): Supported operating systems and prerequisites
- [Installation](https://www.rediacc.com/en/docs/installation.txt): Install the rdc CLI on Linux, macOS, or Windows
- [Architecture](https://www.rediacc.com/en/docs/architecture.txt): How Rediacc works — modes, security model, Docker isolation, config structure
- [Machine Setup](https://www.rediacc.com/en/docs/setup.txt): Create contexts, add machines, provision servers, configure infrastructure
- [Repositories](https://www.rediacc.com/en/docs/repositories.txt): Create, manage, resize, fork, and validate encrypted repositories
- [Services](https://www.rediacc.com/en/docs/services.txt): Rediaccfiles, service networking, deployment, autostart
- [Networking](https://www.rediacc.com/en/docs/networking.txt): Reverse proxy, Docker labels, TLS certificates, DNS, and port forwarding
- [Backup & Restore](https://www.rediacc.com/en/docs/backup-restore.txt): Back up to external storage, restore, schedule automated backups
- [Tools](https://www.rediacc.com/en/docs/tools.txt): File sync, SSH terminal, VS Code integration, CLI updates
- [Monitoring](https://www.rediacc.com/en/docs/monitoring.txt): Machine health, containers, services, diagnostics
- [Troubleshooting](https://www.rediacc.com/en/docs/troubleshooting.txt): Solutions for common issues
- [Migration Guide](https://www.rediacc.com/en/docs/migration.txt): Bring existing projects into Rediacc repositories

## Use Cases

- [Development Environments](https://www.rediacc.com/en/docs/development-environments.txt): Spin up isolated dev environments in seconds
- [Time Travel Recovery](https://www.rediacc.com/en/docs/time-travel-recovery.txt): Restore any application to any point in time
- [Cross Backup Strategy](https://www.rediacc.com/en/docs/cross-backup.txt): Multi-destination backup with encryption
- [Risk-Free Upgrades](https://www.rediacc.com/en/docs/risk-free-upgrades.txt): Snapshot-based upgrades with instant rollback
- [Dynamic Resource Scaling](https://www.rediacc.com/en/docs/dynamic-resource-scaling.txt): Scale resources across machines
- [Accelerated Development Operations](https://www.rediacc.com/en/docs/zero-cost-backup.txt): Fast backup and restore workflows
- [Legacy Database Scaling](https://www.rediacc.com/en/docs/legacy-database-scaling.txt): Scale legacy databases without application changes
- [Banking Continuity During Blackout](https://www.rediacc.com/en/docs/blackout.txt): Disaster recovery for critical infrastructure

## Optional

- [Full Documentation](https://www.rediacc.com/llms-full.txt): Complete documentation in a single file
`;

  return new Response(content, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
