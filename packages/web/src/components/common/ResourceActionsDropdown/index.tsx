import { Button, Dropdown, type MenuProps } from 'antd';
import { useTranslation } from 'react-i18next';
import { MoreOutlined } from '@/utils/optimizedIcons';

interface ResourceActionsDropdownProps {
  menuItems: MenuProps['items'];
  isLoading?: boolean;
}

export function ResourceActionsDropdown({ menuItems, isLoading }: ResourceActionsDropdownProps) {
  const { t } = useTranslation('common');

  return (
    <Dropdown menu={{ items: menuItems }} trigger={['click']} placement="bottomRight">
      <Button
        type="text"
        size="small"
        icon={<MoreOutlined />}
        onClick={(e) => e.stopPropagation()}
        aria-label={t('actions.actions')}
        loading={isLoading}
      />
    </Dropdown>
  );
}
