import React, { useState } from 'react'
import { Table, Button, Card, Statistic, Row, Col, Tag, Input, Space, Popconfirm, message, Tooltip } from 'antd'
import { SearchOutlined, CloseCircleOutlined, ReloadOutlined, LinkOutlined, BranchesOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useUserRequests, useDeleteUserRequest, type UserRequest } from '@/api/queries/users'
import { useSelector } from 'react-redux'
import { selectUser } from '@/store/auth/authSelectors'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import { useComponentStyles, useTableStyles, useFormStyles } from '@/hooks/useComponentStyles'
import { createDateSorter } from '@/utils/tableSorters'

dayjs.extend(relativeTime)

const UserSessionsTab: React.FC = () => {
  const { t } = useTranslation('system')
  const user = useSelector(selectUser)
  const [searchTerm, setSearchTerm] = useState('')
  
  const styles = useComponentStyles()
  const tableStyles = useTableStyles()
  const formStyles = useFormStyles()
  
  const { data: sessions = [], isLoading, refetch } = useUserRequests()
  const deleteUserRequestMutation = useDeleteUserRequest()

  const handleTerminateSession = async (session: UserRequest) => {
    try {
      await deleteUserRequestMutation.mutateAsync({ requestId: session.requestId })
      if (session.userEmail === user?.email) {
        message.warning(t('userSessions.selfTerminateWarning'))
      }
    } catch (error) {
      // Failed to terminate session
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

  const columns: ColumnsType<UserRequest> = [
    {
      title: t('userSessions.columns.user'),
      dataIndex: 'userEmail',
      key: 'userEmail',
      width: 200,
      render: (email: string) => (
        <Space>
          <span style={styles.body}>{email}</span>
          {email === user?.email && (
            <Tag 
              color="blue" 
              style={{
                borderRadius: 'var(--border-radius-sm)',
                ...styles.caption
              }}
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
        const childCount = filteredSessions.filter(s => s.parentRequestId === record.requestId).length
        return (
          <Space>
            <span style={styles.body}>{name}</span>
            {record.parentRequestId && (
              <Tooltip title={t('userSessions.forkToken')}>
                <Tag
                  color="blue"
                  icon={<LinkOutlined />}
                  style={{
                    borderRadius: 'var(--border-radius-sm)',
                    ...styles.caption
                  }}
                >
                  {t('userSessions.fork')}
                </Tag>
              </Tooltip>
            )}
            {childCount > 0 && (
              <Tooltip title={t('userSessions.hasChildren', { count: childCount })}>
                <Tag
                  color="purple"
                  icon={<BranchesOutlined />}
                  style={{
                    borderRadius: 'var(--border-radius-sm)',
                    ...styles.caption
                  }}
                >
                  {childCount}
                </Tag>
              </Tooltip>
            )}
          </Space>
        )
      }
    },
    {
      title: t('userSessions.columns.ipAddress'),
      dataIndex: 'ipAddress',
      key: 'ipAddress',
      width: 140,
      render: (ip: string | null) => (
        <span style={{ ...styles.body, color: ip ? 'inherit' : 'var(--color-text-tertiary)' }}>
          {ip ? ip : t('userSessions.notAvailable')}
        </span>
      )
    },
    {
      title: t('userSessions.columns.userAgent'),
      dataIndex: 'userAgent',
      key: 'userAgent',
      width: 300,
      ellipsis: true,
      render: (agent: string | null) => (
        <Tooltip title={agent ? agent : t('userSessions.notAvailable')}>
          <span style={{ ...styles.body, color: agent ? 'inherit' : 'var(--color-text-tertiary)' }}>
            {agent ? agent : t('userSessions.notAvailable')}
          </span>
        </Tooltip>
      )
    },
    {
      title: t('userSessions.columns.status'),
      dataIndex: 'isActive',
      key: 'isActive',
      width: 100,
      render: (isActive: boolean) => (
        <Tag 
          color={isActive ? 'green' : 'red'}
          style={{
            borderRadius: 'var(--border-radius-sm)',
            ...styles.caption
          }}
        >
          {isActive ? t('userSessions.active') : t('userSessions.inactive')}
        </Tag>
      ),
    },
    {
      title: t('userSessions.columns.createdAt'),
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 180,
      render: (date: string) => dayjs(date).format('YYYY-MM-DD HH:mm:ss'),
      sorter: createDateSorter<UserRequest>('createdAt'),
      defaultSortOrder: 'descend',
    },
    {
      title: t('userSessions.columns.lastActivity'),
      dataIndex: 'lastActivity',
      key: 'lastActivity',
      width: 150,
      render: (date: string) => dayjs(date).fromNow(),
    },
    {
      title: t('userSessions.columns.duration'),
      key: 'duration',
      width: 120,
      render: (_, record) => {
        const duration = dayjs(record.lastActivity).diff(dayjs(record.createdAt), 'minute')
        return `${duration} ${t('userSessions.minutes')}`
      },
    },
    {
      title: t('userSessions.columns.actions'),
      key: 'actions',
      width: 120,
      fixed: 'right',
      render: (_, record) => (
        <Popconfirm
          title={<span style={styles.label}>{t('userSessions.confirmTerminate')}</span>}
          description={
            <span style={styles.body}>
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
              type="link"
              danger
              icon={<CloseCircleOutlined style={styles.icon.small} />}
              disabled={!record.isActive}
              loading={deleteUserRequestMutation.isPending}
              style={{
                ...tableStyles.tableActionButton,
                ...styles.controlSurfaceSmall
              }}
              aria-label={t('userSessions.terminate')}
            />
          </Tooltip>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div className="user-sessions-tab" style={styles.container}>
      <Row gutter={16} style={styles.marginBottom.lg}>
        <Col span={6}>
          <Card 
            data-testid="sessions-stat-total"
            style={{
              ...styles.card,
              boxShadow: 'var(--shadow-sm)',
              border: '1px solid var(--color-border-secondary)'
            }}
          >
            <Statistic
              title={<span style={styles.label}>{t('userSessions.totalSessions')}</span>}
              value={sessions.length}
              valueStyle={styles.heading3}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card 
            data-testid="sessions-stat-active"
            style={{
              ...styles.card,
              boxShadow: 'var(--shadow-sm)',
              border: '1px solid var(--color-border-secondary)'
            }}
          >
            <Statistic
              title={<span style={styles.label}>{t('userSessions.activeSessions')}</span>}
              value={activeSessions.length}
              valueStyle={{ 
                ...styles.heading3,
                color: 'var(--color-success)'
              }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card 
            data-testid="sessions-stat-unique-users"
            style={{
              ...styles.card,
              boxShadow: 'var(--shadow-sm)',
              border: '1px solid var(--color-border-secondary)'
            }}
          >
            <Statistic
              title={<span style={styles.label}>{t('userSessions.uniqueUsers')}</span>}
              value={new Set(sessions.map((s: UserRequest) => s.userEmail)).size}
              valueStyle={styles.heading3}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card 
            data-testid="sessions-stat-average-duration"
            style={{
              ...styles.card,
              boxShadow: 'var(--shadow-sm)',
              border: '1px solid var(--color-border-secondary)'
            }}
          >
            <Statistic
              title={<span style={styles.label}>{t('userSessions.averageDuration')}</span>}
              value={
                sessions.length > 0
                  ? Math.round(
                      sessions.reduce((acc: number, session: UserRequest) => {
                        const duration = dayjs(session.lastActivity).diff(
                          dayjs(session.createdAt),
                          'minute'
                        )
                        return acc + duration
                      }, 0) / sessions.length
                    )
                  : 0
              }
              suffix={<span style={styles.caption}>{t('userSessions.minutes')}</span>}
              valueStyle={styles.heading3}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title={
          <Space style={styles.flexStart}>
            <span style={styles.heading4}>{t('userSessions.title')}</span>
            <Tooltip title={t('common:actions.refresh')}>
              <Button
                data-testid="sessions-refresh-button"
                icon={<ReloadOutlined style={styles.icon.small} />}
                onClick={() => refetch()}
                loading={isLoading}
                style={{
                  ...styles.buttonSecondary,
                  ...styles.controlSurfaceSmall
                }}
                aria-label={t('common:actions.refresh')}
              />
            </Tooltip>
          </Space>
        }
        extra={
          <Input
            data-testid="sessions-search-input"
            placeholder={t('userSessions.searchPlaceholder')}
            prefix={<SearchOutlined style={styles.icon.small} />}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{ 
              width: 300,
              ...formStyles.formInput
            }}
            autoComplete="off"
          />
        }
        style={{
          ...styles.card,
          border: '1px solid var(--color-border-secondary)'
        }}
      >
        <div style={tableStyles.tableContainer}>
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
                <span style={styles.caption}>
                  {t('userSessions.totalCount', { count: total })}
                </span>
              ),
            }}
            scroll={{ x: 1500 }}
            onRow={(record) => ({
              'data-testid': `sessions-row-${record.requestId}`,
            } as any)}
          />
        </div>
      </Card>
    </div>
  )
}

export default UserSessionsTab
