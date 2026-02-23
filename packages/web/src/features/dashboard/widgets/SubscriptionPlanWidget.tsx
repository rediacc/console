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
} from 'antd';
import { useTranslation } from 'react-i18next';
import { CrownOutlined } from '@/utils/optimizedIcons';
import type { OrganizationDashboardData } from '@rediacc/shared/types';

const CRITICAL_DAYS_THRESHOLD = 30;

interface SubscriptionPlanWidgetProps {
  activeSubscription?: OrganizationDashboardData['activeSubscription'];
  allActiveSubscriptions: OrganizationDashboardData['allActiveSubscriptions'];
  planLimits?: OrganizationDashboardData['planLimits'];
}

const SubscriptionPlanWidget: React.FC<SubscriptionPlanWidgetProps> = ({
  activeSubscription,
  allActiveSubscriptions,
  planLimits,
}) => {
  const { t } = useTranslation(['system', 'common']);

  return (
    <Card
      title={
        <Flex align="center" wrap className="inline-flex">
          <CrownOutlined />
          <Typography.Text>
            {t('common:dashboard.widgets.subscriptionPlan.title')} - {planLimits?.planCode ?? 'N/A'}
          </Typography.Text>
          {allActiveSubscriptions.length > 0 && <Badge count={allActiveSubscriptions.length} />}
        </Flex>
      }
      data-testid="dashboard-card-subscription-plans"
    >
      <Row gutter={[24, 24]}>
        <Col xs={24} md={allActiveSubscriptions.length > 0 ? 12 : 24}>
          {activeSubscription ? (
            <Flex vertical className="w-full">
              <Flex vertical>
                <Flex className="block">
                  <Typography.Text>
                    {t('common:dashboard.widgets.subscriptionPlan.currentSubscription')}
                  </Typography.Text>
                </Flex>
                <Typography.Title level={4}>{activeSubscription.planCode}</Typography.Title>
                <Row gutter={[16, 16]}>
                  <Col span={12}>
                    <Statistic
                      title={t('system:dashboard.activeSubscriptions')}
                      value={activeSubscription.totalActivePurchases ?? undefined}
                      data-testid="dashboard-stat-active-subscriptions"
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      title={t('system:dashboard.daysRemaining')}
                      value={activeSubscription.daysRemaining ?? undefined}
                      valueStyle={
                        (activeSubscription.daysRemaining ?? 0) <= CRITICAL_DAYS_THRESHOLD
                          ? { color: '#ff4d4f' }
                          : undefined
                      }
                      data-testid="dashboard-stat-days-remaining"
                    />
                  </Col>
                </Row>
              </Flex>
            </Flex>
          ) : (
            <Empty description={t('system:dashboard.noSubscription')} />
          )}
        </Col>

        {allActiveSubscriptions.length > 0 && (
          <Col xs={24} md={12}>
            <Flex vertical className="w-full">
              <Flex vertical>
                <Flex className="block">
                  <Typography.Text>
                    {t('common:dashboard.widgets.subscriptionPlan.allActiveSubscriptions')}
                  </Typography.Text>
                </Flex>
                <Typography.Title level={4}>
                  {allActiveSubscriptions.length}{' '}
                  {t('common:dashboard.widgets.subscriptionPlan.total')}
                </Typography.Title>
              </Flex>
              {/* eslint-disable-next-line no-restricted-syntax */}
              <Flex style={{ maxHeight: 320, overflowY: 'auto' }}>
                <Flex vertical className="gap-sm w-full">
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
                      (sub.daysRemaining ?? 0) <= CRITICAL_DAYS_THRESHOLD ? '#ff4d4f' : '#1677ff';

                    return (
                      <Flex
                        vertical
                        key={`${sub.planCode}-${index}`}
                        data-testid={`dashboard-subscription-item-${index}`}
                      >
                        <Flex align="center" justify="space-between">
                          <Flex align="center" wrap className="inline-flex">
                            <Typography.Text strong>{sub.planCode}</Typography.Text>
                            <Badge count={sub.quantity} />
                            {sub.isTrial === true && (
                              <Tag>{t('common:dashboard.widgets.subscriptionPlan.trial')}</Tag>
                            )}
                          </Flex>
                          <Typography.Text>
                            {sub.daysRemaining}{' '}
                            {sub.daysRemaining === 1
                              ? t('common:dashboard.widgets.subscriptionPlan.day')
                              : t('common:dashboard.widgets.subscriptionPlan.days')}{' '}
                            {t('common:dashboard.widgets.subscriptionPlan.remaining')}
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
          <Col xs={24} md={8}>
            <Statistic
              title={t('system:dashboard.maxReservedJobs')}
              value={planLimits.maxReservedJobs ?? undefined}
            />
          </Col>
          <Col xs={24} md={8}>
            <Statistic
              title={t('system:dashboard.jobTimeout')}
              value={planLimits.jobTimeoutHours ?? undefined}
              suffix={t('common:dashboard.widgets.subscriptionPlan.hours')}
            />
          </Col>
          <Col xs={24} md={8}>
            <Statistic
              title={t('system:dashboard.maxRepoSize')}
              value={planLimits.maxRepositorySize ?? undefined}
              suffix="GB"
            />
          </Col>
        </Row>
      ) : (
        <Empty description={t('system:dashboard.noPlanData')} />
      )}
    </Card>
  );
};

export default SubscriptionPlanWidget;
