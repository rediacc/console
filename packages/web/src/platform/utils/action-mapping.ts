/**
 * Action mapping utilities for mapping actions to icons and colors
 */

import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  EditOutlined,
  InfoCircleOutlined,
  LoginOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import type { ElementType } from 'react';

/**
 * Configuration for action icon mapping
 */
interface ActionConfig {
  keywords: string[];
  icon: ElementType;
}

/**
 * Default action icon mapping configuration
 */
const ACTION_ICON_MAP: ActionConfig[] = [
  { keywords: ['create'], icon: CheckCircleOutlined },
  { keywords: ['delete'], icon: CloseCircleOutlined },
  { keywords: ['update', 'modify'], icon: EditOutlined },
  { keywords: ['login', 'auth'], icon: LoginOutlined },
  { keywords: ['export', 'import'], icon: SwapOutlined },
];

/**
 * Default configuration when no match is found
 */
const DEFAULT_ACTION_CONFIG: Omit<ActionConfig, 'keywords'> = {
  icon: InfoCircleOutlined,
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
  return config ?? DEFAULT_ACTION_CONFIG;
}
