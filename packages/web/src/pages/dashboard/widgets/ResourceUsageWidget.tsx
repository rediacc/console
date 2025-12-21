import React from 'react';
import { Card, Col, Flex, Progress, Row, Typography, theme } from 'antd';
import { DesktopOutlined, InboxOutlined, ThunderboltOutlined } from '@/utils/optimizedIcons';
import type { CompanyDashboardData } from '@rediacc/shared/types';

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
  resources: CompanyDashboardData['resources'];
}

const ResourceUsageWidget: React.FC<ResourceUsageWidgetProps> = ({ resources }) => {
  const { token } = theme.useToken();

  return (
    <Card
      title={
        <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
          <ThunderboltOutlined />
          <Typography.Text>Resource Usage</Typography.Text>
        </Flex>
      }
      extra={
        <Typography.Text style={{ fontSize: 12 }}>
          Monitor your resource consumption against plan limits
        </Typography.Text>
      }
      data-testid="dashboard-card-resource-usage"
    >
      <Row gutter={[16, 24]}>
        {resources
          .filter(
            (resource) =>
              resource.resourceType === 'Machine' || resource.resourceType === 'Repository'
          )
          .map((resource) => {
            const progressColor =
              resource.isLimitReached === 1 ? token.colorError : token.colorPrimary;
            return (
              <Col key={resource.resourceType} xs={24} sm={12} md={8}>
                <Flex vertical>
                  <Flex vertical gap={16} style={{ width: '100%' }}>
                    <Flex align="center" justify="space-between" style={{ width: '100%' }}>
                      <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
                        {resourceIcons[resource.resourceType]}
                        <Typography.Text strong>{resource.resourceType}s</Typography.Text>
                      </Flex>
                      <Typography.Text
                        style={{ display: 'inline-block', fontWeight: 500, fontSize: 14 }}
                      >
                        {resource.currentUsage} /{' '}
                        {resource.resourceLimit === 0 ? '∞' : resource.resourceLimit}
                      </Typography.Text>
                    </Flex>
                    <Progress
                      percent={resource.resourceLimit === 0 ? 0 : resource.usagePercentage}
                      status={getProgressStatus(resource.usagePercentage)}
                      strokeColor={progressColor}
                      data-testid={`dashboard-progress-${resource.resourceType.toLowerCase()}`}
                    />
                    {resource.isLimitReached === 1 && (
                      <Typography.Text type="danger" style={{ fontSize: 12 }}>
                        Limit reached
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
