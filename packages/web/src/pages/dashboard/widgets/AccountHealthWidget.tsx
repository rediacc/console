import React from 'react';
import { Card, Empty, Flex, Tag, Typography } from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  SafetyCertificateOutlined,
} from '@/utils/optimizedIcons';
import type { CompanyDashboardData } from '@rediacc/shared/types';

interface AccountHealthWidgetProps {
  accountHealth?: CompanyDashboardData['accountHealth'];
}

const AccountHealthWidget: React.FC<AccountHealthWidgetProps> = ({ accountHealth }) => {
  if (!accountHealth) {
    return (
      <Card
        data-testid="dashboard-account-health-card"
        title={
          <Flex align="center" gap={8} wrap className="inline-flex">
            <SafetyCertificateOutlined />
            <Typography.Text>Account Health</Typography.Text>
          </Flex>
        }
      >
        <Empty description="No account health data available" />
      </Card>
    );
  }

  return (
    <Card
      data-testid="dashboard-account-health-card"
      title={
        <Flex align="center" gap={8} wrap className="inline-flex">
          <SafetyCertificateOutlined />
          <Typography.Text>Account Health</Typography.Text>
        </Flex>
      }
    >
      <Flex vertical gap={16} className="w-full">
        <Flex align="center" justify="space-between">
          <Typography.Text>Overall Status</Typography.Text>
          <Tag bordered={false}>{accountHealth.subscriptionStatus}</Tag>
        </Flex>

        <Flex vertical gap={8} className="w-full">
          <Flex align="center" gap={8} wrap className="inline-flex">
            {accountHealth.resourcesAtLimit > 0 ? (
              <Flex className="inline-flex">
                <ExclamationCircleOutlined />
              </Flex>
            ) : (
              <Flex className="inline-flex">
                <CheckCircleOutlined />
              </Flex>
            )}
            <Typography.Text>{accountHealth.resourcesAtLimit} resources at limit</Typography.Text>
          </Flex>

          <Flex align="center" gap={8} wrap className="inline-flex">
            <Flex className="inline-flex">
              <ClockCircleOutlined />
            </Flex>
            <Typography.Text>
              {accountHealth.resourcesNearLimit} resources near limit
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
