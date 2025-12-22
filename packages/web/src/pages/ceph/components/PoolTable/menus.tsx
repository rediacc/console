import { Typography } from 'antd';
import { DatabaseOutlined, FunctionOutlined, PlusOutlined } from '@/utils/optimizedIcons';
import type { MenuProps } from 'antd';
import type { TFunction } from 'i18next';

// Helper to create menu labels with consistent data-testid
const createActionLabel = (actionKey: string, label: React.ReactNode) => (
  <Typography.Text data-testid={`pool-action-${actionKey.replace(/_/g, '-')}`}>
    {label}
  </Typography.Text>
);

export const getPoolFunctionMenuItems = (t: TFunction<'ceph' | 'common'>): MenuProps['items'] => [
  {
    key: 'list',
    label: createActionLabel('list', t('functions.pool_list')),
    icon: <DatabaseOutlined />,
  },
  {
    key: 'image_create',
    label: createActionLabel('image-create', t('functions.image_create')),
    icon: <PlusOutlined />,
  },
  { type: 'divider' },
  {
    key: 'advanced',
    label: createActionLabel('advanced', t('common:actions.advanced')),
    icon: <FunctionOutlined />,
  },
];
