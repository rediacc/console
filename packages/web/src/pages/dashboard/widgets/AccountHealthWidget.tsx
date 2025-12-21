import React from 'react';
import { Card, Empty, Flex, Tag, Typography } from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  SafetyCertificateOutlined,
} from '@/utils/optimizedIcons';
import type { CompanyDashboardData } from '@rediacc/shared/types';

const STATUS_TYPE_MAP: Record<string, 'success' | 'warning' | 'error'> = {
  Critical: 'error',
  Warning: 'warning',
  Good: 'success',
};

interface AccountHealthWidgetProps {
  accountHealth?: CompanyDashboardData['accountHealth'];
}

const AccountHealthWidget: React.FC<AccountHealthWidgetProps> = ({ accountHealth }) => {
  if (!accountHealth) {
    return (
      <Card
        data-testid="dashboard-account-health-card"
        title={
          <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
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
        <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
          <SafetyCertificateOutlined />
          <Typography.Text>Account Health</Typography.Text>
        </Flex>
      }
    >
      <Flex vertical gap={16} style={{ width: '100%' }}>
        <Flex align="center" justify="space-between">
          <Typography.Text>Overall Status</Typography.Text>
          <Tag
            bordered={false}
            color={STATUS_TYPE_MAP[accountHealth.subscriptionStatus] || 'success'}
          >
            {accountHealth.subscriptionStatus}
          </Tag>
        </Flex>

        <Flex vertical gap={8} style={{ width: '100%' }}>
          <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
            {accountHealth.resourcesAtLimit > 0 ? (
              <Flex style={{ color: 'var(--ant-color-warning)', display: 'inline-flex' }}>
                <ExclamationCircleOutlined />
              </Flex>
            ) : (
              <Flex style={{ color: 'var(--ant-color-success)', display: 'inline-flex' }}>
                <CheckCircleOutlined />
              </Flex>
            )}
            <Typography.Text>{accountHealth.resourcesAtLimit} resources at limit</Typography.Text>
          </Flex>

          <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
            <Flex style={{ color: 'var(--ant-color-text-secondary)', display: 'inline-flex' }}>
              <ClockCircleOutlined />
            </Flex>
            <Typography.Text>
              {accountHealth.resourcesNearLimit} resources near limit
            </Typography.Text>
          </Flex>
        </Flex>

        <Flex align="center" justify="space-between" style={{ width: '100%' }}>
          <Typography.Text strong>{accountHealth.upgradeRecommendation}</Typography.Text>
        </Flex>
      </Flex>
    </Card>
  );
};

export default AccountHealthWidget;
