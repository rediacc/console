import { Button, Dropdown, Flex } from 'antd';
import React from 'react';
import { useSelector } from 'react-redux';
import { useOrganizationInfo } from '@/api/hooks-organization';
import NotificationBell from '@/components/layout/MainLayout/components/NotificationBell';
import { selectOrganization, selectUser } from '@/store/auth/authSelectors';
import { RootState } from '@/store/store';
import { UserOutlined } from '@/utils/optimizedIcons';
import { UserMenu } from './UserMenu';

type HeaderActionsProps = {
  onModeToggle: () => void;
  onThemeToggle: () => void;
  onLogout: () => void;
};

export const HeaderActions: React.FC<HeaderActionsProps> = ({
  onModeToggle,
  onThemeToggle,
  onLogout,
}) => {
  const user = useSelector(selectUser);
  const organization = useSelector(selectOrganization);
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const themeMode = useSelector((state: RootState) => state.ui.themeMode);
  const { data: organizationData } = useOrganizationInfo();

  return (
    <Flex align="center">
      <NotificationBell />
      <Dropdown
        trigger={['click']}
        placement="bottomRight"
        popupRender={() => (
          <UserMenu
            user={user}
            organization={organization}
            organizationData={organizationData}
            uiMode={uiMode}
            themeMode={themeMode}
            onModeToggle={onModeToggle}
            onThemeToggle={onThemeToggle}
            onLogout={onLogout}
          />
        )}
        overlayStyle={{ minWidth: 300 }}
      >
        <Button type="text" icon={<UserOutlined />} data-testid="user-menu-button" />
      </Dropdown>
    </Flex>
  );
};
