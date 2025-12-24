import React from 'react';
import { Card, Empty, Flex, Tag, Timeline, Typography } from 'antd';
import { Link as RouterLink } from 'react-router-dom';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { HistoryOutlined } from '@/utils/optimizedIcons';
import type { GetAuditLogs_ResultSet1 } from '@rediacc/shared/types';
import { getActionIcon } from '../utils/actionIconMapping';
import { formatTimestamp } from '../utils/formatTimestamp';

const DESCRIPTION_TRUNCATE_LENGTH = 80;

interface RecentActivityWidgetProps {
  auditLogs?: GetAuditLogs_ResultSet1[];
  isLoading: boolean;
}

const RecentActivityWidget: React.FC<RecentActivityWidgetProps> = ({ auditLogs, isLoading }) => {
  return (
    <Card
      title={
        <Flex align="center" gap={8} wrap className="inline-flex">
          <HistoryOutlined />
          <Typography.Text>Recent Activity</Typography.Text>
        </Flex>
      }
      extra={
        <RouterLink to="/audit" data-testid="dashboard-activity-viewall-link">
          View All
        </RouterLink>
      }
      data-testid="dashboard-card-recent-activity"
    >
      {isLoading ? (
        <Flex vertical align="center" justify="center">
          <LoadingWrapper loading centered minHeight={120}>
            <Flex />
          </LoadingWrapper>
        </Flex>
      ) : auditLogs && auditLogs.length > 0 ? (
        <Timeline
          items={auditLogs
            .filter((log) => {
              const action = log.action.toLowerCase();
              const isTokenValidation = action.includes('token') && action.includes('validat');
              const isRoutineAuth = action.includes('login') && action.includes('success');
              return !isTokenValidation && !isRoutineAuth;
            })
            .slice(0, 5)
            .map((log, index) => ({
              key: index,
              dot: getActionIcon(log.action),
              children: (
                <Flex vertical gap={8} className="w-full">
                  <Flex align="center" justify="space-between">
                    <Flex align="center" gap={8} wrap className="inline-flex">
                      <Typography.Text strong>{log.action.replace(/_/g, ' ')}</Typography.Text>
                      <Tag bordered={false}>{log.entity}</Tag>
                    </Flex>
                    <Typography.Text>{formatTimestamp(log.timestamp)}</Typography.Text>
                  </Flex>
                  <Typography.Text>
                    {log.entityName} {log.actionByUser && `• ${log.actionByUser}`}
                  </Typography.Text>
                  {log.details && log.details.trim() && (
                    <Typography.Text>
                      {log.details.length > DESCRIPTION_TRUNCATE_LENGTH
                        ? `${log.details.substring(0, DESCRIPTION_TRUNCATE_LENGTH)}...`
                        : log.details}
                    </Typography.Text>
                  )}
                </Flex>
              ),
            }))}
        />
      ) : (
        <Flex vertical align="center" justify="center">
          <Empty description="No recent activity" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </Flex>
      )}
    </Card>
  );
};

export default RecentActivityWidget;
