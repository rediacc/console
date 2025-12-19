import React from 'react';
import { Col, Row } from 'antd';
import { createTruncatedColumn } from '@/components/common/columns';
import { RediaccCard, RediaccStack, RediaccTable, RediaccTag, RediaccText } from '@/components/ui';
import { createSorter } from '@/platform';
import {
  DesktopOutlined,
  RobotOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import type {
  CompanyDashboardData,
  QueueMachineIssue,
  QueueTeamIssue,
} from '@rediacc/shared/types';
import {
  BorderlessList,
  BorderlessListItem,
  FlexBetween,
  HorizontalScroll,
  InlineStack,
  QueueBadge,
  QueueBadgeRow,
  ResourceTile,
  SectionTitle,
  StatRow,
  StatValue,
} from '../styles';
import type { ColumnsType } from 'antd/es/table';

const machineNameColumn = createTruncatedColumn<QueueMachineIssue>({
  title: 'Machine',
  dataIndex: 'machineName',
  key: 'machineName',
  sorter: createSorter<QueueMachineIssue>('machineName'),
});

const teamColumn = createTruncatedColumn<QueueMachineIssue>({
  title: 'Team',
  dataIndex: 'teamName',
  key: 'teamName',
  sorter: createSorter<QueueMachineIssue>('teamName'),
});

const machineIssueColumns: ColumnsType<QueueMachineIssue> = [
  machineNameColumn,
  teamColumn,
  {
    title: 'Status',
    key: 'status',
    width: 200,
    render: (_: unknown, record: QueueMachineIssue) => (
      <InlineStack>
        {(record.staleItems || 0) > 0 && (
          <RediaccTag variant="warning">{record.staleItems} stale</RediaccTag>
        )}
        <RediaccTag variant="info">{record.pendingItems || 0} pending</RediaccTag>
        <RediaccTag variant="info">{record.activeItems || 0} active</RediaccTag>
      </InlineStack>
    ),
  },
];

interface QueueDetailsWidgetProps {
  queueStats: NonNullable<CompanyDashboardData['queueStats']>;
  featureAccess?: CompanyDashboardData['featureAccess'];
}

const QueueDetailsWidget: React.FC<QueueDetailsWidgetProps> = ({ queueStats, featureAccess }) => {
  const teamIssues: QueueTeamIssue[] = Array.isArray(queueStats.teamIssues)
    ? (queueStats.teamIssues as QueueTeamIssue[])
    : [];
  const machineIssues: QueueMachineIssue[] = Array.isArray(queueStats.machineIssues)
    ? (queueStats.machineIssues as QueueMachineIssue[])
    : [];

  return (
    <RediaccCard
      fullWidth
      title={
        <InlineStack>
          <RobotOutlined />
          <span>Queue Details</span>
        </InlineStack>
      }
      data-testid="dashboard-card-queue-details"
    >
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <ResourceTile>
            <RediaccText weight="bold">Today&apos;s Activity</RediaccText>
            <RediaccStack direction="vertical" gap="md" fullWidth>
              <StatRow>
                <RediaccText variant="caption" color="secondary">
                  Created
                </RediaccText>
                <StatValue data-testid="dashboard-stat-created-today">
                  {queueStats.createdToday || 0}
                </StatValue>
              </StatRow>
              <StatRow>
                <RediaccText variant="caption" color="secondary">
                  Completed
                </RediaccText>
                <StatValue $variant="success" data-testid="dashboard-stat-completed-today">
                  {queueStats.completedToday || 0}
                </StatValue>
              </StatRow>
              <StatRow>
                <RediaccText variant="caption" color="secondary">
                  Cancelled
                </RediaccText>
                <StatValue $variant="error" data-testid="dashboard-stat-cancelled-today">
                  {queueStats.cancelledToday || 0}
                </StatValue>
              </StatRow>
              <StatRow>
                <RediaccText variant="caption" color="secondary">
                  Failed
                </RediaccText>
                <StatValue $variant="error" data-testid="dashboard-stat-failed-today">
                  {queueStats.failedToday || 0}
                </StatValue>
              </StatRow>
            </RediaccStack>
          </ResourceTile>
        </Col>

        <Col xs={24} lg={16}>
          <RediaccStack direction="vertical" gap="md" fullWidth>
            {teamIssues.length > 0 && (
              <div>
                <SectionTitle weight="bold">
                  <TeamOutlined /> Team Queue Status
                </SectionTitle>
                <BorderlessList
                  size="sm"
                  dataSource={teamIssues}
                  data-testid="dashboard-list-team-issues"
                  renderItem={(team) => {
                    const teamIssue = team as QueueTeamIssue;
                    return (
                      <BorderlessListItem>
                        <FlexBetween>
                          <RediaccText weight="bold">{teamIssue.teamName}</RediaccText>
                          <InlineStack>
                            {(teamIssue.staleItems || 0) > 0 && (
                              <RediaccTag variant="warning">
                                <WarningOutlined /> {teamIssue.staleItems} stale
                              </RediaccTag>
                            )}
                            <RediaccTag variant="info">
                              {teamIssue.pendingItems || 0} pending
                            </RediaccTag>
                            <RediaccTag variant="info">
                              {teamIssue.activeItems || 0} active
                            </RediaccTag>
                          </InlineStack>
                        </FlexBetween>
                      </BorderlessListItem>
                    );
                  }}
                />
              </div>
            )}

            {machineIssues.length > 0 && (
              <div>
                <SectionTitle weight="bold">
                  <DesktopOutlined /> Machine Queue Status
                </SectionTitle>
                <HorizontalScroll>
                  <RediaccTable<QueueMachineIssue>
                    size="sm"
                    dataSource={machineIssues}
                    pagination={false}
                    columns={machineIssueColumns}
                    data-testid="dashboard-table-machine-issues"
                    rowKey={(record) => `${record.teamName}-${record.machineName}`}
                  />
                </HorizontalScroll>
              </div>
            )}

            {featureAccess?.hasAdvancedAnalytics === 1 &&
              queueStats.highestPriorityPending !== null && (
                <ResourceTile>
                  <RediaccText weight="bold">
                    <ThunderboltOutlined /> Priority Breakdown
                  </RediaccText>
                  <QueueBadgeRow>
                    <FlexBetween>
                      <RediaccText>Highest Priority</RediaccText>
                      <QueueBadge
                        $variant="error"
                        count={queueStats.highestPriorityPending ?? 0}
                        data-testid="dashboard-badge-highest-priority"
                      />
                    </FlexBetween>
                    <FlexBetween>
                      <RediaccText>High Priority</RediaccText>
                      <QueueBadge
                        $variant="warning"
                        count={queueStats.highPriorityPending ?? 0}
                        data-testid="dashboard-badge-high-priority"
                      />
                    </FlexBetween>
                    <FlexBetween>
                      <RediaccText>Normal Priority</RediaccText>
                      <QueueBadge
                        $variant="info"
                        count={queueStats.normalPriorityPending ?? 0}
                        data-testid="dashboard-badge-normal-priority"
                      />
                    </FlexBetween>
                    <FlexBetween>
                      <RediaccText>Low Priority</RediaccText>
                      <QueueBadge
                        $variant="default"
                        count={queueStats.lowPriorityPending ?? 0}
                        data-testid="dashboard-badge-low-priority"
                      />
                    </FlexBetween>
                  </QueueBadgeRow>
                </ResourceTile>
              )}
          </RediaccStack>
        </Col>
      </Row>
    </RediaccCard>
  );
};

export default QueueDetailsWidget;
