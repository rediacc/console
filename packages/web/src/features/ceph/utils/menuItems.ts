import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { MenuProps } from 'antd';
import { Typography } from 'antd';
import React from 'react';
import {
  DatabaseOutlined,
  ExpandOutlined,
  FunctionOutlined,
  KeyOutlined,
  PlusOutlined,
} from '@/utils/optimizedIcons';

// Helper to create menu labels with consistent data-testid
const createClusterActionLabel = (actionKey: string, label: React.ReactNode) =>
  React.createElement(
    Typography.Text,
    { 'data-testid': `cluster-action-${actionKey.replaceAll('_', '-')}` } as React.ComponentProps<
      typeof Typography.Text
    >,
    label
  );

const createPoolActionLabel = (actionKey: string, label: React.ReactNode) =>
  React.createElement(
    Typography.Text,
    { 'data-testid': `pool-action-${actionKey.replaceAll('_', '-')}` } as React.ComponentProps<
      typeof Typography.Text
    >,
    label
  );

export const buildClusterMenuItems = (t: TypedTFunction): MenuProps['items'] => [
  {
    key: 'status',
    label: createClusterActionLabel('status', t('functions.cluster_status')),
    icon: React.createElement(ExpandOutlined),
  },
  {
    key: 'dashboard',
    label: createClusterActionLabel('dashboard', t('functions.cluster_dashboard')),
    icon: React.createElement(KeyOutlined),
  },
  { type: 'divider' },
  {
    key: 'advanced',
    label: createClusterActionLabel('advanced', t('common:actions.advanced')),
    icon: React.createElement(FunctionOutlined),
  },
];

export const buildPoolMenuItems = (t: TypedTFunction): MenuProps['items'] => [
  {
    key: 'list',
    label: createPoolActionLabel('list', t('functions.pool_list')),
    icon: React.createElement(DatabaseOutlined),
  },
  {
    key: 'image_create',
    label: createPoolActionLabel('image-create', t('functions.image_create')),
    icon: React.createElement(PlusOutlined),
  },
  { type: 'divider' },
  {
    key: 'advanced',
    label: createPoolActionLabel('advanced', t('common:actions.advanced')),
    icon: React.createElement(FunctionOutlined),
  },
];
