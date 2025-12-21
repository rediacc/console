import { Flex, Tooltip } from 'antd';
import React from 'react';
import { InfoCircleOutlined } from '@/utils/optimizedIcons';
import type { FieldLabelProps } from '../types';

export const FieldLabel: React.FC<FieldLabelProps> = ({ label, description }) => (
  <Flex align="center" gap={4}>
    {label}
    {description && (
      <Tooltip title={description}>
        <InfoCircleOutlined style={{ fontSize: 12 }} />
      </Tooltip>
    )}
  </Flex>
);
