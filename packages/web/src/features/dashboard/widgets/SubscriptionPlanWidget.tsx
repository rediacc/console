import React from 'react';
import {
  Badge,
  Card,
  Col,
  Empty,
  Flex,
  Progress,
  Row,
  Statistic,
  Tag,
  Tooltip,
  Typography,
  theme,
} from 'antd';
import { useTranslation } from 'react-i18next';
import { CrownOutlined } from '@/utils/optimizedIcons';
import type { CompanyDashboardData } from '@rediacc/shared/types';

const CRITICAL_DAYS_THRESHOLD = 30;

interface SubscriptionPlanWidgetProps {
  activeSubscription?: CompanyDashboardData['activeSubscription'];
  allActiveSubscriptions: CompanyDashboardData['allActiveSubscriptions'];
  planLimits?: CompanyDashboardData['planLimits'];
}

const SubscriptionPlanWidget: React.FC<SubscriptionPlanWidgetProps> = ({
  activeSubscription,
  allActiveSubscriptions,
  planLimits,
}) => {
  const { t } = useTranslation('system');
  const { token } = theme.useToken();

  return (
    <Card
      title={
        <Flex align="center" gap={8} wrap className="inline-flex">
          <CrownOutlined />
          <Typography.Text>
            Subscription & Plan Details - {planLimits?.planCode ?? 'N/A'}
          </Typography.Text>
          {allActiveSubscriptions && allActiveSubscriptions.length > 0 && (
            <Badge count={allActiveSubscriptions.length} />
          )}
        </Flex>
      }
      data-testid="dashboard-card-subscription-plans"
    >
      <Row gutter={[24, 24]}>
        <Col xs={24} md={allActiveSubscriptions && allActiveSubscriptions.length > 0 ? 12 : 24}>
          {activeSubscription ? (
            <Flex vertical gap={16} className="w-full">
              <Flex vertical>
                <Flex className="block">
                  <Typography.Text>CURRENT SUBSCRIPTION</Typography.Text>
                </Flex>
                <Typography.Title level={4}>{activeSubscription.planCode}</Typography.Title>
                <Row gutter={[16, 16]}>
                  <Col span={12}>
                    <Statistic
                      title={t('dashboard.activeLicenses')}
                      value={activeSubscription.totalActivePurchases ?? undefined}
                      data-testid="dashboard-stat-active-licenses"
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      title={t('dashboard.daysRemaining')}
                      value={activeSubscription.daysRemaining ?? undefined}
                      valueStyle={
                        (activeSubscription.daysRemaining ?? 0) <= CRITICAL_DAYS_THRESHOLD
                          ? { color: token.colorError }
                          : undefined
                      }
                      data-testid="dashboard-stat-days-remaining"
                    />
                  </Col>
                </Row>
              </Flex>
            </Flex>
          ) : (
            <Empty description={t('dashboard.noSubscription')} />
          )}
        </Col>

        {allActiveSubscriptions && allActiveSubscriptions.length > 0 && (
          <Col xs={24} md={12}>
            <Flex vertical gap={16} className="w-full">
              <Flex vertical>
                <Flex className="block">
                  <Typography.Text>ALL ACTIVE LICENSES</Typography.Text>
                </Flex>
                <Typography.Title level={4}>{allActiveSubscriptions.length} Total</Typography.Title>
              </Flex>
              {/* eslint-disable-next-line no-restricted-syntax */}
              <Flex style={{ maxHeight: 320, overflowY: 'auto' }}>
                <Flex vertical gap={8} className="w-full">
                  {allActiveSubscriptions.map((sub, index) => {
                    const startDate = sub.startDate ? new Date(sub.startDate) : new Date();
                    const endDate = sub.endDate ? new Date(sub.endDate) : new Date();
                    const now = new Date();

                    const percent = (() => {
                      if (now < startDate) return 0;
                      if (now > endDate) return 100;
                      const total = endDate.getTime() - startDate.getTime();
                      const elapsed = now.getTime() - startDate.getTime();
                      return Math.round(Math.max(0, Math.min(100, (elapsed / total) * 100)));
                    })();

                    const strokeColor =
                      (sub.daysRemaining ?? 0) <= CRITICAL_DAYS_THRESHOLD
                        ? token.colorError
                        : token.colorPrimary;

                    return (
                      <Flex
                        vertical
                        key={`${sub.planCode}-${index}`}
                        data-testid={`dashboard-license-item-${index}`}
                      >
                        <Flex align="center" justify="space-between">
                          <Flex align="center" gap={8} wrap className="inline-flex">
                            <Typography.Text strong>{sub.planCode}</Typography.Text>
                            <Badge count={sub.quantity} />
                            {sub.isTrial === 1 && <Tag>Trial</Tag>}
                          </Flex>
                          <Typography.Text>
                            {sub.daysRemaining} {sub.daysRemaining === 1 ? 'day' : 'days'} remaining
                          </Typography.Text>
                        </Flex>
                        <Tooltip
                          title={`From ${startDate.toLocaleDateString()} to ${endDate.toLocaleDateString()}`}
                        >
                          <Progress
                            percent={percent}
                            showInfo={false}
                            size="small"
                            strokeColor={strokeColor}
                            data-testid={`dashboard-progress-subscription-${sub.planCode}`}
                          />
                        </Tooltip>
                      </Flex>
                    );
                  })}
                </Flex>
              </Flex>
            </Flex>
          </Col>
        )}
      </Row>

      {planLimits ? (
        <Row gutter={[24, 24]}>
          <Col xs={24} md={6}>
            <Statistic title={t('dashboard.maxActiveJobs')} value={planLimits.maxActiveJobs ?? undefined} />
          </Col>
          <Col xs={24} md={6}>
            <Statistic title={t('dashboard.maxReservedJobs')} value={planLimits.maxReservedJobs ?? undefined} />
          </Col>
          <Col xs={24} md={6}>
            <Statistic
              title={t('dashboard.jobTimeout')}
              value={planLimits.jobTimeoutHours ?? undefined}
              suffix="hours"
            />
          </Col>
          <Col xs={24} md={6}>
            <Statistic
              title={t('dashboard.maxRepoSize')}
              value={planLimits.maxRepositorySize ?? undefined}
              suffix="GB"
            />
          </Col>
        </Row>
      ) : (
        <Empty description={t('dashboard.noPlanData')} />
      )}
    </Card>
  );
};

export default SubscriptionPlanWidget;
