import React from 'react';
import { Tooltip } from 'antd';
import { FieldInfoIcon, FieldLabelStack } from '../styles';
import type { FieldLabelProps } from '../types';

export const FieldLabel: React.FC<FieldLabelProps> = ({ label, description }) => (
  <FieldLabelStack>
    {label}
    {description && (
      <Tooltip title={description}>
        <FieldInfoIcon />
      </Tooltip>
    )}
  </FieldLabelStack>
);
