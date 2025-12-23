import { DeleteOutlined, EditOutlined, HistoryOutlined } from '@/utils/optimizedIcons';
import type { MenuProps } from 'antd';
import type { TFunction } from 'i18next';

type MenuItem = NonNullable<MenuProps['items']>[number];

/**
 * Builds an edit menu item with EditOutlined icon
 */
export const buildEditMenuItem = (
  t: TFunction<string[]>,
  onClick: () => void,
): MenuItem => ({
  key: 'edit',
  label: t('common:actions.edit'),
  icon: <EditOutlined />,
  onClick,
});

/**
 * Builds a delete menu item with DeleteOutlined icon and danger styling
 */
export const buildDeleteMenuItem = (
  t: TFunction<string[]>,
  onClick: () => void,
): MenuItem => ({
  key: 'delete',
  label: t('common:actions.delete'),
  icon: <DeleteOutlined />,
  danger: true,
  onClick,
});

/**
 * Builds a trace menu item with HistoryOutlined icon
 */
export const buildTraceMenuItem = (
  t: TFunction<string[]>,
  onClick: () => void,
): MenuItem => ({
  key: 'trace',
  label: t('common:actions.trace'),
  icon: <HistoryOutlined />,
  onClick,
});

/**
 * Builds a menu divider
 */
export const buildDivider = (): MenuItem => ({
  type: 'divider' as const,
});
