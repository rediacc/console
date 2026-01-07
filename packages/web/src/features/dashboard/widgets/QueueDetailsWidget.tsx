import React from 'react';
import { Badge, Card, Col, Flex, Grid, List, Row, Table, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { createTruncatedColumn } from '@/components/common/columns';
import { MobileCard } from '@/components/common/MobileCard';
import { createSorter } from '@/platform';
import {
  DesktopOutlined,
  RobotOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import type {
  GetOrganizationDashboard_ResultSet10,
  GetOrganizationDashboard_ResultSet11,
  OrganizationDashboardData,
} from '@rediacc/shared/types';
import type { ColumnsType } from 'antd/es/table';

const getMachineIssueColumns = (
  t: (key: string) => string
): ColumnsType<GetOrganizationDashboard_ResultSet11> => {
  const machineNameColumn = createTruncatedColumn<GetOrganizationDashboard_ResultSet11>({
    title: t('dashboard.widgets.queueDetails.machine'),
    dataIndex: 'machineName',
    key: 'machineName',
    sorter: createSorter<GetOrganizationDashboard_ResultSet11>('machineName'),
  });

  const teamColumn = createTruncatedColumn<GetOrganizationDashboard_ResultSet11>({
    title: t('dashboard.widgets.queueDetails.team'),
    dataIndex: 'teamName',
    key: 'teamName',
    sorter: createSorter<GetOrganizationDashboard_ResultSet11>('teamName'),
  });

  return [
    machineNameColumn,
    teamColumn,
    {
      title: t('dashboard.widgets.queueDetails.status'),
      key: 'status',
      width: 200,
      render: (_: unknown, record: GetOrganizationDashboard_ResultSet11) => (
        <Flex align="center" wrap className="inline-flex">
          {(record.staleItems ?? 0) > 0 && (
            <Tag>
              {record.staleItems} {t('dashboard.widgets.queueDetails.stale')}
            </Tag>
          )}
          <Tag>
            {record.pendingItems ?? 0} {t('dashboard.widgets.queueDetails.pending')}
          </Tag>
          <Tag>
            {record.activeItems ?? 0} {t('dashboard.widgets.queueDetails.active')}
          </Tag>
        </Flex>
      ),
    },
  ];
};

interface QueueDetailsWidgetProps {
  queueStats: NonNullable<OrganizationDashboardData['queueStats']>;
  teamIssues: GetOrganizationDashboard_ResultSet10[];
  machineIssues: GetOrganizationDashboard_ResultSet11[];
  featureAccess?: OrganizationDashboardData['featureAccess'];
}

const QueueDetailsWidget: React.FC<QueueDetailsWidgetProps> = ({
  queueStats,
  teamIssues,
  machineIssues,
  featureAccess,
}) => {
  const { t } = useTranslation('common');
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.sm;
  const machineIssueColumns = getMachineIssueColumns(t);

  return (
    <Card
      title={
        <Flex align="center" wrap className="inline-flex">
          <RobotOutlined />
          <Typography.Text>{t('dashboard.widgets.queueDetails.title')}</Typography.Text>
        </Flex>
      }
      data-testid="dashboard-card-queue-details"
    >
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Flex vertical>
            <Typography.Text strong>
              {t('dashboard.widgets.queueDetails.todayActivity')}
            </Typography.Text>
            <Flex vertical className="w-full">
              <Flex align="center" justify="space-between">
                <Typography.Text>{t('dashboard.widgets.queueDetails.created')}</Typography.Text>
                <Typography.Text data-testid="dashboard-stat-created-today">
                  {queueStats.createdToday ?? 0}
                </Typography.Text>
              </Flex>
              <Flex align="center" justify="space-between">
                <Typography.Text>{t('dashboard.widgets.queueDetails.completed')}</Typography.Text>
                <Typography.Text data-testid="dashboard-stat-completed-today">
                  {queueStats.completedToday ?? 0}
                </Typography.Text>
              </Flex>
              <Flex align="center" justify="space-between">
                <Typography.Text>{t('dashboard.widgets.queueDetails.cancelled')}</Typography.Text>
                <Typography.Text data-testid="dashboard-stat-cancelled-today">
                  {queueStats.cancelledToday ?? 0}
                </Typography.Text>
              </Flex>
              <Flex align="center" justify="space-between">
                <Typography.Text>{t('dashboard.widgets.queueDetails.failedTotal')}</Typography.Text>
                <Typography.Text data-testid="dashboard-stat-failed-today">
                  {queueStats.failedCount ?? 0}
                </Typography.Text>
              </Flex>
            </Flex>
          </Flex>
        </Col>

        <Col xs={24} lg={16}>
          <Flex vertical className="w-full">
            {teamIssues.length > 0 && (
              <Flex vertical>
                <Typography.Text strong>
                  <TeamOutlined /> {t('dashboard.widgets.queueDetails.teamQueueStatus')}
                </Typography.Text>
                <List
                  size="small"
                  dataSource={teamIssues}
                  data-testid="dashboard-list-team-issues"
                  renderItem={(team) => {
                    const teamIssue = team;
                    return (
                      <List.Item>
                        <Flex align="center" justify="space-between">
                          <Typography.Text strong>{teamIssue.teamName}</Typography.Text>
                          <Flex align="center" wrap className="inline-flex">
                            {(teamIssue.staleItems ?? 0) > 0 && (
                              <Tag>
                                <WarningOutlined /> {teamIssue.staleItems}{' '}
                                {t('dashboard.widgets.queueDetails.stale')}
                              </Tag>
                            )}
                            <Tag>
                              {teamIssue.pendingItems ?? 0}{' '}
                              {t('dashboard.widgets.queueDetails.pending')}
                            </Tag>
                            <Tag>
                              {teamIssue.activeItems ?? 0}{' '}
                              {t('dashboard.widgets.queueDetails.active')}
                            </Tag>
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
                  <DesktopOutlined /> {t('dashboard.widgets.queueDetails.machineQueueStatus')}
                </Typography.Text>
                {isMobile ? (
                  <List
                    size="small"
                    dataSource={machineIssues}
                    data-testid="dashboard-table-machine-issues"
                    renderItem={(record) => (
                      <List.Item key={`${record.teamName}-${record.machineName}`}>
                        <MobileCard>
                          <Flex align="center">
                            <DesktopOutlined />
                            <Typography.Text strong className="truncate">
                              {record.machineName}
                            </Typography.Text>
                          </Flex>
                          <Typography.Text type="secondary">{record.teamName}</Typography.Text>
                          <Flex align="center" wrap className="inline-flex">
                            {(record.staleItems ?? 0) > 0 && (
                              <Tag>
                                {record.staleItems} {t('dashboard.widgets.queueDetails.stale')}
                              </Tag>
                            )}
                            <Tag>
                              {record.pendingItems ?? 0}{' '}
                              {t('dashboard.widgets.queueDetails.pending')}
                            </Tag>
                            <Tag>
                              {record.activeItems ?? 0} {t('dashboard.widgets.queueDetails.active')}
                            </Tag>
                          </Flex>
                        </MobileCard>
                      </List.Item>
                    )}
                  />
                ) : (
                  // eslint-disable-next-line no-restricted-syntax
                  <Flex style={{ width: '100%', overflowX: 'auto' }}>
                    <Table<GetOrganizationDashboard_ResultSet11>
                      dataSource={machineIssues}
                      pagination={false}
                      columns={machineIssueColumns}
                      data-testid="dashboard-table-machine-issues"
                      rowKey={(record) => `${record.teamName}-${record.machineName}`}
                    />
                  </Flex>
                )}
              </Flex>
            )}

            {featureAccess?.hasAdvancedAnalytics && queueStats.highestPriorityPending !== null && (
              <Flex vertical>
                <Typography.Text strong>
                  <ThunderboltOutlined /> {t('dashboard.widgets.queueDetails.priorityBreakdown')}
                </Typography.Text>
                <Flex vertical className="w-full">
                  <Flex align="center" justify="space-between">
                    <Typography.Text>
                      {t('dashboard.widgets.queueDetails.highestPriority')}
                    </Typography.Text>
                    <Badge
                      count={queueStats.highestPriorityPending}
                      showZero
                      data-testid="dashboard-badge-highest-priority"
                    />
                  </Flex>
                  <Flex align="center" justify="space-between">
                    <Typography.Text>
                      {t('dashboard.widgets.queueDetails.highPriority')}
                    </Typography.Text>
                    <Badge
                      count={queueStats.highPriorityPending ?? 0}
                      showZero
                      data-testid="dashboard-badge-high-priority"
                    />
                  </Flex>
                  <Flex align="center" justify="space-between">
                    <Typography.Text>
                      {t('dashboard.widgets.queueDetails.normalPriority')}
                    </Typography.Text>
                    <Badge
                      count={queueStats.normalPriorityPending ?? 0}
                      showZero
                      data-testid="dashboard-badge-normal-priority"
                    />
                  </Flex>
                  <Flex align="center" justify="space-between">
                    <Typography.Text>
                      {t('dashboard.widgets.queueDetails.lowPriority')}
                    </Typography.Text>
                    <Badge
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
