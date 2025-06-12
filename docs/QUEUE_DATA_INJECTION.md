# Queue Data Injection System

## Overview

The Queue Data Injection System automatically enriches queue requests with context-specific data based on function requirements. This ensures that system functions receive all necessary credentials, configurations, and metadata without manual configuration.

## Architecture

### 1. Function Requirements Definition

Each function in `src/data/functions.json` now includes a `requirements` field that specifies what context data it needs:

```json
{
  "os_setup": {
    "name": "os_setup",
    "category": "machine",
    "requirements": {
      "machine": true,
      "team": true,
      "company": true
    },
    "params": { ... }
  }
}
```

### 2. Context Data Types

- **company**: UNIVERSAL_USER_ID, UNIVERSAL_USER_NAME, DOCKER_JSON_CONF, LOG_FILE, SSH_PRIVATE_KEY (base64), SSH_PUBLIC_KEY (base64)
- **team**: Team name, SSH_PRIVATE_KEY (base64), SSH_PUBLIC_KEY (base64)
- **machine**: Machine name, IP, USER, DATASTORE, HOST_ENTRY, ssh_key_configured, SSH_PASSWORD, port
- **repository**: Repository name, size, credential
- **storage**: Storage name and all provider-specific fields (dynamic based on provider)
- **bridge**: Bridge name and any bridge-specific fields
- **plugin**: All plugin data from company vault PLUGINS

### 3. Data Sources

The system pulls data from multiple sources in order of priority:

1. **Entity Vaults**: Direct vault data from the specific entity (machine, repository, etc.)
2. **Company Vault**: Company-wide configurations and credentials

### 4. Components

#### QueueDataService (`src/services/queueDataService.ts`)

Central service that:
- Reads function requirements
- Extracts data from various vault sources
- Builds the final queue vault JSON with all required context

#### useQueueVaultBuilder Hook (`src/hooks/useQueueVaultBuilder.ts`)

React hook that:
- Fetches company vault data
- Provides a `buildQueueVault` function for components
- Handles async data fetching and caching

## Usage

### Basic Usage

```typescript
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder'

function MyComponent() {
  const { buildQueueVault } = useQueueVaultBuilder()
  
  const handleCreateQueueItem = async () => {
    const queueVault = await buildQueueVault({
      teamName: 'MyTeam',
      machineName: 'machine1',
      bridgeName: 'bridge1',
      repositoryName: 'repo1', // Optional, only if function needs it
      functionName: 'repo_mount',
      params: { repo: 'repo1' },
      priority: 3,
      description: 'Mount repository',
      addedVia: 'my-component'
    })
    
    // Use queueVault in createQueueItem mutation
  }
}
```

### Queue Vault Structure

The resulting queue vault JSON contains:

```json
{
  "function": "repo_mount",
  "params": { "repo": "repo1" },
  "priority": 3,
  "description": "Mount repository",
  "addedVia": "my-component",
  "contextData": {
    "company": {
      "UNIVERSAL_USER_ID": "777",
      "UNIVERSAL_USER_NAME": "rediacc",
      "DOCKER_JSON_CONF": { ... },
      "LOG_FILE": "/tmp/rediacc.log",
      "SSH_PRIVATE_KEY": "...",
      "SSH_PUBLIC_KEY": "..."
    },
    "team": {
      "name": "MyTeam",
      "SSH_PRIVATE_KEY": "...",
      "SSH_PUBLIC_KEY": "..."
    },
    "machine": {
      "name": "machine1",
      "IP": "192.168.111.11",
      "USER": "muhammed",
      "DATASTORE": "/mnt/datastore",
      "HOST_ENTRY": "...",
      "ssh_key_configured": true,
      "SSH_PASSWORD": null
    },
    "repository": {
      "name": "repo1",
      "size": "100GB",
      "credential": "BmCL79Kp49oeN{y4%qURMv6YkqC/wBug"
    }
  }
}
```

## Adding New Functions

1. Add the function to `src/data/functions.json` with appropriate requirements:
   ```json
   {
     "my_function": {
       "name": "my_function",
       "category": "machine",
       "requirements": {
         "machine": true,
         "team": true,
         "plugin": true
       },
       "params": { ... }
     }
   }
   ```

2. The system will automatically inject the required data when the function is queued

## Development Mode

In development mode, ensure that vault data is properly configured in the backend for testing the queue data injection system.

## Security Considerations

1. **Sensitive Data**: SSH passwords are never included in the context data
2. **Credentials**: Repository and storage credentials are only included when required
3. **Minification**: All queue vault JSON is minified before sending to reduce size
4. **Access Control**: Data is only included based on user's access to entities

## Future Enhancements

1. **Selective Data Loading**: Currently loads all data upfront; could lazy-load based on requirements
2. **Data Caching**: Implement React Query caching for vault data
3. **Custom Requirements**: Allow functions to specify exactly which fields they need
4. **Validation**: Add validation to ensure all required data is present before queuing