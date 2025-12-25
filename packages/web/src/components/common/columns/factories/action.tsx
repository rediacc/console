import { DeleteOutlined, EditOutlined, EyeOutlined, MoreOutlined } from '@ant-design/icons';
import { Button, Dropdown, type MenuProps } from 'antd';
import i18n from '@/i18n/config';
import type { ActionColumnOptions, ActionMenuItem } from '../types';
import type { ColumnsType } from 'antd/es/table';

/**
 * Create a reusable actions column with a dropdown menu
 */
export const createActionColumn = <T,>(
  options: ActionColumnOptions<T>
): ColumnsType<T>[number] => ({
  title: options.title ?? i18n.t('common:actionsColumn'),
  key: 'actions',
  width: options.width ?? 120,
  fixed: options.fixed,
  render: (_: unknown, record: T) => {
    if (options.renderActions) {
      return options.renderActions(record);
    }

    const baseItems: ActionMenuItem<T>[] = [];
    if (options.onView) {
      baseItems.push({
        key: 'view',
        label: i18n.t('common:viewDetails'),
        icon: <EyeOutlined />,
        onClick: options.onView,
      });
    }
    if (options.onEdit) {
      baseItems.push({
        key: 'edit',
        label: i18n.t('common:actions.edit'),
        icon: <EditOutlined />,
        onClick: options.onEdit,
      });
    }
    if (options.onDelete) {
      baseItems.push({
        key: 'delete',
        label: i18n.t('common:actions.delete'),
        icon: <DeleteOutlined />,
        danger: true,
        onClick: options.onDelete,
      });
    }

    const extraItems = options.getMenuItems?.(record) ?? [];
    const items = [...baseItems, ...extraItems];

    if (!items.length) {
      return null;
    }

    const handlers: Record<string, (rec: T) => void> = {};
    const menuItems = items.map(({ key, label, icon, danger, onClick }) => {
      handlers[key] = onClick;
      return {
        key,
        label,
        icon,
        danger,
      };
    });

    const menu: MenuProps = {
      items: menuItems,
      onClick: ({ key }) => {
        handlers[key](record);
      },
    };

    return (
      <Dropdown menu={menu} trigger={['click']}>
        <Button icon={options.buttonIcon ?? <MoreOutlined />}>{options.buttonLabel}</Button>
      </Dropdown>
    );
  },
});
