import {
  DeleteOutlined,
  EditOutlined,
  HistoryOutlined,
  KeyOutlined,
  SafetyOutlined,
  SyncOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { MenuProps } from 'antd';

type MenuItem = NonNullable<MenuProps['items']>[number];

/**
 * Builds an edit menu item with EditOutlined icon
 */
export const buildEditMenuItem = (t: TypedTFunction, onClick: () => void): MenuItem => ({
  key: 'edit',
  label: t('common:actions.edit'),
  icon: <EditOutlined />,
  onClick,
});

/**
 * Builds a delete menu item with DeleteOutlined icon and danger styling
 */
export const buildDeleteMenuItem = (t: TypedTFunction, onClick: () => void): MenuItem => ({
  key: 'delete',
  label: t('common:actions.delete'),
  icon: <DeleteOutlined />,
  danger: true,
  onClick,
});

/**
 * Builds a trace menu item with HistoryOutlined icon
 */
export const buildTraceMenuItem = (t: TypedTFunction, onClick: () => void): MenuItem => ({
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

/**
 * Builds a permissions menu item with SafetyOutlined icon
 */
export const buildPermissionsMenuItem = (t: TypedTFunction, onClick: () => void): MenuItem => ({
  key: 'permissions',
  label: t('system:actions.permissions'),
  icon: <SafetyOutlined />,
  onClick,
});

/**
 * Builds a members menu item with UserOutlined icon
 */
export const buildMembersMenuItem = (t: TypedTFunction, onClick: () => void): MenuItem => ({
  key: 'members',
  label: t('system:actions.members'),
  icon: <UserOutlined />,
  onClick,
});

/**
 * Builds a token menu item with KeyOutlined icon
 */
export const buildTokenMenuItem = (t: TypedTFunction, onClick: () => void): MenuItem => ({
  key: 'token',
  label: t('system:actions.token'),
  icon: <KeyOutlined />,
  onClick,
});

/**
 * Builds a reset auth menu item with SyncOutlined icon
 */
export const buildResetAuthMenuItem = (t: TypedTFunction, onClick: () => void): MenuItem => ({
  key: 'resetAuth',
  label: t('system:actions.resetAuth'),
  icon: <SyncOutlined />,
  onClick,
});
