import type { MenuProps } from 'antd'
import type { TFunction } from 'i18next'
import {
  ExpandOutlined,
  KeyOutlined,
  FunctionOutlined,
} from '@/utils/optimizedIcons'

export const getClusterFunctionMenuItems = (
  t: TFunction<'distributedStorage' | 'common' | 'machines'>,
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
]
