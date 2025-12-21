import React from 'react';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  EditOutlined,
  InfoCircleOutlined,
  LoginOutlined,
  SwapOutlined,
} from '@/utils/optimizedIcons';

type ActionIconColor = 'success' | 'error' | 'warning' | 'info' | 'primary' | 'textSecondary';

interface ActionIconConfig {
  color: ActionIconColor;
  Icon: React.ComponentType;
}

const ACTION_ICON_MAP = new Map<string, ActionIconConfig>([
  ['create', { color: 'success', Icon: CheckCircleOutlined }],
  ['delete', { color: 'error', Icon: CloseCircleOutlined }],
  ['update', { color: 'warning', Icon: EditOutlined }],
  ['modify', { color: 'warning', Icon: EditOutlined }],
  ['login', { color: 'info', Icon: LoginOutlined }],
  ['auth', { color: 'info', Icon: LoginOutlined }],
  ['export', { color: 'primary', Icon: SwapOutlined }],
  ['import', { color: 'primary', Icon: SwapOutlined }],
]);

const DEFAULT_ICON_CONFIG: ActionIconConfig = {
  color: 'textSecondary',
  Icon: InfoCircleOutlined,
};

export const getActionIcon = (action: string): React.ReactNode => {
  const actionLower = action.toLowerCase();

  for (const [keyword, config] of ACTION_ICON_MAP) {
    if (actionLower.includes(keyword)) {
      const { color, Icon } = config;
      return (
        <span
          style={{
            display: 'inline-flex',
            color:
              color === 'success'
                ? 'var(--ant-color-success)'
                : color === 'error'
                  ? 'var(--ant-color-error)'
                  : color === 'warning'
                    ? 'var(--ant-color-warning)'
                    : color === 'info'
                      ? 'var(--ant-color-info)'
                      : color === 'primary'
                        ? 'var(--ant-color-primary)'
                        : 'var(--ant-color-text-secondary)',
          }}
        >
          <Icon />
        </span>
      );
    }
  }

  const { color, Icon } = DEFAULT_ICON_CONFIG;
  return (
    <span
      style={{
        display: 'inline-flex',
        color:
          color === 'success'
            ? 'var(--ant-color-success)'
            : color === 'error'
              ? 'var(--ant-color-error)'
              : color === 'warning'
                ? 'var(--ant-color-warning)'
                : color === 'info'
                  ? 'var(--ant-color-info)'
                  : color === 'primary'
                    ? 'var(--ant-color-primary)'
                    : 'var(--ant-color-text-secondary)',
      }}
    >
      <Icon />
    </span>
  );
};
