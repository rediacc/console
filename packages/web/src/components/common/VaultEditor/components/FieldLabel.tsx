import React from 'react';
import { Flex, Tooltip } from 'antd';
import { InfoCircleOutlined } from '@/utils/optimizedIcons';
import type { FieldLabelProps } from '../types';

export const FieldLabel: React.FC<FieldLabelProps> = ({ label, description }) => {
  return (
    <Flex align="center">
      {label}
      {description && (
        <Tooltip title={description}>
          <InfoCircleOutlined className="text-xs" />
        </Tooltip>
      )}
    </Flex>
  );
};
