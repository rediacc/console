/**
 * Action mapping utilities for mapping actions to icons and colors
 */

import type { ElementType } from 'react';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  EditOutlined,
  InfoCircleOutlined,
  LoginOutlined,
  SwapOutlined,
} from '@ant-design/icons';

/**
 * Configuration for action icon and color mapping
 */
export interface ActionConfig {
  keywords: string[];
  icon: ElementType;
  color: string;
}

/**
 * Default action icon mapping configuration
 */
export const ACTION_ICON_MAP: ActionConfig[] = [
  { keywords: ['create'], icon: CheckCircleOutlined, color: 'var(--color-success)' },
  { keywords: ['delete'], icon: CloseCircleOutlined, color: 'var(--color-error)' },
  { keywords: ['update', 'modify'], icon: EditOutlined, color: 'var(--color-warning)' },
  { keywords: ['login', 'auth'], icon: LoginOutlined, color: 'var(--color-primary)' },
  { keywords: ['export', 'import'], icon: SwapOutlined, color: 'var(--color-info)' },
];

/**
 * Default configuration when no match is found
 */
export const DEFAULT_ACTION_CONFIG: Omit<ActionConfig, 'keywords'> = {
  icon: InfoCircleOutlined,
  color: 'var(--color-text-secondary)',
};

/**
 * Find action configuration based on action string
 * @param action - The action string to match
 * @param iconMap - Optional custom icon map (defaults to ACTION_ICON_MAP)
 * @returns Matching action config or default config
 */
export function findActionConfig(
  action: string,
  iconMap: ActionConfig[] = ACTION_ICON_MAP
): Omit<ActionConfig, 'keywords'> {
  const actionLower = action.toLowerCase();
  const config = iconMap.find(({ keywords }) =>
    keywords.some((keyword) => actionLower.includes(keyword))
  );
  return config || DEFAULT_ACTION_CONFIG;
}

/**
 * Get action color for Ant Design Tag component
 * @param action - The action string
 * @returns Color string for Tag component ('success', 'error', 'warning', 'processing', 'default')
 */
export function getActionTagColor(action: string): string {
  const actionLower = action.toLowerCase();
  if (actionLower.includes('create')) return 'success';
  if (actionLower.includes('delete')) return 'error';
  if (actionLower.includes('update') || actionLower.includes('modify')) return 'warning';
  if (actionLower.includes('login') || actionLower.includes('auth')) return 'processing';
  return 'default';
}

/**
 * Get action icon component and color
 * @param action - The action string
 * @returns Object with icon component and color
 */
export function getActionIconAndColor(action: string): { icon: ElementType; color: string } {
  const config = findActionConfig(action);
  return { icon: config.icon, color: config.color };
}
