# Cloudflare Tunnel Template

Secure tunnel to expose local services via Cloudflare with demo Flask application.

## Features
- Cloudflare tunnel (cloudflared) integration for secure remote access
- QUIC protocol optimization with UDP buffer tuning
- Demo Flask web application with SQLite database
- Automated tunnel creation, DNS routing, and cleanup
- Auto-polling web interface with real-time data display

## Usage
```bash
source Rediaccfile
./tunnel.sh setup  # One-time: Authenticate with Cloudflare
prep               # Configure UDP buffers, build image, create tunnel
up                 # Start Flask application
down               # Stop services and cleanup tunnel
```

## Configuration
Set environment variable before running:
- `CLOUDFLARE_TUNNEL_HOST`: Domain for tunnel (default: demo.rediacc.com)

Example:
```bash
export CLOUDFLARE_TUNNEL_HOST="myapp.example.com"
```

The tunnel automatically:
- Creates unique tunnel per hostname
- Configures DNS routing
- Proxies to local Flask app on port 5000

## Access
- **Service Port**: 5000 (internal, accessed via Cloudflare tunnel URL)
- **Tunnel URL**: https://[CLOUDFLARE_TUNNEL_HOST]
- **Authentication**: Requires Cloudflare account (configured during `setup`)
- **View tunnel status**: `docker ps` (look for cloudflared containers)

## Resources
- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [cloudflared Docker Hub](https://hub.docker.com/r/cloudflare/cloudflared)
- [QUIC Protocol UDP Optimization](https://github.com/quic-go/quic-go/wiki/UDP-Buffer-Sizes)