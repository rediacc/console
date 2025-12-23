import { Button, Dropdown, type MenuProps } from 'antd';
import { MoreOutlined } from '@/utils/optimizedIcons';

interface ResourceActionsDropdownProps {
  menuItems: MenuProps['items'];
  isLoading?: boolean;
}

export function ResourceActionsDropdown({ menuItems, isLoading }: ResourceActionsDropdownProps) {
  return (
    <Dropdown menu={{ items: menuItems }} trigger={['click']} placement="bottomRight">
      <Button
        type="text"
        size="small"
        icon={<MoreOutlined />}
        onClick={(e) => e.stopPropagation()}
        aria-label="Actions"
        loading={isLoading}
      />
    </Dropdown>
  );
}
