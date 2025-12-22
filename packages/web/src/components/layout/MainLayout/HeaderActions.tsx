import React from 'react';
import { Button, Dropdown, Flex } from 'antd';
import { useSelector } from 'react-redux';
import { useCompanyInfo } from '@/api/queries/dashboard';
import NotificationBell from '@/components/layout/MainLayout/components/NotificationBell';
import { selectCompany, selectUser } from '@/store/auth/authSelectors';
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
  const company = useSelector(selectCompany);
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const themeMode = useSelector((state: RootState) => state.ui.themeMode);
  const { data: companyData } = useCompanyInfo();

  return (
    <Flex align="center" gap={12}>
      <NotificationBell />
      <Dropdown
        trigger={['click']}
        placement="bottomRight"
        dropdownRender={() => (
          <UserMenu
            user={user}
            company={company}
            companyData={companyData}
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
