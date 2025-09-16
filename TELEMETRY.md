# Rediacc Console Telemetry Implementation

## Overview

The Rediacc Console includes comprehensive OpenTelemetry-based telemetry to monitor user behavior, application performance, and system health. This telemetry system sends data to `obs.rediacc.com` for analysis and insights.

## What Data is Collected

### ✅ Data We Collect
- **Page views and navigation patterns**
- **User interactions** (clicks, form submissions, tab changes)
- **API request performance** (response times, success/failure rates)
- **Application performance metrics** (page load times, component render times)
- **Error events and exceptions**
- **Feature usage patterns**
- **Browser and system information** (browser type, screen resolution, viewport size)
- **Session information** (session duration, user flow)

### ❌ Data We DON'T Collect
- **Passwords or authentication tokens**
- **Vault contents or encrypted data**
- **SSH keys or sensitive credentials**
- **Personal identifiable information beyond email domain**
- **Actual file contents or repository data**

## Technical Implementation

### Core Components

1. **TelemetryService** (`src/services/telemetryService.ts`)
   - Main service managing OpenTelemetry SDK
   - Configures exporters, instrumentation, and sampling
   - Handles endpoint detection and environment configuration

2. **TelemetryProvider** (`src/components/common/TelemetryProvider.tsx`)
   - React context provider for telemetry throughout the app
   - Automatic page view tracking
   - Global error handling
   - Performance monitoring integration

3. **API Client Instrumentation** (`src/api/client.ts`)
   - Automatic tracking of all API requests
   - Request/response timing and status code monitoring
   - Error tracking for failed API calls

4. **Custom Hooks** (`src/hooks/useTelemetryTracking.ts`)
   - Convenient methods for tracking specific application events
   - Resource management tracking
   - Queue operations monitoring
   - Form interaction tracking

### Dependencies Added

```json
{
  "@opentelemetry/api": "^1.9.0",
  "@opentelemetry/exporter-otlp-http": "^0.54.0",
  "@opentelemetry/instrumentation": "^0.54.0",
  "@opentelemetry/instrumentation-fetch": "^0.54.0",
  "@opentelemetry/instrumentation-user-interaction": "^0.40.0",
  "@opentelemetry/instrumentation-xml-http-request": "^0.54.0",
  "@opentelemetry/resources": "^1.26.0",
  "@opentelemetry/sdk-web": "^1.26.0",
  "@opentelemetry/semantic-conventions": "^1.27.0"
}
```

## Usage Examples

### Basic Event Tracking

```typescript
import { useTelemetry } from '@/components/common/TelemetryProvider'

const MyComponent = () => {
  const { trackEvent, trackUserAction } = useTelemetry()

  const handleButtonClick = () => {
    trackUserAction('button_click', 'create_machine_button')
    // ... handle click
  }

  const handleDataExport = () => {
    trackEvent('data.export', {
      'export.type': 'machines',
      'export.format': 'csv',
      'export.record_count': 150
    })
    // ... handle export
  }

  return (
    <button onClick={handleButtonClick}>
      Create Machine
    </button>
  )
}
```

### Resource Management Tracking

```typescript
import { useTelemetryTracking } from '@/hooks/useTelemetryTracking'

const MachineManagement = () => {
  const { trackResourceCreation, trackResourceDeletion } = useTelemetryTracking()

  const createMachine = async (machineData) => {
    try {
      const result = await apiClient.post('/CreateMachine', machineData)
      trackResourceCreation('machine', machineData.name)
      return result
    } catch (error) {
      trackErrorWithContext(error, {
        component: 'MachineManagement',
        action: 'create',
        resourceType: 'machine'
      })
      throw error
    }
  }

  const deleteMachine = async (machineName) => {
    await apiClient.delete('/DeleteMachine', { name: machineName })
    trackResourceDeletion('machine', machineName)
  }
}
```

### Performance Tracking

```typescript
import { useTelemetry } from '@/components/common/TelemetryProvider'

const DataTable = () => {
  const { measureAndTrack } = useTelemetry()

  const loadData = async () => {
    return measureAndTrack('table.load.machines', async () => {
      const response = await apiClient.get('/GetMachines')
      return response.data
    })
  }

  return (
    // ... table component
  )
}
```

### Component Lifecycle Tracking

