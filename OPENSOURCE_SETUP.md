# Open Source Setup Guide

## Environment Configuration

The Rediacc Console supports multiple deployment modes through the `REDIACC_BUILD_TYPE` environment variable.

### Build Types

#### DEBUG Mode (Development & Open Source Contributors)
- Attempts to connect to localhost backend first
- Automatically falls back to sandbox.rediacc.com if localhost is unavailable
- Shows warning when using sandbox environment
- Ideal for developers and open-source contributors

```bash
# Run in debug mode (default)
npm run dev

# Or explicitly set
REDIACC_BUILD_TYPE=DEBUG npm run dev
```

#### RELEASE Mode (Production Deployments)
- Uses `/api` endpoint from the same domain
- **NEVER** connects to sandbox (security feature)
- For production deployments on your own infrastructure
- Ensures data stays within your organization

```bash
# Build for production (uses same-domain /api)
REDIACC_BUILD_TYPE=RELEASE npm run build

# Production deployment will use its own backend at /api
```

### Endpoint Selection

The console performs a health check on startup to determine the best endpoint:

1. **DEBUG Mode Flow:**
   - Check if localhost:7322 is accessible (3-second timeout)
   - If successful → Use localhost
   - If failed → Fall back to sandbox.rediacc.com (with warning)
   
2. **RELEASE Mode Flow:**
   - Always use `/api` from same domain
   - No health checks or fallbacks
   - Ensures production security

### Viewing Active Endpoint

The currently active endpoint is displayed on the login page:
- Shows above the version number
- Indicates "Local Development", "Production", or "Sandbox Environment (DEBUG)"
- Warning icon appears when using sandbox in DEBUG mode

### Custom Sandbox URL

You can specify a custom sandbox URL if needed:

```bash
SANDBOX_API_URL=https://custom-sandbox.example.com/api npm run dev
```

### Example Configurations

#### For Open Source Contributors
```bash
# Develop with automatic fallback to sandbox
REDIACC_BUILD_TYPE=DEBUG npm run dev
# Will try localhost first, fallback to sandbox if needed
```

#### For Local Development (with backend)
```bash
# Ensure your local backend is running on port 7322
# Then run the console in debug mode
REDIACC_BUILD_TYPE=DEBUG npm run dev
# Will connect to localhost:7322
```

#### For Production Deployments
```bash
# Build for production deployment
REDIACC_BUILD_TYPE=RELEASE npm run build
# Will use /api from same domain (e.g., yourcompany.com/api)
```

#### For Testing Production Build Locally
```bash
# Build and preview production build
REDIACC_BUILD_TYPE=RELEASE npm run build
npm run preview
# Note: Will try to use /api which may not work locally
```

### Console Output

During startup, you'll see console messages indicating the connection status:

**DEBUG Mode with localhost:**
```
[API Connection] Build type: DEBUG
[API Connection] DEBUG mode: Checking localhost availability...
[API Connection] ✓ Using localhost endpoint
[API] Connected to: Local Development (http://localhost:7322/api)
```

**DEBUG Mode with sandbox fallback:**
```
[API Connection] Build type: DEBUG
[API Connection] DEBUG mode: Checking localhost availability...
[API Connection] ⚠️  NOTICE: Localhost unavailable, using sandbox environment
[API Connection] ⚠️  This is only suitable for development/testing, not production
[API Connection] ✓ Using sandbox endpoint (DEBUG mode fallback)
[API] Connected to: Sandbox Environment (DEBUG) (https://sandbox.rediacc.com/api)
```

**RELEASE Mode (Production):**
```
[API Connection] Build type: RELEASE
[API Connection] Using production endpoint (same domain /api)
[API] Connected to: Production (/api)
```

### Troubleshooting

1. **Localhost not detected in DEBUG mode:**
   - Ensure your backend is running on the correct port (default: 7322)
   - Check firewall settings
   - Verify the backend health endpoint is accessible

2. **Want to use sandbox without local backend (open-source):**
   - Use `REDIACC_BUILD_TYPE=DEBUG` (default)
   - The console will automatically fallback to sandbox

3. **Production deployment connecting to wrong backend:**
   - Ensure `REDIACC_BUILD_TYPE=RELEASE` is set during build
   - Verify your nginx/proxy configuration serves the backend at `/api`

4. **Custom port for localhost:**
   - Set `VITE_HTTP_PORT=<your-port>`
   - Example: `VITE_HTTP_PORT=8080 npm run dev`

### Security Note

**IMPORTANT:** The RELEASE build type is designed for production deployments and will ONLY connect to `/api` on the same domain. This ensures that production data never leaves your infrastructure. The sandbox fallback is ONLY available in DEBUG mode for development purposes.