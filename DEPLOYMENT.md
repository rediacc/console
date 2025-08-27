# Rediacc Console - Deployment Guide

This guide covers various deployment options for the open-source Rediacc Console.

## Table of Contents
- [Build Configuration](#build-configuration)
- [Static Hosting](#static-hosting)
- [Docker Deployment](#docker-deployment)
- [Self-Hosted with Nginx](#self-hosted-with-nginx)
- [CDN Deployment](#cdn-deployment)
- [Environment Configuration](#environment-configuration)

## Build Configuration

### Building for Open-Source (with Sandbox Fallback)
```bash
# For development/open-source with sandbox fallback
REDIACC_BUILD_TYPE=DEBUG npm run build
```

### Building for Production (Own Backend)
```bash
# For production with your own backend
REDIACC_BUILD_TYPE=RELEASE npm run build
```

The build output will be in the `dist/` directory.

## Static Hosting

The Rediacc Console is a static SPA that can be hosted on any static file hosting service.

### GitHub Pages

1. Build the console:
```bash
REDIACC_BUILD_TYPE=DEBUG npm run build
```

2. Install gh-pages:
```bash
npm install --save-dev gh-pages
```

3. Add to package.json:
```json
{
  "scripts": {
    "deploy": "gh-pages -d dist"
  }
}
```

4. Deploy:
```bash
npm run deploy
```

### Netlify

1. Build the console locally or use Netlify's build system

2. Create `netlify.toml`:
```toml
[build]
  command = "REDIACC_BUILD_TYPE=DEBUG npm run build"
  publish = "dist"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

3. Deploy via Netlify CLI or GitHub integration

### Vercel

1. Create `vercel.json`:
```json
{
  "buildCommand": "REDIACC_BUILD_TYPE=DEBUG npm run build",
  "outputDirectory": "dist",
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

2. Deploy:
```bash
vercel
```

### AWS S3 + CloudFront

1. Build the console:
```bash
REDIACC_BUILD_TYPE=DEBUG npm run build
```

2. Upload to S3:
```bash
aws s3 sync dist/ s3://your-bucket-name --delete
```

3. Configure S3 bucket for static website hosting

4. Set up CloudFront distribution with custom error pages for SPA routing

## Docker Deployment

### Using the Standalone Dockerfile

1. Build the Docker image:
```bash
docker build -f Dockerfile.standalone -t rediacc-console .
```

2. Run the container:
```bash
# For development/sandbox mode
docker run -p 80:80 \
  -e REDIACC_BUILD_TYPE=DEBUG \
  rediacc-console

# For production with your backend
docker run -p 80:80 \
  -e REDIACC_BUILD_TYPE=RELEASE \
  -e API_URL=https://your-backend.com/api \
  rediacc-console
```

### Docker Compose

Create `docker-compose.yml`:
```yaml
version: '3.8'

services:
  console:
    build:
      context: .
      dockerfile: Dockerfile.standalone
      args:
        REDIACC_BUILD_TYPE: DEBUG
    ports:
      - "80:80"
    environment:
      - INSTANCE_NAME=opensource
      - ENABLE_DEBUG=false
```

Run:
```bash
docker-compose up -d
```

## Self-Hosted with Nginx

### Basic Setup

1. Build the console:
```bash
REDIACC_BUILD_TYPE=DEBUG npm run build
```

2. Copy files to web server:
```bash
sudo cp -r dist/* /usr/share/nginx/html/
```

3. Use the provided nginx configuration:
```bash
sudo cp nginx.example.conf /etc/nginx/sites-available/rediacc-console
sudo ln -s /etc/nginx/sites-available/rediacc-console /etc/nginx/sites-enabled/
sudo nginx -s reload
```

### With SSL/TLS

1. Install certbot:
```bash
sudo apt-get install certbot python3-certbot-nginx
```

2. Obtain certificate:
```bash
sudo certbot --nginx -d your-domain.com
```

3. Update nginx configuration with SSL settings (see nginx.example.conf)

### With Custom Backend

If you have your own backend API:

1. Build in RELEASE mode:
```bash
REDIACC_BUILD_TYPE=RELEASE npm run build
```

2. Update nginx configuration to proxy `/api` to your backend:
```nginx
location /api/ {
    proxy_pass http://your-backend:7322;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## CDN Deployment

### CloudFlare Pages

1. Connect your GitHub repository to CloudFlare Pages

2. Configure build settings:
   - Build command: `REDIACC_BUILD_TYPE=DEBUG npm run build`
   - Build output directory: `dist`

3. Add environment variable:
   - `NODE_VERSION`: `18`

### Azure Static Web Apps

1. Create `staticwebapp.config.json`:
```json
{
  "navigationFallback": {
    "rewrite": "/index.html"
  },
  "routes": [
    {
      "route": "/*",
      "serve": "/index.html",
      "statusCode": 200
    }
  ]
}
```

2. Deploy via Azure CLI or GitHub Actions

## Environment Configuration

### Runtime Configuration

You can modify `public/config.js` after build to change runtime settings:

```javascript
window.REDIACC_CONFIG = {
  instanceName: 'production',
  apiUrl: 'https://api.your-domain.com',
  enableDebug: 'false',
  buildType: 'RELEASE'
};
```

### Build-Time Variables

Set these before building:

- `REDIACC_BUILD_TYPE`: `DEBUG` or `RELEASE`
- `VITE_APP_VERSION`: Version string
- `SANDBOX_API_URL`: Custom sandbox URL (optional)

### Security Considerations

For production deployments:

1. **Always use RELEASE mode** for production to prevent sandbox connections
2. **Enable HTTPS** for all production deployments
3. **Set security headers** (CSP, HSTS, etc.) in your web server
4. **Restrict CORS** if hosting your own backend
5. **Use environment-specific config.js** files

## Troubleshooting

### Console Not Loading

1. Check browser console for errors
2. Verify `config.js` is accessible at `/config.js`
3. Ensure SPA routing is configured (all routes → index.html)

### API Connection Issues

1. Check the endpoint displayed on login page
2. Verify CORS headers if using custom backend
3. For DEBUG mode, ensure sandbox is accessible
4. For RELEASE mode, ensure `/api` proxy is configured

### Build Issues

1. Clear node_modules and reinstall:
```bash
rm -rf node_modules package-lock.json
npm install
```

2. Clear build cache:
```bash
rm -rf dist node_modules/.vite
```

3. Verify Node.js version (v18+)

## Support

For deployment issues:
- Open an issue on [GitHub](https://github.com/rediacc/console/issues)
- Check existing [discussions](https://github.com/rediacc/console/discussions)
- Review the [FAQ](https://docs.rediacc.com/console/faq)