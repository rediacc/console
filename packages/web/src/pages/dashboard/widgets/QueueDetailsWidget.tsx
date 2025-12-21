import React from 'react';
import { Badge, Card, Col, Flex, List, Row, Table, Tag, Typography } from 'antd';
import { createTruncatedColumn } from '@/components/common/columns';
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
      <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
        {(record.staleItems || 0) > 0 && <Tag color="warning">{record.staleItems} stale</Tag>}
        <Tag color="processing">{record.pendingItems || 0} pending</Tag>
        <Tag color="processing">{record.activeItems || 0} active</Tag>
      </Flex>
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
    <Card
      title={
        <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
          <RobotOutlined />
          <Typography.Text>Queue Details</Typography.Text>
        </Flex>
      }
      data-testid="dashboard-card-queue-details"
    >
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Flex vertical>
            <Typography.Text strong>Today&apos;s Activity</Typography.Text>
            <Flex vertical gap={16} style={{ width: '100%' }}>
              <Flex align="center" justify="space-between">
                <Typography.Text style={{ fontSize: 12 }}>
                  Created
                </Typography.Text>
                <Typography.Text data-testid="dashboard-stat-created-today">
                  {queueStats.createdToday || 0}
                </Typography.Text>
              </Flex>
              <Flex align="center" justify="space-between">
                <Typography.Text style={{ fontSize: 12 }}>
                  Completed
                </Typography.Text>
                <Typography.Text
                  style={{ color: 'var(--ant-color-success)' }}
                  data-testid="dashboard-stat-completed-today"
                >
                  {queueStats.completedToday || 0}
                </Typography.Text>
              </Flex>
              <Flex align="center" justify="space-between">
                <Typography.Text style={{ fontSize: 12 }}>
                  Cancelled
                </Typography.Text>
                <Typography.Text
                  style={{ color: 'var(--ant-color-error)' }}
                  data-testid="dashboard-stat-cancelled-today"
                >
                  {queueStats.cancelledToday || 0}
                </Typography.Text>
              </Flex>
              <Flex align="center" justify="space-between">
                <Typography.Text style={{ fontSize: 12 }}>
                  Failed
                </Typography.Text>
                <Typography.Text
                  style={{ color: 'var(--ant-color-error)' }}
                  data-testid="dashboard-stat-failed-today"
                >
                  {queueStats.failedToday || 0}
                </Typography.Text>
              </Flex>
            </Flex>
          </Flex>
        </Col>

        <Col xs={24} lg={16}>
          <Flex vertical gap={16} style={{ width: '100%' }}>
            {teamIssues.length > 0 && (
              <Flex vertical>
                <Typography.Text strong>
                  <TeamOutlined /> Team Queue Status
                </Typography.Text>
                <List
                  size="small"
                  dataSource={teamIssues}
                  data-testid="dashboard-list-team-issues"
                  renderItem={(team) => {
                    const teamIssue = team as QueueTeamIssue;
                    return (
                      <List.Item>
                        <Flex align="center" justify="space-between">
                          <Typography.Text strong>{teamIssue.teamName}</Typography.Text>
                          <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
                            {(teamIssue.staleItems || 0) > 0 && (
                              <Tag color="warning">
                                <WarningOutlined /> {teamIssue.staleItems} stale
                              </Tag>
                            )}
                            <Tag color="processing">{teamIssue.pendingItems || 0} pending</Tag>
                            <Tag color="processing">{teamIssue.activeItems || 0} active</Tag>
                          </Flex>
                        </Flex>
                      </List.Item>
                    );
                  }}
                />
              </Flex>
            )}

            {machineIssues.length > 0 && (
              <Flex vertical>
                <Typography.Text strong>
                  <DesktopOutlined /> Machine Queue Status
                </Typography.Text>
                <Flex style={{ width: '100%', overflowX: 'auto' }}>
                  <Table<QueueMachineIssue>
                    size="small"
                    dataSource={machineIssues}
                    pagination={false}
                    columns={machineIssueColumns}
                    data-testid="dashboard-table-machine-issues"
                    rowKey={(record) => `${record.teamName}-${record.machineName}`}
                  />
                </Flex>
              </Flex>
            )}

            {featureAccess?.hasAdvancedAnalytics === 1 &&
              queueStats.highestPriorityPending !== null && (
                <Flex vertical>
                  <Typography.Text strong>
                    <ThunderboltOutlined /> Priority Breakdown
                  </Typography.Text>
                  <Flex vertical style={{ width: '100%' }}>
                    <Flex align="center" justify="space-between">
                      <Typography.Text>Highest Priority</Typography.Text>
                      <Badge
                        color="error"
                        count={queueStats.highestPriorityPending ?? 0}
                        showZero
                        data-testid="dashboard-badge-highest-priority"
                      />
                    </Flex>
                    <Flex align="center" justify="space-between">
                      <Typography.Text>High Priority</Typography.Text>
                      <Badge
                        color="warning"
                        count={queueStats.highPriorityPending ?? 0}
                        showZero
                        data-testid="dashboard-badge-high-priority"
                      />
                    </Flex>
                    <Flex align="center" justify="space-between">
                      <Typography.Text>Normal Priority</Typography.Text>
                      <Badge
                        color="processing"
                        count={queueStats.normalPriorityPending ?? 0}
                        showZero
                        data-testid="dashboard-badge-normal-priority"
                      />
                    </Flex>
                    <Flex align="center" justify="space-between">
                      <Typography.Text>Low Priority</Typography.Text>
                      <Badge
                        color="default"
                        count={queueStats.lowPriorityPending ?? 0}
                        showZero
                        data-testid="dashboard-badge-low-priority"
                      />
                    </Flex>
                  </Flex>
                </Flex>
              )}
          </Flex>
        </Col>
      </Row>
    </Card>
  );
};

export default QueueDetailsWidget;
