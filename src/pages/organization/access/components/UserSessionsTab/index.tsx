import React, { useState } from 'react'
import { Table, Button, Row, Col, Space, Popconfirm, message, Tooltip } from 'antd'
import {
  SearchOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  LinkOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  StopOutlined,
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useUserRequests, useDeleteUserRequest, type UserRequest } from '@/api/queries/users'
import { useSelector } from 'react-redux'
import { selectUser } from '@/store/auth/authSelectors'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import { createDateSorter } from '@/core'
import {
  createActionColumn,
  createDateColumn,
  createStatusColumn,
  createTruncatedColumn,
} from '@/components/common/columns'
import {
  TabContainer,
  StatCard,
  StatTitle,
  StatMetric,
  StatSuffix,
  TableCard,
  CardTitleRow,
  CardTitleText,
  RefreshButton,
  SearchInput,
  TableWrapper,
  SessionTag,
  CellText,
  SummaryText,
} from './styles'

dayjs.extend(relativeTime)

const UserSessionsTab: React.FC = () => {
  const { t } = useTranslation('system')
  const user = useSelector(selectUser)
  const [searchTerm, setSearchTerm] = useState('')

  const { data: sessions = [], isLoading, refetch } = useUserRequests()
  const deleteUserRequestMutation = useDeleteUserRequest()

  const handleTerminateSession = async (session: UserRequest) => {
    try {
      await deleteUserRequestMutation.mutateAsync({ requestId: session.requestId })
      if (session.userEmail === user?.email) {
        message.warning(t('userSessions.selfTerminateWarning'))
      }
    } catch (error) {
      // noop
    }
  }

  const filteredSessions = sessions.filter((session: UserRequest) => {
    const searchLower = searchTerm.toLowerCase()
    return (
      session.userEmail.toLowerCase().includes(searchLower) ||
      (session.ipAddress && session.ipAddress.toLowerCase().includes(searchLower)) ||
      session.sessionName.toLowerCase().includes(searchLower) ||
      (session.userAgent && session.userAgent.toLowerCase().includes(searchLower))
    )
  })

  const activeSessions = sessions.filter((session: UserRequest) => session.isActive)

  const userAgentFallback = t('userSessions.notAvailable')

  const userAgentColumn = createTruncatedColumn<UserRequest>({
    title: t('userSessions.columns.userAgent'),
    dataIndex: 'userAgent',
    key: 'userAgent',
    width: 300,
    renderText: (agent: string | null | undefined) => agent ?? userAgentFallback,
    renderWrapper: (content, fullText) => (
      <CellText $muted={fullText === userAgentFallback}>{content}</CellText>
    ),
  })

  const statusColumn = createStatusColumn<UserRequest>({
    title: t('userSessions.columns.status'),
    dataIndex: 'isActive',
    key: 'isActive',
    statusMap: {
      true: { icon: <CheckCircleOutlined />, label: t('userSessions.active'), color: 'success' },
      false: { icon: <StopOutlined />, label: t('userSessions.inactive'), color: 'default' },
    },
  })

  const createdAtColumn = createDateColumn<UserRequest>({
    title: t('userSessions.columns.createdAt'),
    dataIndex: 'createdAt',
    key: 'createdAt',
    width: 180,
    format: 'YYYY-MM-DD HH:mm:ss',
    sorter: createDateSorter<UserRequest>('createdAt'),
    defaultSortOrder: 'descend',
  })

  const lastActivityColumn = createDateColumn<UserRequest>({
    title: t('userSessions.columns.lastActivity'),
    dataIndex: 'lastActivity',
    key: 'lastActivity',
    width: 150,
    sorter: createDateSorter<UserRequest>('lastActivity'),
    render: (value: string | Date | null | undefined) => {
      if (!value) return '-'
      const timestamp = typeof value === 'string' ? value : value.toString()
      return dayjs(timestamp).fromNow()
    },
  })

  const actionsColumn = createActionColumn<UserRequest>({
    title: t('userSessions.columns.actions'),
    width: 140,
    fixed: 'right',
    renderActions: (record) => (
      <Popconfirm
        title={<StatTitle>{t('userSessions.confirmTerminate')}</StatTitle>}
        description={
          <CellText>
            {record.userEmail === user?.email
              ? t('userSessions.confirmTerminateSelf')
              : t('userSessions.confirmTerminateOther', { email: record.userEmail })}
          </CellText>
        }
        onConfirm={() => handleTerminateSession(record)}
        okText={t('common:yes')}
        cancelText={t('common:no')}
        disabled={!record.isActive}
      >
        <Tooltip title={t('userSessions.terminate')}>
          <Button
            data-testid={`sessions-terminate-${record.requestId}`}
            type="link"
            danger
            icon={<CloseCircleOutlined />}
            disabled={!record.isActive}
            loading={deleteUserRequestMutation.isPending}
            aria-label={t('userSessions.terminate')}
          />
        </Tooltip>
      </Popconfirm>
    ),
  })

  const columns: ColumnsType<UserRequest> = [
    {
      title: t('userSessions.columns.user'),
      dataIndex: 'userEmail',
      key: 'userEmail',
      width: 200,
      render: (email: string) => (
        <Space size="small">
          <CellText>{email}</CellText>
          {email === user?.email && (
            <SessionTag color="blue" data-testid="sessions-current-session-tag">
              {t('userSessions.currentSession')}
            </SessionTag>
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
          (session) => session.parentRequestId === record.requestId,
        ).length

        return (
          <Space size="small">
            <CellText>{name}</CellText>
            {record.parentRequestId && (
              <Tooltip title={t('userSessions.forkToken')}>
                <SessionTag color="blue" icon={<LinkOutlined />} data-testid="sessions-fork-tag">
                  {t('userSessions.fork')}
                </SessionTag>
              </Tooltip>
            )}
            {childCount > 0 && (
              <Tooltip title={t('userSessions.hasChildren', { count: childCount })}>
                <SessionTag
                  color="purple"
                  icon={<BranchesOutlined />}
                  data-testid="sessions-child-tag"
                >
                  {childCount}
                </SessionTag>
              </Tooltip>
            )}
          </Space>
        )
      },
    },
    {
      title: t('userSessions.columns.ipAddress'),
      dataIndex: 'ipAddress',
      key: 'ipAddress',
      width: 140,
      render: (ip: string | null) => (
        <CellText $muted={!ip}>{ip || t('userSessions.notAvailable')}</CellText>
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
        const duration = dayjs(record.lastActivity).diff(dayjs(record.createdAt), 'minute')
        return `${duration} ${t('userSessions.minutes')}`
      },
    },
    actionsColumn,
  ]

  return (
    <TabContainer data-testid="user-sessions-tab">
      <Row gutter={16}>
        <Col span={6}>
          <StatCard data-testid="sessions-stat-total">
            <StatMetric
              title={<StatTitle>{t('userSessions.totalSessions')}</StatTitle>}
              value={sessions.length}
            />
          </StatCard>
        </Col>
        <Col span={6}>
          <StatCard data-testid="sessions-stat-active">
            <StatMetric
              title={<StatTitle>{t('userSessions.activeSessions')}</StatTitle>}
              value={activeSessions.length}
              $color="var(--color-success)"
            />
          </StatCard>
        </Col>
        <Col span={6}>
          <StatCard data-testid="sessions-stat-unique-users">
            <StatMetric
              title={<StatTitle>{t('userSessions.uniqueUsers')}</StatTitle>}
              value={new Set(sessions.map((session) => session.userEmail)).size}
            />
          </StatCard>
        </Col>
        <Col span={6}>
          <StatCard data-testid="sessions-stat-average-duration">
            <StatMetric
              title={<StatTitle>{t('userSessions.averageDuration')}</StatTitle>}
              value={
                sessions.length > 0
                  ? Math.round(
                      sessions.reduce((acc: number, session: UserRequest) => {
                        const duration = dayjs(session.lastActivity).diff(
                          dayjs(session.createdAt),
                          'minute',
                        )
                        return acc + duration
                      }, 0) / sessions.length,
                    )
                  : 0
              }
              suffix={<StatSuffix>{t('userSessions.minutes')}</StatSuffix>}
            />
          </StatCard>
        </Col>
      </Row>

      <TableCard
        title={
          <CardTitleRow>
            <CardTitleText>{t('userSessions.title')}</CardTitleText>
            <Tooltip title={t('common:actions.refresh')}>
              <RefreshButton
                data-testid="sessions-refresh-button"
                icon={<ReloadOutlined />}
                onClick={() => refetch()}
                loading={isLoading}
                aria-label={t('common:actions.refresh')}
              />
            </Tooltip>
          </CardTitleRow>
        }
        extra={
          <SearchInput
            data-testid="sessions-search-input"
            placeholder={t('userSessions.searchPlaceholder')}
            prefix={<SearchOutlined />}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            autoComplete="off"
          />
        }
      >
        <TableWrapper>
          <Table
            data-testid="sessions-table"
            columns={columns}
            dataSource={filteredSessions}
            rowKey={(record) => record.requestId.toString()}
            loading={isLoading}
            pagination={{
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total) => (
                <SummaryText>{t('userSessions.totalCount', { count: total })}</SummaryText>
              ),
            }}
            scroll={{ x: 1500 }}
            onRow={(record) =>
              ({
                'data-testid': `sessions-row-${record.requestId}`,
              } as React.HTMLAttributes<HTMLTableRowElement>)
            }
          />
        </TableWrapper>
      </TableCard>
    </TabContainer>
  )
}

export default UserSessionsTab