```typescript
import { useComponentTelemetry } from '@/components/common/TelemetryProvider'

const ImportantComponent = () => {
  useComponentTelemetry('ImportantComponent')

  return (
    // ... component content
  )
}
```

## Configuration

### Environment Detection

The telemetry service automatically detects the appropriate observability endpoint:

- **Development**: Uses `obs.rediacc.com` or attempts to construct obs subdomain from current domain
- **Production**: Uses `obs.{current-domain}` (e.g., `obs.mydomain.com`)

### Sampling Rates

- **Development**: 100% sampling for complete debugging
- **Production**: 10% sampling to balance insights with performance

### User Consent

Currently set to enabled by default. Future implementation should include:
- User consent UI in settings
- Opt-out capability
- Privacy policy integration

## Data Destinations

### Primary Endpoint
- **URL**: `https://www.rediacc.com/otlp`
- **Protocol**: OTLP over HTTP
- **Format**: JSON

### Observability Stack
- **Grafana**: Dashboards and visualization
- **Prometheus**: Metrics storage and querying
- **Loki**: Log aggregation
- **Tempo**: Distributed tracing
- **Pyroscope**: Continuous profiling

## Privacy and Security

### Data Minimization
- Only collect data necessary for improving user experience
- No personally identifiable information beyond email domain
- No sensitive application data (passwords, keys, vault contents)

### Data Retention
- Follows obs.rediacc.com retention policy (30 days by default)
- Data automatically expires and is purged

### Security Measures
- HTTPS-only transport
- No authentication tokens in telemetry
- Sanitized error messages
- No user input content tracking

## Development and Testing

### Running with Telemetry

```bash
# Start development server with telemetry enabled
./go dev

# Start in sandbox mode (also includes telemetry)
./go sandbox
```

### Disabling Telemetry for Development

To disable telemetry during development, modify the configuration in `TelemetryService`:

```typescript
// In createTelemetryConfig()
return {
  // ... other config
  enabledInDevelopment: false, // Set to false to disable
}
```

### Viewing Telemetry Data

1. Navigate to `https://obs.rediacc.com`
2. Login with Grafana credentials (admin/admin for development)
3. Explore dashboards for:
   - Application performance
   - User behavior analytics
   - Error tracking
   - API performance metrics

## Troubleshooting

### Common Issues

1. **Telemetry not sending data**
   - Check browser network tab for OTLP requests to obs.rediacc.com
   - Verify obs.rediacc.com is accessible
   - Check console for telemetry initialization errors

2. **High network usage**
   - Adjust sampling rate in production
   - Review batch size and export interval settings

3. **Performance impact**
   - Telemetry uses background processing
   - Minimal impact with proper batching
   - Consider reducing instrumentation scope if needed

### Debug Mode

Enable verbose telemetry logging:

```typescript
// In browser console
localStorage.setItem('telemetry-debug', 'true')
// Reload page to see detailed telemetry logs
```

## Future Enhancements

### Planned Features
1. **User Consent Management**
   - Settings page integration
   - Granular consent options
   - Privacy policy integration

2. **Custom Dashboards**
   - Role-based analytics
   - Team-specific insights
   - Feature adoption tracking

3. **Real-time Monitoring**
   - Live user session tracking
   - Real-time error alerting
   - Performance threshold monitoring

4. **A/B Testing Integration**
   - Feature flag tracking
   - Experiment result tracking
   - Conversion funnel analysis

## Contributing

When adding new features to the console:

1. **Add appropriate telemetry tracking** for new user interactions
2. **Use existing hooks** (`useTelemetryTracking`) for common patterns
3. **Track performance** for new heavy operations
4. **Add error tracking** for new error conditions
5. **Update this documentation** for new telemetry patterns

### Example Pull Request Telemetry Checklist

- [ ] Added click tracking for new buttons/actions
- [ ] Added form submission tracking for new forms
- [ ] Added performance tracking for new API calls
- [ ] Added error tracking for new error scenarios
- [ ] Added feature access tracking for new pages/features
- [ ] Verified no sensitive data is tracked
- [ ] Updated telemetry documentation if needed

## Contact

For questions about telemetry implementation or data usage:
- Technical questions: Check the code comments and this documentation
- Privacy concerns: Review the privacy policy and data collection sections
- Data access requests: Contact your system administrator