import React from 'react';
import { RediaccTooltip } from '@/components/ui';
import { FieldInfoIcon, FieldLabelStack } from '../styles';
import type { FieldLabelProps } from '../types';

export const FieldLabel: React.FC<FieldLabelProps> = ({ label, description }) => (
  <FieldLabelStack>
    {label}
    {description && (
      <RediaccTooltip title={description}>
        <FieldInfoIcon />
      </RediaccTooltip>
    )}
  </FieldLabelStack>
);
