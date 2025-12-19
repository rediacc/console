import React from 'react';
import { Col, Row } from 'antd';
import { useTheme as useStyledTheme } from 'styled-components';
import { RediaccCard, RediaccStack, RediaccText } from '@/components/ui';
import { DesktopOutlined, InboxOutlined, ThunderboltOutlined } from '@/utils/optimizedIcons';
import type { CompanyDashboardData } from '@rediacc/shared/types';
import {
  ErrorText,
  InlineStack,
  ResourceProgress,
  ResourceTile,
  TileHeader,
  TileMeta,
} from '../styles';

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
  const theme = useStyledTheme();

  return (
    <RediaccCard
      fullWidth
      title={
        <InlineStack>
          <ThunderboltOutlined />
          <span>Resource Usage</span>
        </InlineStack>
      }
      extra={
        <RediaccText variant="description">
          Monitor your resource consumption against plan limits
        </RediaccText>
      }
      data-testid="dashboard-card-resource-usage"
    >
      <Row gutter={[16, 24]}>
        {resources
          .filter((resource) => resource.resourceType === 'Machine' || resource.resourceType === 'Repository')
          .map((resource) => {
            const progressColor =
              resource.isLimitReached === 1 ? theme.colors.error : theme.colors.primary;
            return (
              <Col key={resource.resourceType} xs={24} sm={12} md={8}>
                <ResourceTile>
                  <RediaccStack direction="vertical" gap="md" fullWidth>
                    <TileHeader>
                      <InlineStack>
                        {resourceIcons[resource.resourceType]}
                        <RediaccText weight="bold">{resource.resourceType}s</RediaccText>
                      </InlineStack>
                      <TileMeta>
                        {resource.currentUsage} /{' '}
                        {resource.resourceLimit === 0 ? '∞' : resource.resourceLimit}
                      </TileMeta>
                    </TileHeader>
                    <ResourceProgress
                      percent={resource.resourceLimit === 0 ? 0 : resource.usagePercentage}
                      status={getProgressStatus(resource.usagePercentage)}
                      strokeColor={progressColor}
                      data-testid={`dashboard-progress-${resource.resourceType.toLowerCase()}`}
                    />
                    {resource.isLimitReached === 1 && (
                      <ErrorText variant="caption" as="span">
                        Limit reached
                      </ErrorText>
                    )}
                  </RediaccStack>
                </ResourceTile>
              </Col>
            );
          })}
      </Row>
    </RediaccCard>
  );
};

export default ResourceUsageWidget;
