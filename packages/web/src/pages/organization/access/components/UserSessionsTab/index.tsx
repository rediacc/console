import React, { useState } from 'react';
import { Button, Card, Col, Flex, Input, Popconfirm, Row, Space, Statistic, Table, Tag, Tooltip, Typography } from 'antd';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import { type UserRequest, useDeleteUserRequest, useUserRequests } from '@/api/queries/users';
import {
  createActionColumn,
  createDateColumn,
  createStatusColumn,
  createTruncatedColumn,
} from '@/components/common/columns';
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
import type { ColumnsType } from 'antd/es/table';

dayjs.extend(relativeTime);

const UserSessionsTab: React.FC = () => {
  const { t } = useTranslation('system');
  const message = useMessage();
  const user = useSelector(selectUser);
  const [searchTerm, setSearchTerm] = useState('');

  const { data: sessions = [], isLoading, refetch } = useUserRequests();
  const deleteUserRequestMutation = useDeleteUserRequest();

  const handleTerminateSession = async (session: UserRequest) => {
    try {
      await deleteUserRequestMutation.mutateAsync({ targetRequestId: session.requestId });
      if (session.userEmail === user?.email) {
        message.warning('system:userSessions.selfTerminateWarning');
      }
    } catch {
      // noop
    }
  };

  const filteredSessions = sessions.filter((session: UserRequest) => {
    const searchLower = searchTerm.toLowerCase();
    return (
      session.userEmail.toLowerCase().includes(searchLower) ||
      (session.ipAddress && session.ipAddress.toLowerCase().includes(searchLower)) ||
      session.sessionName.toLowerCase().includes(searchLower) ||
      (session.userAgent && session.userAgent.toLowerCase().includes(searchLower))
    );
  });

  const activeSessions = sessions.filter((session: UserRequest) => session.isActive);

  const userAgentFallback = t('userSessions.notAvailable');

  const userAgentColumn = createTruncatedColumn<UserRequest>({
    title: t('userSessions.columns.userAgent'),
    dataIndex: 'userAgent',
    key: 'userAgent',
    width: 300,
    renderText: (agent: string | null | undefined) => agent ?? userAgentFallback,
    renderWrapper: (content, fullText) => (
      <span
        style={{
          fontSize: 14,
          color: fullText === userAgentFallback ? 'var(--ant-color-text-secondary)' : undefined,
        }}
      >
        {content}
      </span>
    ),
  });

  const statusColumn = createStatusColumn<UserRequest>({
    title: t('userSessions.columns.status'),
    dataIndex: 'isActive',
    key: 'isActive',
    statusMap: {
      true: { icon: <CheckCircleOutlined />, label: t('userSessions.active'), color: 'success' },
      false: { icon: <StopOutlined />, label: t('userSessions.inactive'), color: 'default' },
    },
  });

  const createdAtColumn = createDateColumn<UserRequest>({
    title: t('userSessions.columns.createdAt'),
    dataIndex: 'createdAt',
    key: 'createdAt',
    width: 180,
    format: 'YYYY-MM-DD HH:mm:ss',
    sorter: createDateSorter<UserRequest>('createdAt'),
    defaultSortOrder: 'descend',
  });

  const lastActivityColumn = createDateColumn<UserRequest>({
    title: t('userSessions.columns.lastActivity'),
    dataIndex: 'lastActivity',
    key: 'lastActivity',
    width: 150,
    sorter: createDateSorter<UserRequest>('lastActivity'),
    render: (value: string | Date | null | undefined) => {
      if (!value) return '-';
      const timestamp = typeof value === 'string' ? value : value.toString();
      return dayjs(timestamp).fromNow();
    },
  });

  const actionsColumn = createActionColumn<UserRequest>({
    title: t('userSessions.columns.actions'),
    width: 140,
    fixed: 'end',
    renderActions: (record) => (
      <Popconfirm
        title={<span style={{ fontSize: 14, fontWeight: 500 }}>{t('userSessions.confirmTerminate')}</span>}
        description={
          <span style={{ fontSize: 14 }}>
            {record.userEmail === user?.email
              ? t('userSessions.confirmTerminateSelf')
              : t('userSessions.confirmTerminateOther', { email: record.userEmail })}
          </span>
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

  const columns: ColumnsType<UserRequest> = [
    {
      title: t('userSessions.columns.user'),
      dataIndex: 'userEmail',
      key: 'userEmail',
      width: 200,
      render: (email: string) => (
        <Space size="small">
          <span style={{ fontSize: 14 }}>{email}</span>
          {email === user?.email && (
            <Tag
              color="processing"
              style={{ fontSize: 12, fontWeight: 500 }}
              data-testid="sessions-current-session-tag"
            >
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
      render: (name: string, record: UserRequest) => {
        const childCount = filteredSessions.filter(
          (session) => session.parentRequestId === record.requestId
        ).length;

        return (
          <Space size="small">
            <span style={{ fontSize: 14 }}>{name}</span>
            {record.parentRequestId && (
              <Tooltip title={t('userSessions.forkToken')}>
                <Tag
                  color="processing"
                  icon={<LinkOutlined />}
                  style={{ fontSize: 12, fontWeight: 500 }}
                  data-testid="sessions-fork-tag"
                >
                  {t('userSessions.fork')}
                </Tag>
              </Tooltip>
            )}
            {childCount > 0 && (
              <Tooltip title={t('userSessions.hasChildren', { count: childCount })}>
                <Tag
                  color="warning"
                  icon={<BranchesOutlined />}
                  style={{ fontSize: 12, fontWeight: 500 }}
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
        <span
          style={{
            fontSize: 14,
            color: !ip ? 'var(--ant-color-text-secondary)' : undefined,
          }}
        >
          {ip || t('userSessions.notAvailable')}
        </span>
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

  return (
    <Flex vertical gap={16} data-testid="user-sessions-tab">
      <Row gutter={16}>
        <Col span={6}>
          <Card data-testid="sessions-stat-total">
            <Statistic
              title={<span style={{ fontSize: 14, fontWeight: 500 }}>{t('userSessions.totalSessions')}</span>}
              value={sessions.length}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card data-testid="sessions-stat-active">
            <Statistic
              title={<span style={{ fontSize: 14, fontWeight: 500 }}>{t('userSessions.activeSessions')}</span>}
              value={activeSessions.length}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card data-testid="sessions-stat-unique-users">
            <Statistic
              title={<span style={{ fontSize: 14, fontWeight: 500 }}>{t('userSessions.uniqueUsers')}</span>}
              value={new Set(sessions.map((session) => session.userEmail)).size}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card data-testid="sessions-stat-average-duration">
            <Statistic
              title={<span style={{ fontSize: 14, fontWeight: 500 }}>{t('userSessions.averageDuration')}</span>}
              value={
                sessions.length > 0
                  ? Math.round(
                      sessions.reduce((acc: number, session: UserRequest) => {
                        const duration = dayjs(session.lastActivity).diff(
                          dayjs(session.createdAt),
                          'minute'
                        );
                        return acc + duration;
                      }, 0) / sessions.length
                    )
                  : 0
              }
              suffix={<span style={{ fontSize: 12 }}>{t('userSessions.minutes')}</span>}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title={
          <Flex justify="space-between" align="center">
            <Space size={8}>
              <Typography.Text style={{ fontSize: 16, fontWeight: 600 }}>{t('userSessions.title')}</Typography.Text>
              <Tooltip title={t('common:actions.refresh')}>
                <Button
                  style={{ minWidth: 40, minHeight: 40, fontSize: 16 }}
                  data-testid="sessions-refresh-button"
                  icon={<ReloadOutlined />}
                  onClick={() => refetch()}
                  loading={isLoading}
                  aria-label={t('common:actions.refresh')}
                />
              </Tooltip>
            </Space>
            <Input
              style={{ width: 'min(360px, 100%)', maxWidth: '100%' }}
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
        <Table<UserRequest>
          data-testid="sessions-table"
          columns={columns}
          dataSource={filteredSessions}
          rowKey={(record) => record.requestId.toString()}
          loading={isLoading}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t('userSessions.totalCount', { count: total })}
              </Typography.Text>
            ),
          }}
          scroll={{ x: 1500 }}
          onRow={(record) =>
            ({
              'data-testid': `sessions-row-${record.requestId}`,
            }) as React.HTMLAttributes<HTMLTableRowElement>
          }
        />
      </Card>
    </Flex>
  );
};

export default UserSessionsTab;
