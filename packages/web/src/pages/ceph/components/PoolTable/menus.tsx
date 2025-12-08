import { DatabaseOutlined, FunctionOutlined, PlusOutlined } from '@/utils/optimizedIcons';
import type { MenuProps } from 'antd';
import type { TFunction } from 'i18next';

export const getPoolFunctionMenuItems = (t: TFunction<'ceph' | 'common'>): MenuProps['items'] => [
  {
    key: 'list',
    label: t('functions.pool_list'),
    icon: <DatabaseOutlined />,
  },
  {
    key: 'image_create',
    label: t('functions.image_create'),
    icon: <PlusOutlined />,
  },
  { type: 'divider' },
  {
    key: 'advanced',
    label: t('common:actions.advanced'),
    icon: <FunctionOutlined />,
  },
];
