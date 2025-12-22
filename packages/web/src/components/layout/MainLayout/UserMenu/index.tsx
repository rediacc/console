import React from 'react';
import { Avatar, Button, Card, Divider, Flex, Segmented, Space, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import LanguageSelector from '@/components/common/LanguageSelector';
import {
  LogoutOutlined,
  SafetyCertificateOutlined,
  SmileOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
import type { CompanyDashboardData } from '@rediacc/shared/types';

type UserMenuProps = {
  user: { email: string } | null;
  company: string | null;
  companyData?: Pick<CompanyDashboardData, 'companyInfo' | 'activeSubscription'>;
  uiMode: 'simple' | 'expert';
  onModeToggle: () => void;
  onLogout: () => void;
};

export const UserMenu: React.FC<UserMenuProps> = ({
  user,
  company,
  companyData,
  uiMode,
  onModeToggle,
  onLogout,
}) => {
  const { t } = useTranslation('common');

  return (
    <Card styles={{ body: { padding: 0 } }}>
      <Flex
        vertical
        // eslint-disable-next-line no-restricted-syntax
        style={{ width: 280 }}
      >
        <Flex align="center" gap={12} wrap data-testid="user-info">
          <Avatar icon={<UserOutlined />} size={48} />
          <Flex vertical className="flex-1 min-w-0">
            <Typography.Text strong className="block" data-testid="user-info-email">
              {user?.email}
            </Typography.Text>
            {company && (
              <Typography.Text type="secondary" className="block" data-testid="user-info-company">
                {company}
              </Typography.Text>
            )}
            {companyData?.activeSubscription && (
              <Tag data-testid="user-info-plan">
                {companyData.activeSubscription.planCode ?? 'UNKNOWN'}
              </Tag>
            )}
          </Flex>
        </Flex>

        <Divider
          // eslint-disable-next-line no-restricted-syntax
          style={{ margin: '12px 0' }}
        />

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

        <Divider
          // eslint-disable-next-line no-restricted-syntax
          style={{ margin: '12px 0' }}
        />

        <Flex vertical>
          <Typography.Text strong className="block">
            {t('language.label')}
          </Typography.Text>
          <LanguageSelector iconOnly={false} />
        </Flex>

        <Divider
          // eslint-disable-next-line no-restricted-syntax
          style={{ margin: '12px 0' }}
        />

        <Button
          type="text"
          danger
          icon={<LogoutOutlined />}
          onClick={onLogout}
          data-testid="main-logout-button"
          // eslint-disable-next-line no-restricted-syntax
          style={{ justifyContent: 'flex-start' }}
          className="w-full"
        >
          {t('navigation.logout')}
        </Button>
      </Flex>
    </Card>
  );
};
