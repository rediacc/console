import React from 'react';
import { Card, Col, Flex, Progress, Row, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { DesktopOutlined, InboxOutlined, ThunderboltOutlined } from '@/utils/optimizedIcons';
import type { OrganizationDashboardData } from '@rediacc/shared/types';

const resourceIcons: Record<string, React.ReactNode> = {
  Machine: <DesktopOutlined />,
  Repository: <InboxOutlined />,
};

const PROGRESS_THRESHOLDS = {
  EXCEPTION: 90,
  NORMAL: 75,
};

const getProgressStatus = (percentage: number): 'exception' | 'normal' | 'success' => {
  if (percentage >= PROGRESS_THRESHOLDS.EXCEPTION) return 'exception';
  if (percentage >= PROGRESS_THRESHOLDS.NORMAL) return 'normal';
  return 'success';
};

interface ResourceUsageWidgetProps {
  resources: OrganizationDashboardData['resources'];
}

const ResourceUsageWidget: React.FC<ResourceUsageWidgetProps> = ({ resources }) => {
  const { t } = useTranslation('common');

  return (
    <Card
      title={
        <Flex align="center" wrap className="inline-flex">
          <ThunderboltOutlined />
          <Typography.Text>{t('dashboard.widgets.resourceUsage.title')}</Typography.Text>
        </Flex>
      }
      extra={<Typography.Text>{t('dashboard.widgets.resourceUsage.subtitle')}</Typography.Text>}
      data-testid="dashboard-card-resource-usage"
    >
      <Row gutter={[16, 24]}>
        {resources
          .filter(
            (resource) =>
              resource.resourceType === 'Machine' || resource.resourceType === 'Repository'
          )
          .map((resource) => {
            const progressColor = resource.isLimitReached === true ? '#ff4d4f' : '#1677ff';
            const resourceKey = resource.resourceType === 'Machine' ? 'machines' : 'repositories';
            return (
              <Col key={resource.resourceType} xs={24} sm={12} md={8}>
                <Flex vertical>
                  <Flex vertical className="w-full">
                    <Flex align="center" justify="space-between" className="w-full">
                      <Flex align="center" wrap className="inline-flex">
                        {resourceIcons[resource.resourceType ?? '']}
                        <Typography.Text strong>
                          {t(`dashboard.widgets.resourceUsage.${resourceKey}`)}
                        </Typography.Text>
                      </Flex>
                      <Typography.Text className="inline-block">
                        {resource.currentUsage} /{' '}
                        {resource.resourceLimit === 0 ? '∞' : resource.resourceLimit}
                      </Typography.Text>
                    </Flex>
                    <Progress
                      percent={resource.resourceLimit === 0 ? 0 : (resource.usagePercentage ?? 0)}
                      status={getProgressStatus(resource.usagePercentage ?? 0)}
                      strokeColor={progressColor}
                      data-testid={`dashboard-progress-${(resource.resourceType ?? '').toLowerCase()}`}
                    />
                    {resource.isLimitReached === true && (
                      <Typography.Text type="danger">
                        {t('dashboard.widgets.resourceUsage.limitReached')}
                      </Typography.Text>
                    )}
                  </Flex>
                </Flex>
              </Col>
            );
          })}
      </Row>
    </Card>
  );
};

export default ResourceUsageWidget;
