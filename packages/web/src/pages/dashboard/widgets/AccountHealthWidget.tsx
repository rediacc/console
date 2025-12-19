import React from 'react';
import { Empty } from 'antd';
import { RediaccCard, RediaccStack, RediaccTag, RediaccText } from '@/components/ui';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  SafetyCertificateOutlined,
} from '@/utils/optimizedIcons';
import type { CompanyDashboardData } from '@rediacc/shared/types';
import { FlexBetween, InlineStack, SectionFooter, StatusIcon } from '../styles';

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
      <RediaccCard
        fullWidth
        data-testid="dashboard-account-health-card"
        title={
          <InlineStack>
            <SafetyCertificateOutlined />
            <span>Account Health</span>
          </InlineStack>
        }
      >
        <Empty description="No account health data available" />
      </RediaccCard>
    );
  }

  return (
    <RediaccCard
      fullWidth
      data-testid="dashboard-account-health-card"
      title={
        <InlineStack>
          <SafetyCertificateOutlined />
          <span>Account Health</span>
        </InlineStack>
      }
    >
      <RediaccStack direction="vertical" gap="md" fullWidth>
        <FlexBetween>
          <RediaccText>Overall Status</RediaccText>
          <RediaccTag variant={STATUS_TYPE_MAP[accountHealth.subscriptionStatus] || 'success'}>
            {accountHealth.subscriptionStatus}
          </RediaccTag>
        </FlexBetween>

        <RediaccStack direction="vertical" gap="sm" fullWidth>
          <InlineStack>
            {accountHealth.resourcesAtLimit > 0 ? (
              <StatusIcon $variant="warning">
                <ExclamationCircleOutlined />
              </StatusIcon>
            ) : (
              <StatusIcon $variant="success">
                <CheckCircleOutlined />
              </StatusIcon>
            )}
            <RediaccText>{accountHealth.resourcesAtLimit} resources at limit</RediaccText>
          </InlineStack>

          <InlineStack>
            <StatusIcon $variant="secondary">
              <ClockCircleOutlined />
            </StatusIcon>
            <RediaccText>{accountHealth.resourcesNearLimit} resources near limit</RediaccText>
          </InlineStack>
        </RediaccStack>

        <SectionFooter>
          <RediaccText weight="bold">{accountHealth.upgradeRecommendation}</RediaccText>
        </SectionFooter>
      </RediaccStack>
    </RediaccCard>
  );
};

export default AccountHealthWidget;
