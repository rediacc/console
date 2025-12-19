import React from 'react';
import { Empty } from 'antd';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { RediaccCard, RediaccStack, RediaccTag, RediaccText } from '@/components/ui';
import { EmptyStateWrapper } from '@/styles/primitives';
import { HistoryOutlined } from '@/utils/optimizedIcons';
import type { GetAuditLogs_ResultSet1 } from '@rediacc/shared/types';
import { AuditMeta, FlexBetween, InlineLink, InlineStack, TimelineWrapper } from '../styles';
import { getActionIcon } from '../utils/actionIconMapping';
import { formatTimestamp } from '../utils/formatTimestamp';

const DESCRIPTION_TRUNCATE_LENGTH = 80;

interface RecentActivityWidgetProps {
  auditLogs?: GetAuditLogs_ResultSet1[];
  isLoading: boolean;
}

const RecentActivityWidget: React.FC<RecentActivityWidgetProps> = ({ auditLogs, isLoading }) => {
  return (
    <RediaccCard
      fullWidth
      title={
        <InlineStack>
          <HistoryOutlined />
          <span>Recent Activity</span>
        </InlineStack>
      }
      extra={
        <InlineLink to="/audit" data-testid="dashboard-activity-viewall-link">
          View All
        </InlineLink>
      }
      data-testid="dashboard-card-recent-activity"
    >
      {isLoading ? (
        <EmptyStateWrapper>
          <LoadingWrapper loading centered minHeight={120}>
            <div />
          </LoadingWrapper>
        </EmptyStateWrapper>
      ) : auditLogs && auditLogs.length > 0 ? (
        <TimelineWrapper
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
                <RediaccStack direction="vertical" gap="sm" fullWidth>
                  <FlexBetween>
                    <InlineStack>
                      <RediaccText weight="bold">{log.action.replace(/_/g, ' ')}</RediaccText>
                      <RediaccTag variant="neutral">{log.entity}</RediaccTag>
                    </InlineStack>
                    <AuditMeta>{formatTimestamp(log.timestamp)}</AuditMeta>
                  </FlexBetween>
                  <AuditMeta>
                    {log.entityName} {log.actionByUser && `• ${log.actionByUser}`}
                  </AuditMeta>
                  {log.details && log.details.trim() && (
                    <AuditMeta>
                      {log.details.length > DESCRIPTION_TRUNCATE_LENGTH
                        ? `${log.details.substring(0, DESCRIPTION_TRUNCATE_LENGTH)}...`
                        : log.details}
                    </AuditMeta>
                  )}
                </RediaccStack>
              ),
            }))}
        />
      ) : (
        <EmptyStateWrapper>
          <Empty description="No recent activity" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </EmptyStateWrapper>
      )}
    </RediaccCard>
  );
};

export default RecentActivityWidget;
