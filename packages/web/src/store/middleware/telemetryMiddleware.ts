import { telemetryService } from '@/services/telemetryService';
import type { RootState } from '@/store/store';
import type { Middleware, UnknownAction } from '@reduxjs/toolkit';

// Actions to track for business intelligence
const TRACKED_ACTIONS = [
  // Authentication actions
  'auth/loginSuccess',
  'auth/logout',
  'auth/updateOrganization',

  // UI actions
  'ui/toggleUiMode',
  'ui/setTheme',

  // Notification actions
  'notifications/addNotification',

  // Machine assignment actions (Ceph)
  'machineAssignment/assignMachine',
  'machineAssignment/validateSelectedMachines',
  'machineAssignment/clearAssignments',
] as const;

// Actions that indicate feature usage
const FEATURE_USAGE_ACTIONS = [
  'machineAssignment/assignMachine',
  'machineAssignment/validateSelectedMachines',
  'ui/toggleUiMode',
] as const;

// Actions that indicate user preferences
const PREFERENCE_ACTIONS = ['ui/setTheme', 'ui/toggleUiMode'] as const;

// Actions that indicate workflow progression
const WORKFLOW_ACTIONS = [
  'auth/loginSuccess',
  'machineAssignment/assignMachine',
  'machineAssignment/validateSelectedMachines',
] as const;

interface TelemetryMiddlewareOptions {
  enabled?: boolean;
  debugMode?: boolean;
}

type TelemetryEventPayload = Record<string, string | number | boolean>;

interface TelemetryWindow extends Window {
  sessionStartTime?: number;
}

const createTelemetryMiddleware = (
  options: TelemetryMiddlewareOptions = {}
): Middleware<object, RootState> => {
  const { enabled = true, debugMode = false } = options;

  return (store) => (next) => (action) => {
    const typedAction = action as UnknownAction & { payload?: unknown };
    if (!enabled) {
      return next(action);
    }

    const startTime = performance.now();
    const stateBefore = store.getState();

    // Execute the action
    const result = next(action);

    const stateAfter = store.getState();
    const duration = performance.now() - startTime;

    // Skip actions that are too frequent or not business-relevant
    if (shouldTrackAction(typedAction.type)) {
      try {
        // Track basic action execution
        telemetryService.trackEvent('redux.action_dispatched', {
          'typedAction.type': typedAction.type,
          'action.duration_ms': duration,
          'action.has_payload': !!typedAction.payload,
          'redux.state_size': JSON.stringify(stateAfter).length,
          'page.url': window.location.pathname,
        });

        // Track feature usage
        if ((FEATURE_USAGE_ACTIONS as readonly string[]).includes(typedAction.type)) {
          trackFeatureUsage(action as UnknownAction);
        }

        // Track user preferences
        if ((PREFERENCE_ACTIONS as readonly string[]).includes(typedAction.type)) {
          trackUserPreferences(action as UnknownAction, stateBefore, stateAfter);
        }

        // Track workflow progression
        if ((WORKFLOW_ACTIONS as readonly string[]).includes(typedAction.type)) {
          trackWorkflowProgression(action as UnknownAction, stateAfter);
        }

        // Track specific business actions
        trackBusinessActions(action as UnknownAction, stateBefore, stateAfter);

        if (debugMode) {
          console.warn('Telemetry tracked action:', typedAction.type, {
            duration,
            hasPayload: !!typedAction.payload,
          });
        }
      } catch (error) {
        // Don't let telemetry errors break the app
        console.warn('Telemetry middleware error:', error);
      }
    }

    return result;
  };
};

function shouldTrackAction(actionType: string): boolean {
  // Skip high-frequency actions that aren't business-relevant
  const skipActions = [
    '@@INIT',
    '@@redux',
    'persist/',
    '_REHYDRATE',
    '_PERSIST',
    '_PURGE',
    '_REGISTER',
  ];

  return (
    !skipActions.some((skip) => actionType.includes(skip)) &&
    (TRACKED_ACTIONS as readonly string[]).includes(actionType)
  );
}

