import React, { useCallback, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Flex,
  Input,
  Popconfirm,
  Row,
  Space,
  Statistic,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import { useDeleteUserRequest, useGetUserRequests } from '@/api/api-hooks.generated';
import {
  createDateColumn,
  createStatusColumn,
  createTruncatedColumn,
} from '@/components/common/columns';
import { createActionColumn } from '@/components/common/columns/factories/action';
import { MobileCard } from '@/components/common/MobileCard';
import ResourceListView from '@/components/common/ResourceListView';
import { useMessage } from '@/hooks';
import { createDateSorter } from '@/platform';
import { selectUser } from '@/store/auth/authSelectors';
import {
  BranchesOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LinkOutlined,
  ReloadOutlined,
  SearchOutlined,
  StopOutlined,
} from '@/utils/optimizedIcons';
import type { GetUserRequests_ResultSet1 } from '@rediacc/shared/types';
import type { ColumnsType } from 'antd/es/table';

dayjs.extend(relativeTime);

const UserSessionsTab: React.FC = () => {
  const { t } = useTranslation('system');
  const message = useMessage();
  const user = useSelector(selectUser);
  const [searchTerm, setSearchTerm] = useState('');

  const { data: sessions = [], isLoading, refetch } = useGetUserRequests();
  const deleteUserRequestMutation = useDeleteUserRequest();

  /* eslint-disable react-hooks/preserve-manual-memoization */
  const handleTerminateSession = useCallback(
    async (session: GetUserRequests_ResultSet1) => {
      try {
        await deleteUserRequestMutation.mutateAsync({ targetRequestId: session.requestId });
        if (session.userEmail === user?.email) {
          message.warning('system:userSessions.selfTerminateWarning');
        }
      } catch {
        // noop
      }
    },
    [deleteUserRequestMutation, user?.email, message]
  );
  /* eslint-enable react-hooks/preserve-manual-memoization */

  const filteredSessions = sessions.filter((session: GetUserRequests_ResultSet1) => {
    const searchLower = searchTerm.toLowerCase();
    const searchFields = [
      session.userEmail,
      session.ipAddress,
      session.sessionName,
      session.userAgent,
    ];
    return searchFields.some((field) => field?.toLowerCase().includes(searchLower));
  });

  const activeSessions = sessions.filter((session: GetUserRequests_ResultSet1) => session.isActive);

  const userAgentFallback = t('userSessions.notAvailable');

  const userAgentColumn = createTruncatedColumn<GetUserRequests_ResultSet1>({
    title: t('userSessions.columns.userAgent'),
    dataIndex: 'userAgent',
    key: 'userAgent',
    width: 300,
    renderText: (agent: string | null | undefined) => agent ?? userAgentFallback,
    renderWrapper: (content) => <Typography.Text>{content}</Typography.Text>,
  });

  const statusColumn = createStatusColumn<GetUserRequests_ResultSet1>({
    title: t('userSessions.columns.status'),
    dataIndex: 'isActive',
    key: 'isActive',
    statusMap: {
      true: { icon: <CheckCircleOutlined />, label: t('userSessions.active') },
      false: { icon: <StopOutlined />, label: t('userSessions.inactive') },
    },
  });

  const createdAtColumn = createDateColumn<GetUserRequests_ResultSet1>({
    title: t('userSessions.columns.createdAt'),
    dataIndex: 'createdAt',
    key: 'createdAt',
    width: 180,
    format: 'YYYY-MM-DD HH:mm:ss',
    sorter: createDateSorter<GetUserRequests_ResultSet1>('createdAt'),
    defaultSortOrder: 'descend',
  });

  const lastActivityColumn = createDateColumn<GetUserRequests_ResultSet1>({
    title: t('userSessions.columns.lastActivity'),
    dataIndex: 'lastActivity',
    key: 'lastActivity',
    width: 150,
    sorter: createDateSorter<GetUserRequests_ResultSet1>('lastActivity'),
    render: (value: string | Date | null | undefined) => {
      if (!value) return '-';
      const timestamp = typeof value === 'string' ? value : value.toString();
      return dayjs(timestamp).fromNow();
    },
  });

  const actionsColumn = createActionColumn<GetUserRequests_ResultSet1>({
    title: t('userSessions.columns.actions'),
    width: 140,
    fixed: 'right',
    renderActions: (record) => (
      <Popconfirm
        title={
          <Typography.Text className="text-sm font-medium">
            {t('userSessions.confirmTerminate')}
          </Typography.Text>
        }
        description={
          <Typography.Text>
            {record.userEmail === user?.email
              ? t('userSessions.confirmTerminateSelf')
              : t('userSessions.confirmTerminateOther', { email: record.userEmail })}
          </Typography.Text>
        }
        onConfirm={() => handleTerminateSession(record)}
        okText={t('common:yes')}
        cancelText={t('common:no')}
        disabled={!record.isActive}
      >
        <Tooltip title={t('userSessions.terminate')}>
          <Button
            data-testid={`sessions-terminate-${record.requestId}`}
            variant="link"
            danger
            icon={<CloseCircleOutlined />}
            disabled={!record.isActive}
            loading={deleteUserRequestMutation.isPending}
            aria-label={t('userSessions.terminate')}
          />
        </Tooltip>
      </Popconfirm>
    ),
  });

  const columns: ColumnsType<GetUserRequests_ResultSet1> = [
    {
      title: t('userSessions.columns.user'),
      dataIndex: 'userEmail',
      key: 'userEmail',
      width: 200,
      render: (email: string) => (
        <Space size="small">
          <Typography.Text>{email}</Typography.Text>
          {email === user?.email && (
            <Tag className="text-xs font-medium" data-testid="sessions-current-session-tag">
              {t('userSessions.currentSession')}
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: t('userSessions.columns.sessionName'),
      dataIndex: 'sessionName',
      key: 'sessionName',
      width: 220,
      render: (name: string, record: GetUserRequests_ResultSet1) => {
        const childCount = filteredSessions.filter(
          (session) => session.parentRequestId === record.requestId
        ).length;

        return (
          <Space size="small">
            <Typography.Text>{name}</Typography.Text>
            {record.parentRequestId && (
              <Tooltip title={t('userSessions.forkToken')}>
                <Tag
                  icon={<LinkOutlined />}
                  className="text-xs font-medium"
                  data-testid="sessions-fork-tag"
                >
                  {t('userSessions.fork')}
                </Tag>
              </Tooltip>
            )}
            {childCount > 0 && (
              <Tooltip title={t('userSessions.hasChildren', { count: childCount })}>
                <Tag
                  icon={<BranchesOutlined />}
                  className="text-xs font-medium"
                  data-testid="sessions-child-tag"
                >
                  {childCount}
                </Tag>
              </Tooltip>
            )}
          </Space>
        );
      },
    },
    {
      title: t('userSessions.columns.ipAddress'),
      dataIndex: 'ipAddress',
      key: 'ipAddress',
      width: 140,
      render: (ip: string | null) => (
        <Typography.Text>{ip ?? t('userSessions.notAvailable')}</Typography.Text>
      ),
    },
    userAgentColumn,
    {
      ...statusColumn,
      render: (isActive: boolean, record, index) =>
        statusColumn.render?.(String(isActive), record, index) as React.ReactNode,
    },
    createdAtColumn,
    lastActivityColumn,
    {
      title: t('userSessions.columns.duration'),
      key: 'duration',
      width: 120,
      render: (_, record) => {
        const duration = dayjs(record.lastActivity).diff(dayjs(record.createdAt), 'minute');
        return `${duration} ${t('userSessions.minutes')}`;
      },
    },
    actionsColumn,
  ];

  /* eslint-disable react-hooks/preserve-manual-memoization */
  const mobileRender = useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: GetUserRequests_ResultSet1) => {
      const childCount = filteredSessions.filter(
        (session) => session.parentRequestId === record.requestId
      ).length;

      const actions = (
        <Popconfirm
          title={t('userSessions.confirmTerminate')}
          description={
            record.userEmail === user?.email
              ? t('userSessions.confirmTerminateSelf')
              : t('userSessions.confirmTerminateOther', { email: record.userEmail })
          }
          onConfirm={() => handleTerminateSession(record)}
          okText={t('common:yes')}
          cancelText={t('common:no')}
          disabled={!record.isActive}
        >
          <Tooltip title={t('userSessions.terminate')}>
            <Button
              type="text"
              size="small"
              danger
              icon={<CloseCircleOutlined />}
              disabled={!record.isActive}
              loading={deleteUserRequestMutation.isPending}
              aria-label={t('userSessions.terminate')}
            />
          </Tooltip>
        </Popconfirm>
      );

      return (
        <MobileCard actions={actions}>
          <Space wrap>
            <Typography.Text strong>{record.userEmail}</Typography.Text>
            {record.userEmail === user?.email && <Tag>{t('userSessions.currentSession')}</Tag>}
            {record.isActive ? (
              <Tag color="success" icon={<CheckCircleOutlined />}>
                {t('userSessions.active')}
              </Tag>
            ) : (
              <Tag icon={<StopOutlined />}>{t('userSessions.inactive')}</Tag>
            )}
          </Space>
          <Space wrap>
            <Typography.Text type="secondary">{record.sessionName}</Typography.Text>
            {record.parentRequestId && (
              <Tag icon={<LinkOutlined />} className="text-xs">
                {t('userSessions.fork')}
              </Tag>
            )}
            {childCount > 0 && (
              <Tag icon={<BranchesOutlined />} className="text-xs">
                {childCount}
              </Tag>
            )}
          </Space>
          <Typography.Text type="secondary" className="text-xs">
            {t('userSessions.ipLabel')}: {record.ipAddress ?? t('userSessions.notAvailable')}
          </Typography.Text>
          <Typography.Text type="secondary" className="text-xs">
            {t('userSessions.columns.lastActivity')}: {dayjs(record.lastActivity).fromNow()}
          </Typography.Text>
        </MobileCard>
      );
    },
    [t, user?.email, filteredSessions, handleTerminateSession, deleteUserRequestMutation.isPending]
  );
  /* eslint-enable react-hooks/preserve-manual-memoization */

  return (
    <Flex vertical data-testid="user-sessions-tab">
      <Row gutter={16}>
        <Col span={6}>
          <Card data-testid="sessions-stat-total">
            <Statistic
              title={
                <Typography.Text className="text-sm font-medium">
                  {t('userSessions.totalSessions')}
                </Typography.Text>
              }
              value={sessions.length}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card data-testid="sessions-stat-active">
            <Statistic
              title={
                <Typography.Text className="text-sm font-medium">
                  {t('userSessions.activeSessions')}
                </Typography.Text>
              }
              value={activeSessions.length}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card data-testid="sessions-stat-unique-users">
            <Statistic
              title={
                <Typography.Text className="text-sm font-medium">
                  {t('userSessions.uniqueUsers')}
                </Typography.Text>
              }
              value={new Set(sessions.map((session) => session.userEmail)).size}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card data-testid="sessions-stat-average-duration">
            <Statistic
              title={
                <Typography.Text className="text-sm font-medium">
                  {t('userSessions.averageDuration')}
                </Typography.Text>
              }
              value={
                sessions.length > 0
                  ? Math.round(
                      sessions.reduce((acc: number, session: GetUserRequests_ResultSet1) => {
                        const duration = dayjs(session.lastActivity).diff(
                          dayjs(session.createdAt),
                          'minute'
                        );
                        return acc + duration;
                      }, 0) / sessions.length
                    )
                  : 0
              }
              suffix={<Typography.Text>{t('userSessions.minutes')}</Typography.Text>}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title={
          <Flex justify="space-between" align="center">
            <Space size={8}>
              <Typography.Text className="text-base font-semibold">
                {t('userSessions.title')}
              </Typography.Text>
              <Tooltip title={t('common:actions.refresh')}>
                <Button
                  className="min-w-btn min-h-btn text-base"
                  data-testid="sessions-refresh-button"
                  icon={<ReloadOutlined />}
                  onClick={() => refetch()}
                  loading={isLoading}
                  aria-label={t('common:actions.refresh')}
                />
              </Tooltip>
            </Space>
            <Input
              className="w-full-max-sm"
              data-testid="sessions-search-input"
              placeholder={t('userSessions.searchPlaceholder')}
              prefix={<SearchOutlined />}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              autoComplete="off"
            />
          </Flex>
        }
      >
        <ResourceListView<GetUserRequests_ResultSet1>
          data-testid="sessions-table"
          columns={columns}
          data={filteredSessions}
          rowKey={(record) => (record.requestId ?? '').toString()}
          loading={isLoading}
          mobileRender={mobileRender}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => (
              <Typography.Text>{t('userSessions.totalCount', { count: total })}</Typography.Text>
            ),
          }}
          onRow={(record) => {
            const props: React.HTMLAttributes<HTMLElement> & Record<string, string> = {
              'data-testid': `sessions-row-${record.requestId ?? ''}`,
            };
            return props;
          }}
        />
      </Card>
    </Flex>
  );
};

export default UserSessionsTab;
