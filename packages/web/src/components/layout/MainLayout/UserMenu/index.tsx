import React from 'react';
import { Avatar, Button, Card, Divider, Flex, Segmented, Space, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import LanguageSelector from '@/components/common/LanguageSelector';
import type { ThemeMode } from '@/store/ui/uiSlice';
import {
  LogoutOutlined,
  MoonOutlined,
  SafetyCertificateOutlined,
  SmileOutlined,
  SunOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
import type { OrganizationDashboardData } from '@rediacc/shared/types';

type UserMenuProps = {
  user: { email: string } | null;
  organization: string | null;
  organizationData?: Pick<OrganizationDashboardData, 'organizationInfo' | 'activeSubscription'>;
  uiMode: 'simple' | 'expert';
  themeMode: ThemeMode;
  onModeToggle: () => void;
  onThemeToggle: () => void;
  onLogout: () => void;
};

export const UserMenu: React.FC<UserMenuProps> = ({
  user,
  organization,
  organizationData,
  uiMode,
  themeMode,
  onModeToggle,
  onThemeToggle,
  onLogout,
}) => {
  const { t } = useTranslation('common');

  return (
    <Card>
      <Flex vertical className="w-280">
        <Flex align="center" wrap data-testid="user-info">
          <Avatar icon={<UserOutlined />} size={48} />
          <Flex vertical className="flex-1 min-w-0">
            <Typography.Text strong className="block" data-testid="user-info-email">
              {user?.email}
            </Typography.Text>
            {organization && (
              <Typography.Text
                type="secondary"
                className="block"
                data-testid="user-info-organization"
              >
                {organization}
              </Typography.Text>
            )}
            {organizationData?.activeSubscription && (
              <Tag data-testid="user-info-plan">
                {organizationData.activeSubscription.planCode ?? 'UNKNOWN'}
              </Tag>
            )}
          </Flex>
        </Flex>

        <Divider className="my-3" />

        <Flex vertical>
          <Typography.Text type="secondary">{t('uiMode.label')}</Typography.Text>
          <Segmented
            block
            value={uiMode}
            onChange={(value) => {
              if (value !== uiMode) {
                onModeToggle();
              }
            }}
            options={[
              {
                label: (
                  <Space size={4}>
                    <SmileOutlined />
                    <Typography.Text>{t('uiMode.simple')}</Typography.Text>
                  </Space>
                ),
                value: 'simple',
              },
              {
                label: (
                  <Space size={4}>
                    <SafetyCertificateOutlined />
                    <Typography.Text>{t('uiMode.expert')}</Typography.Text>
                  </Space>
                ),
                value: 'expert',
              },
            ]}
            data-testid="main-mode-toggle"
          />
        </Flex>

        <Divider className="my-3" />

        <Flex vertical>
          <Typography.Text type="secondary">{t('theme.label')}</Typography.Text>
          <Segmented
            block
            value={themeMode}
            onChange={(value) => {
              if (value !== themeMode) {
                onThemeToggle();
              }
            }}
            options={[
              {
                label: (
                  <Space size={4}>
                    <SunOutlined />
                    <Typography.Text>{t('theme.light')}</Typography.Text>
                  </Space>
                ),
                value: 'light',
              },
              {
                label: (
                  <Space size={4}>
                    <MoonOutlined />
                    <Typography.Text>{t('theme.dark')}</Typography.Text>
                  </Space>
                ),
                value: 'dark',
              },
            ]}
            data-testid="main-theme-toggle"
          />
        </Flex>

        <Divider className="my-3" />

        <Flex vertical>
          <Typography.Text strong className="block">
            {t('language.label')}
          </Typography.Text>
          <LanguageSelector iconOnly={false} />
        </Flex>

        <Divider className="my-3" />

        <Button
          type="text"
          danger
          icon={<LogoutOutlined />}
          onClick={onLogout}
          data-testid="main-logout-button"
          className="w-full justify-start"
        >
          {t('navigation.logout')}
        </Button>
      </Flex>
    </Card>
  );
};
