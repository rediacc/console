import { useCallback } from 'react'
import { useTelemetry, useInteractionTracking } from '@/components/common/TelemetryProvider'

type TelemetryAttributes = Record<string, string | number | boolean | null | undefined>

const mapAttributes = (prefix: string, details?: TelemetryAttributes) =>
  Object.fromEntries(
    Object.entries(details ?? {}).map(([key, value]) => [`${prefix}.${key}`, String(value)])
  )

/**
 * Custom hook for common telemetry tracking patterns
 * Provides convenient methods for tracking user interactions across the app
 */
export const useTelemetryTracking = () => {
  const { trackEvent, trackError, trackPerformance } = useTelemetry()
  const interactions = useInteractionTracking()

  // Resource management tracking
  const trackResourceAction = useCallback((action: string, resourceType: string, resourceName?: string) => {
    trackEvent('resource.action', {
      'resource.action': action,
      'resource.type': resourceType,
      'resource.name': resourceName || 'unknown',
    })
  }, [trackEvent])

  const trackResourceCreation = useCallback((resourceType: string, resourceName: string) => {
    trackResourceAction('create', resourceType, resourceName)
  }, [trackResourceAction])

  const trackResourceUpdate = useCallback((resourceType: string, resourceName: string) => {
    trackResourceAction('update', resourceType, resourceName)
  }, [trackResourceAction])

  const trackResourceDeletion = useCallback((resourceType: string, resourceName: string) => {
    trackResourceAction('delete', resourceType, resourceName)
  }, [trackResourceAction])

  // Queue operations tracking
  const trackQueueAction = useCallback((action: string, details?: TelemetryAttributes) => {
    trackEvent('queue.action', {
      'queue.action': action,
      ...mapAttributes('queue', details),
    })
  }, [trackEvent])

  const trackQueueItemSubmission = useCallback((functionName: string, priority: number) => {
    trackQueueAction('submit', {
      function: functionName,
      priority,
    })
  }, [trackQueueAction])

  const trackQueueMonitoring = useCallback((itemCount: number, filterType?: string) => {
    trackQueueAction('monitor', {
      item_count: itemCount,
      filter_type: filterType || 'all',
    })
  }, [trackQueueAction])

  // Navigation and UI tracking
  const trackFeatureAccess = useCallback((featureName: string) => {
    trackEvent('feature.access', {
      'feature.name': featureName,
    })
  }, [trackEvent])

  const trackDataExport = useCallback((exportType: string, recordCount: number, format: string) => {
    trackEvent('data.export', {
      'export.type': exportType,
      'export.record_count': recordCount,
      'export.format': format,
    })
  }, [trackEvent])

  const trackDataImport = useCallback((importType: string, recordCount: number, success: boolean) => {
    trackEvent('data.import', {
      'import.type': importType,
      'import.record_count': recordCount,
      'import.success': success,
    })
  }, [trackEvent])

  // Settings and configuration tracking
  const trackSettingsChange = useCallback((settingCategory: string, settingName: string, newValue: string) => {
    trackEvent('settings.change', {
      'settings.category': settingCategory,
      'settings.name': settingName,
      'settings.value_type': typeof newValue,
    })
  }, [trackEvent])

  // Performance and usage tracking
  const trackTableOperation = useCallback((operation: string, tableName: string, recordCount: number, duration?: number) => {
    trackEvent('table.operation', {
      'table.operation': operation,
      'table.name': tableName,
      'table.record_count': recordCount,
    })

    if (duration !== undefined) {
      trackPerformance(`table.${operation}.${tableName}`, duration)
    }
  }, [trackEvent, trackPerformance])

  const trackFormInteraction = useCallback((formName: string, action: string, fieldName?: string) => {
    trackEvent('form.interaction', {
      'form.name': formName,
      'form.action': action,
      'form.field': fieldName || 'unknown',
    })
  }, [trackEvent])

  // Audit and security tracking
  const trackAuditAccess = useCallback((auditType: string, resourceType?: string) => {
    trackEvent('audit.access', {
      'audit.type': auditType,
      'audit.resource_type': resourceType || 'unknown',
    })
  }, [trackEvent])

  const trackSecurityAction = useCallback((action: string, details?: TelemetryAttributes) => {
    trackEvent('security.action', {
      'security.action': action,
      ...mapAttributes('security', details),
    })
  }, [trackEvent])

  // Distributed storage tracking
  const trackStorageOperation = useCallback((operation: string, details?: TelemetryAttributes) => {
    trackEvent('storage.operation', {
      'storage.operation': operation,
      ...mapAttributes('storage', details),
    })
  }, [trackEvent])

  // Error tracking with context
  const trackErrorWithContext = useCallback((error: Error, context: {
    component?: string
    action?: string
    resourceType?: string
    resourceName?: string
    additionalContext?: TelemetryAttributes
  }) => {
    trackError(error, {
      component: context.component || 'unknown',
      action: context.action || 'unknown',
      resource_type: context.resourceType || 'unknown',
      resource_name: context.resourceName || 'unknown',
      ...context.additionalContext,
    })
  }, [trackError])

  return {
    // Resource management
    trackResourceCreation,
    trackResourceUpdate,
    trackResourceDeletion,

    // Queue operations
    trackQueueItemSubmission,
    trackQueueMonitoring,

    // Navigation and features
    trackFeatureAccess,

    // Data operations
    trackDataExport,
    trackDataImport,

    // Settings
    trackSettingsChange,

    // Performance
    trackTableOperation,

    // Forms
    trackFormInteraction,

    // Audit and security
    trackAuditAccess,
    trackSecurityAction,

    // Storage
    trackStorageOperation,

    // Error tracking
    trackErrorWithContext,

    // Direct access to interaction tracking
    ...interactions,
  }
}

export default useTelemetryTracking