function trackFeatureUsage(action: UnknownAction): void {
  const actionWithPayload = action as UnknownAction & { payload?: unknown };
  telemetryService.trackEvent('feature.usage', {
    'feature.name': extractFeatureName(action.type),
    'feature.action': action.type,
    'feature.has_data': !!actionWithPayload.payload,
    'usage.timestamp': Date.now(),
  });
}

function trackUserPreferences(
  action: UnknownAction,
  stateBefore: RootState,
  stateAfter: RootState
): void {
  const preferences: Record<string, string> = {};

  if (action.type === 'ui/setTheme') {
    const actionWithPayload = action as UnknownAction & { payload?: string };
    preferences['ui.theme'] = actionWithPayload.payload ?? 'unknown';
  }

  if (action.type === 'ui/toggleUiMode') {
    preferences['ui.mode'] = stateAfter.ui.uiMode;
    preferences['ui.mode_switched_from'] = stateBefore.ui.uiMode;
  }

  telemetryService.trackEvent('user.preferences_updated', {
    'preference.action': action.type,
    ...Object.fromEntries(
      Object.entries(preferences).map(([key, value]) => [`preference.${key}`, value])
    ),
  });
}

function trackWorkflowProgression(action: UnknownAction, stateAfter: RootState): void {
  let workflowData: TelemetryEventPayload = {
    'workflow.action': action.type,
    'workflow.timestamp': Date.now(),
  };

  switch (action.type) {
    case 'auth/loginSuccess':
      workflowData = {
        ...workflowData,
        'workflow.name': 'authentication',
        'workflow.step': 'login_completed',
        'user.organization': stateAfter.auth.organization ?? 'unknown',
      };
      break;

    case 'machineAssignment/assignMachine':
      workflowData = {
        ...workflowData,
        'workflow.name': 'machine_assignment',
        'workflow.step': 'machine_assigned',
        'machine.count': stateAfter.machineAssignment.selectedMachines.length,
      };
      break;

    case 'machineAssignment/validateSelectedMachines':
      workflowData = {
        ...workflowData,
        'workflow.name': 'machine_assignment',
        'workflow.step': 'validation_requested',
      };
      break;
  }

  telemetryService.trackEvent('workflow.progression', workflowData);
}

function trackBusinessActions(
  action: UnknownAction,
  stateBefore: RootState,
  stateAfter: RootState
): void {
  const typedAction = action as UnknownAction & { payload?: Record<string, unknown> };
  switch (action.type) {
    case 'auth/loginSuccess':
      telemetryService.trackEvent('business.user_session_start', {
        'session.organization': String(typedAction.payload?.organization ?? 'unknown'),
        'session.has_encryption': !!typedAction.payload?.organizationEncryptionEnabled,
        'auth.method': 'standard',
      });
      break;

    case 'auth/logout': {
      const sessionStartTime = (window as TelemetryWindow).sessionStartTime ?? Date.now();
      const sessionDuration = Date.now() - sessionStartTime;
      telemetryService.trackEvent('business.user_session_end', {
        'session.duration_ms': sessionDuration,
        'session.organization': stateBefore.auth.organization ?? 'unknown',
      });
      break;
    }

    case 'notifications/addNotification':
      telemetryService.trackEvent('business.notification_created', {
        'notification.type': String(typedAction.payload?.type ?? 'unknown'),
        'notification.has_title': !!typedAction.payload?.title,
        'ux.notification_frequency': getNotificationCount(stateAfter),
      });
      break;

    case 'machineAssignment/assignMachine':
      telemetryService.trackEvent('business.machine_assignment', {
        'machine.id': String(typedAction.payload?.id ?? 'unknown'),
        'assignment.pool_type': String(typedAction.payload?.poolType ?? 'unknown'),
        'assignment.total_assigned': stateAfter.machineAssignment.selectedMachines.length,
      });
      break;
  }
}

function extractFeatureName(actionType: string): string {
  // Extract feature name from action type
  const parts = actionType.split('/');
  return parts[0] || 'unknown';
}

function getNotificationCount(state: RootState): number {
  return state.notifications.notifications.length;
}

// Create the default telemetry middleware
export const telemetryMiddleware = createTelemetryMiddleware({
  enabled: true,
  debugMode: import.meta.env.DEV,
});
