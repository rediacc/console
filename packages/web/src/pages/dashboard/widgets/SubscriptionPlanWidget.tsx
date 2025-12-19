import React from 'react';
import { Col, Empty, Row } from 'antd';
import { useTranslation } from 'react-i18next';
import { useTheme as useStyledTheme } from 'styled-components';
import { RediaccCard, RediaccStack, RediaccStatistic, RediaccTag, RediaccText, RediaccTooltip } from '@/components/ui';
import { CrownOutlined } from '@/utils/optimizedIcons';
import type { CompanyDashboardData } from '@rediacc/shared/types';
import {
  DaysRemainingText,
  InlineStack,
  LicenseHeader,
  LicenseItem,
  PlanCountBadge,
  QuantityBadge,
  ResourceProgress,
  ScrollContainer,
  SectionLabelWrapper,
  SectionTitleWrapper,
} from '../styles';

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
  const theme = useStyledTheme();

  return (
    <RediaccCard
      fullWidth
      title={
        <InlineStack>
          <CrownOutlined />
          <span>Subscription & Plan Details - {planLimits?.planCode ?? 'N/A'}</span>
          {allActiveSubscriptions.length > 0 && (
            <PlanCountBadge count={allActiveSubscriptions.length} />
          )}
        </InlineStack>
      }
      data-testid="dashboard-card-subscription-plans"
    >
      <Row gutter={[24, 24]}>
        <Col xs={24} md={allActiveSubscriptions.length > 0 ? 12 : 24}>
          {activeSubscription ? (
            <RediaccStack direction="vertical" gap="md" fullWidth>
              <div>
                <SectionLabelWrapper>
                  <RediaccText variant="label">CURRENT SUBSCRIPTION</RediaccText>
                </SectionLabelWrapper>
                <SectionTitleWrapper level={4}>
                  {activeSubscription.planCode}
                </SectionTitleWrapper>
                <Row gutter={[16, 16]}>
                  <Col span={12}>
                    <RediaccStatistic
                      title={t('dashboard.activeLicenses')}
                      value={activeSubscription.totalActivePurchases}
                      variant="textPrimary"
                      data-testid="dashboard-stat-active-licenses"
                    />
                  </Col>
                  <Col span={12}>
                    <RediaccStatistic
                      title={t('dashboard.daysRemaining')}
                      value={activeSubscription.daysRemaining}
                      critical={activeSubscription.daysRemaining <= CRITICAL_DAYS_THRESHOLD}
                      data-testid="dashboard-stat-days-remaining"
                    />
                  </Col>
                </Row>
              </div>
            </RediaccStack>
          ) : (
            <Empty description={t('dashboard.noSubscription')} />
          )}
        </Col>

        {allActiveSubscriptions.length > 0 && (
          <Col xs={24} md={12}>
            <RediaccStack direction="vertical" gap="md" fullWidth>
              <div>
                <SectionLabelWrapper>
                  <RediaccText variant="label">ALL ACTIVE LICENSES</RediaccText>
                </SectionLabelWrapper>
                <SectionTitleWrapper level={4}>
                  {allActiveSubscriptions.length} Total
                </SectionTitleWrapper>
              </div>
              <ScrollContainer>
                <RediaccStack direction="vertical" gap="sm" fullWidth>
                  {allActiveSubscriptions.map((sub, index) => {
                    const startDate = new Date(sub.startDate);
                    const endDate = new Date(sub.endDate);
                    const now = new Date();

                    const percent = (() => {
                      if (now < startDate) return 0;
                      if (now > endDate) return 100;
                      const total = endDate.getTime() - startDate.getTime();
                      const elapsed = now.getTime() - startDate.getTime();
                      return Math.round(Math.max(0, Math.min(100, (elapsed / total) * 100)));
                    })();

                    const strokeColor =
                      sub.daysRemaining <= CRITICAL_DAYS_THRESHOLD
                        ? theme.colors.error
                        : theme.colors.primary;

                    return (
                      <LicenseItem
                        key={`${sub.planCode}-${index}`}
                        data-testid={`dashboard-license-item-${index}`}
                      >
                        <LicenseHeader>
                          <InlineStack>
                            <RediaccText weight="bold">{sub.planCode}</RediaccText>
                            <QuantityBadge count={sub.quantity} />
                            {sub.isTrial === 1 && <RediaccTag variant="info">Trial</RediaccTag>}
                          </InlineStack>
                          <DaysRemainingText
                            variant="caption"
                            as="span"
                            $critical={sub.daysRemaining <= CRITICAL_DAYS_THRESHOLD}
                          >
                            {sub.daysRemaining} {sub.daysRemaining === 1 ? 'day' : 'days'} remaining
                          </DaysRemainingText>
                        </LicenseHeader>
                        <RediaccTooltip
                          title={`From ${startDate.toLocaleDateString()} to ${endDate.toLocaleDateString()}`}
                        >
                          <ResourceProgress
                            percent={percent}
                            showInfo={false}
                            size="sm"
                            strokeColor={strokeColor}
                            data-testid={`dashboard-progress-subscription-${sub.planCode}`}
                          />
                        </RediaccTooltip>
                      </LicenseItem>
                    );
                  })}
                </RediaccStack>
              </ScrollContainer>
            </RediaccStack>
          </Col>
        )}
      </Row>

      {planLimits ? (
        <Row gutter={[24, 24]}>
          <Col xs={24} md={6}>
            <RediaccStatistic
              title={t('dashboard.maxActiveJobs')}
              value={planLimits.maxActiveJobs}
              variant="primary"
            />
          </Col>
          <Col xs={24} md={6}>
            <RediaccStatistic
              title={t('dashboard.maxReservedJobs')}
              value={planLimits.maxReservedJobs}
              variant="primary"
            />
          </Col>
          <Col xs={24} md={6}>
            <RediaccStatistic
              title={t('dashboard.jobTimeout')}
              value={planLimits.jobTimeoutHours}
              suffix="hours"
              variant="primary"
            />
          </Col>
          <Col xs={24} md={6}>
            <RediaccStatistic
              title={t('dashboard.maxRepoSize')}
              value={planLimits.maxRepoSize}
              suffix="GB"
              variant="primary"
            />
          </Col>
        </Row>
      ) : (
        <Empty description={t('dashboard.noPlanData')} />
      )}
    </RediaccCard>
  );
};

export default SubscriptionPlanWidget;
