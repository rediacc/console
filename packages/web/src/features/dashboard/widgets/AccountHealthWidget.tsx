import type { OrganizationDashboardData } from '@rediacc/shared/types';
import { Card, Empty, Flex, Tag, Typography } from 'antd';
import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  SafetyCertificateOutlined,
} from '@/utils/optimizedIcons';

interface AccountHealthWidgetProps {
  accountHealth?: OrganizationDashboardData['accountHealth'];
}

const AccountHealthWidget: React.FC<AccountHealthWidgetProps> = ({ accountHealth }) => {
  const { t } = useTranslation('common');

  if (!accountHealth) {
    return (
      <Card
        data-testid="dashboard-account-health-card"
        title={
          <Flex align="center" wrap className="inline-flex">
            <SafetyCertificateOutlined />
            <Typography.Text>{t('dashboard.widgets.accountHealth.title')}</Typography.Text>
          </Flex>
        }
      >
        <Empty description={t('dashboard.widgets.accountHealth.noData')} />
      </Card>
    );
  }

  return (
    <Card
      data-testid="dashboard-account-health-card"
      title={
        <Flex align="center" wrap className="inline-flex">
          <SafetyCertificateOutlined />
          <Typography.Text>{t('dashboard.widgets.accountHealth.title')}</Typography.Text>
        </Flex>
      }
    >
      <Flex vertical className="w-full">
        <Flex align="center" justify="space-between">
          <Typography.Text>{t('dashboard.widgets.accountHealth.overallStatus')}</Typography.Text>
          <Tag bordered={false}>{accountHealth.subscriptionStatus}</Tag>
        </Flex>

        <Flex vertical className="gap-sm w-full">
          <Flex align="center" wrap className="inline-flex">
            {(accountHealth.resourcesAtLimit ?? 0) > 0 ? (
              <Flex className="inline-flex">
                <ExclamationCircleOutlined />
              </Flex>
            ) : (
              <Flex className="inline-flex">
                <CheckCircleOutlined />
              </Flex>
            )}
            <Typography.Text>
              {accountHealth.resourcesAtLimit}{' '}
              {t('dashboard.widgets.accountHealth.resourcesAtLimit')}
            </Typography.Text>
          </Flex>

          <Flex align="center" wrap className="inline-flex">
            <Flex className="inline-flex">
              <ClockCircleOutlined />
            </Flex>
            <Typography.Text>
              {accountHealth.resourcesNearLimit}{' '}
              {t('dashboard.widgets.accountHealth.resourcesNearLimit')}
            </Typography.Text>
          </Flex>
        </Flex>

        <Flex align="center" justify="space-between" className="w-full">
          <Typography.Text strong>{accountHealth.upgradeRecommendation}</Typography.Text>
        </Flex>
      </Flex>
    </Card>
  );
};

export default AccountHealthWidget;
