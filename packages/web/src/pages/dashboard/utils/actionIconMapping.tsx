import React from 'react';
import { Flex } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  EditOutlined,
  InfoCircleOutlined,
  LoginOutlined,
  SwapOutlined,
} from '@/utils/optimizedIcons';

interface ActionIconConfig {
  Icon: React.ComponentType;
}

const ACTION_ICON_MAP = new Map<string, ActionIconConfig>([
  ['create', { Icon: CheckCircleOutlined }],
  ['delete', { Icon: CloseCircleOutlined }],
  ['update', { Icon: EditOutlined }],
  ['modify', { Icon: EditOutlined }],
  ['login', { Icon: LoginOutlined }],
  ['auth', { Icon: LoginOutlined }],
  ['export', { Icon: SwapOutlined }],
  ['import', { Icon: SwapOutlined }],
]);

const DEFAULT_ICON_CONFIG: ActionIconConfig = {
  Icon: InfoCircleOutlined,
};

export const getActionIcon = (action: string): React.ReactNode => {
  const actionLower = action.toLowerCase();

  for (const [keyword, config] of ACTION_ICON_MAP) {
    if (actionLower.includes(keyword)) {
      const { Icon } = config;
      return (
        <Flex className="inline-flex">
          <Icon />
        </Flex>
      );
    }
  }

  const { Icon } = DEFAULT_ICON_CONFIG;
  return (
    <Flex className="inline-flex">
      <Icon />
    </Flex>
  );
};
