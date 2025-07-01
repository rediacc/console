import React, { useState } from 'react'
import { Table, Button, Card, Statistic, Row, Col, Tag, Input, Space, Popconfirm, message } from 'antd'
import { SearchOutlined, CloseCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { useUserRequests, useDeleteUserRequest, type UserRequest } from '@/api/queries/users'
import { useSelector } from 'react-redux'
import { selectUser } from '@/store/auth/authSelectors'
import { RootState } from '@/store/store'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'

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
      // Failed to terminate session
    }
  }

  const filteredSessions = sessions.filter((session: UserRequest) =>
    session.userEmail.toLowerCase().includes(searchTerm.toLowerCase()) ||
    session.ipAddress.toLowerCase().includes(searchTerm.toLowerCase()) ||
    session.sessionName.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const activeSessions = sessions.filter((session: UserRequest) => session.isActive)

  const columns: ColumnsType<UserRequest> = [
    {
      title: t('userSessions.columns.user'),
      dataIndex: 'userEmail',
      key: 'userEmail',
      width: 200,
      render: (email: string) => (
        <Space>
          <span>{email}</span>
          {email === user?.email && <Tag color="blue">{t('userSessions.currentSession')}</Tag>}
        </Space>
      ),
    },
    {
      title: t('userSessions.columns.sessionName'),
      dataIndex: 'sessionName',
      key: 'sessionName',
      width: 150,
    },
    {
      title: t('userSessions.columns.ipAddress'),
      dataIndex: 'ipAddress',
      key: 'ipAddress',
      width: 120,
    },
    {
      title: t('userSessions.columns.userAgent'),
      dataIndex: 'userAgent',
      key: 'userAgent',
      width: 300,
      ellipsis: true,
    },
    {
      title: t('userSessions.columns.status'),
      dataIndex: 'isActive',
      key: 'isActive',
      width: 100,
      render: (isActive: boolean) => (
        <Tag color={isActive ? 'green' : 'red'}>
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
      sorter: (a, b) => dayjs(a.createdAt).unix() - dayjs(b.createdAt).unix(),
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
          <Button
            type="link"
            danger
            icon={<CloseCircleOutlined />}
            disabled={!record.isActive}
            loading={deleteUserRequestMutation.isPending}
          >
            {t('userSessions.terminate')}
          </Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div className="user-sessions-tab">
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title={t('userSessions.totalSessions')}
              value={sessions.length}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title={t('userSessions.activeSessions')}
              value={activeSessions.length}
              valueStyle={{ color: '#3f8600' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title={t('userSessions.uniqueUsers')}
              value={new Set(sessions.map((s: UserRequest) => s.userEmail)).size}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title={t('userSessions.averageDuration')}
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
              suffix={t('userSessions.minutes')}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title={
          <Space>
            <span>{t('userSessions.title')}</span>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => refetch()}
              loading={isLoading}
            >
              {t('common:actions.refresh')}
            </Button>
          </Space>
        }
        extra={
          <Input
            placeholder={t('userSessions.searchPlaceholder')}
            prefix={<SearchOutlined />}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{ width: 300 }}
          />
        }
      >
        <Table
          columns={columns}
          dataSource={filteredSessions}
          rowKey="requestId"
          loading={isLoading}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => t('userSessions.totalCount', { count: total }),
          }}
          scroll={{ x: 1500 }}
        />
      </Card>
    </div>
  )
}

export default UserSessionsTab