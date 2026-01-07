/**
 * Centralized status color mappings for consistent UI across the application.
 * Use these instead of inline switch statements or local functions.
 */

// =============================================================================
// Queue Item Status Colors
// =============================================================================

const QUEUE_STATUS_COLORS: Record<string, string> = {
  pending: 'blue',
  assigned: 'cyan',
  processing: 'orange',
  completed: 'green',
  failed: 'red',
  cancelled: 'default',
  cancelling: 'orange',
};

/**
 * Get the tag color for a queue item status.
 * @example <Tag color={getQueueStatusColor(item.status)}>{item.status}</Tag>
 */
export const getQueueStatusColor = (status: string): string =>
  QUEUE_STATUS_COLORS[status.toLowerCase()] ?? 'default';

// =============================================================================
// Container State Colors
// =============================================================================

const CONTAINER_STATE_COLORS: Record<string, string> = {
  running: 'success',
  paused: 'warning',
  restarting: 'processing',
  exited: 'default',
  created: 'blue',
  dead: 'red',
};

/**
 * Get the tag color for a container state.
 * @example <Tag color={getContainerStateColor(container.state)}>{container.state}</Tag>
 */
export const getContainerStateColor = (state: string): string =>
  CONTAINER_STATE_COLORS[state.toLowerCase()] ?? 'default';
