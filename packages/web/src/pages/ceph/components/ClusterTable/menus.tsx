import { ExpandOutlined, FunctionOutlined, KeyOutlined } from '@/utils/optimizedIcons';
import type { MenuProps } from 'antd';
import type { TFunction } from 'i18next';

// Helper to create menu labels with consistent data-testid
const createActionLabel = (actionKey: string, label: React.ReactNode) => (
  <span data-testid={`cluster-action-${actionKey.replace(/_/g, '-')}`}>{label}</span>
);

export const getClusterFunctionMenuItems = (
  t: TFunction<'ceph' | 'common' | 'machines'>
): MenuProps['items'] => [
  {
    key: 'status',
    label: createActionLabel('status', t('functions.cluster_status')),
    icon: <ExpandOutlined />,
  },
  {
    key: 'dashboard',
    label: createActionLabel('dashboard', t('functions.cluster_dashboard')),
    icon: <KeyOutlined />,
  },
  { type: 'divider' },
  {
    key: 'advanced',
    label: createActionLabel('advanced', t('common:actions.advanced')),
    icon: <FunctionOutlined />,
  },
];
