import { ExpandOutlined, FunctionOutlined, KeyOutlined } from '@/utils/optimizedIcons';
import type { MenuProps } from 'antd';
import type { TFunction } from 'i18next';

export const getClusterFunctionMenuItems = (
  t: TFunction<'ceph' | 'common' | 'machines'>
): MenuProps['items'] => [
  {
    key: 'status',
    label: t('functions.cluster_status'),
    icon: <ExpandOutlined />,
  },
  {
    key: 'dashboard',
    label: t('functions.cluster_dashboard'),
    icon: <KeyOutlined />,
  },
  { type: 'divider' },
  {
    key: 'advanced',
    label: t('common:actions.advanced'),
    icon: <FunctionOutlined />,
  },
];
