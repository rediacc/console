import { useMemo } from 'react';
import { MoreOutlined } from '@ant-design/icons';
import { RediaccButton } from '@/components/ui/Button';
import { RediaccTooltip } from '@/components/ui/Tooltip';
import { RediaccDropdown } from './RediaccDropdown';
import type { RediaccActionMenuProps, ActionMenuItem } from './RediaccActionMenu.types';
import type { MenuProps } from 'antd';

/**
 * RediaccActionMenu - Specialized dropdown for table row actions
 *
 * Simplifies the common pattern of action menus in table columns
 * with built-in record context, visibility/disabled functions, and test IDs.
 *
 * @example
 * <RediaccActionMenu
 *   record={row}
 *   items={[
 *     { key: 'edit', label: 'Edit', icon: <EditOutlined />, onClick: handleEdit },
 *     { key: 'delete', label: 'Delete', icon: <DeleteOutlined />, danger: true, onClick: handleDelete },
 *   ]}
 *   testIdPrefix="user-row"
 * />
 */
export function RediaccActionMenu<T>({
  record,
  items,
  icon,
  label,
  buttonVariant = 'default',
  disabled = false,
  loading = false,
  placement = 'bottomRight',
  testIdPrefix,
  tooltip,
  'aria-label': ariaLabel,
}: RediaccActionMenuProps<T>) {
  // Build menu items with record context
  const menuConfig = useMemo((): MenuProps => {
    const handlers: Record<string, (rec: T) => void> = {};
    const menuItems: MenuProps['items'] = [];

    items.forEach((item: ActionMenuItem<T>) => {
      // Check visibility
      const isVisible =
        item.visible === undefined
          ? true
          : typeof item.visible === 'function'
            ? item.visible(record)
            : item.visible;

      if (!isVisible) return;

      // Check disabled
      const isDisabled =
        typeof item.disabled === 'function' ? item.disabled(record) : item.disabled;

      // Store handler reference
      handlers[item.key] = item.onClick;

      // Add menu item
      menuItems.push({
        key: item.key,
        label: item.label,
        icon: item.icon,
        danger: item.danger,
        disabled: isDisabled,
        'data-testid': testIdPrefix ? `${testIdPrefix}-menu-${item.key}` : undefined,
      });

      // Add divider if specified
      if (item.dividerAfter) {
        menuItems.push({ type: 'divider' });
      }
    });

    return {
      items: menuItems,
      onClick: ({ key }) => handlers[key]?.(record),
    };
  }, [items, record, testIdPrefix]);

  // Don't render if no visible items
  if (!menuConfig.items?.length) {
    return null;
  }

  const triggerButton = (
    <RediaccButton
      variant={buttonVariant}
      iconOnly={!label}
      icon={icon || <MoreOutlined />}
      disabled={disabled}
      loading={loading}
      data-testid={testIdPrefix ? `${testIdPrefix}-action-menu` : undefined}
      aria-label={ariaLabel || tooltip || 'Actions'}
    >
      {label}
    </RediaccButton>
  );

  return (
    <RediaccDropdown
      menu={menuConfig}
      trigger={['click']}
      placement={placement}
      disabled={disabled}
    >
      {tooltip ? <RediaccTooltip title={tooltip}>{triggerButton}</RediaccTooltip> : triggerButton}
    </RediaccDropdown>
  );
}

RediaccActionMenu.displayName = 'RediaccActionMenu';
