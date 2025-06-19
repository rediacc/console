import React, { useState } from 'react'
import { Badge, Button, Drawer, List, Tag, Space, Typography, Progress, Empty, Tooltip } from 'antd'
import { 
  ClockCircleOutlined, 
  LoadingOutlined, 
  CheckCircleOutlined, 
  CloseCircleOutlined,
  DeleteOutlined,
  ReloadOutlined,
  ThunderboltOutlined
} from '@ant-design/icons'
import { useManagedQueueItem } from '@/hooks/useManagedQueueItem'
import { useTranslation } from 'react-i18next'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'

dayjs.extend(relativeTime)

const { Text, Title } = Typography

const QueueManagerStatus: React.FC = () => {
  const { t } = useTranslation(['queue', 'common'])
  const [drawerVisible, setDrawerVisible] = useState(false)
  const { localQueue, queueStats, retryQueueItem, removeFromQueue, clearCompleted, getQueuePosition } = useManagedQueueItem()

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'pending':
        return <ClockCircleOutlined style={{ color: '#faad14' }} />
      case 'submitting':
        return <LoadingOutlined style={{ color: '#1890ff' }} />
      case 'submitted':
        return <CheckCircleOutlined style={{ color: '#52c41a' }} />
      case 'failed':
        return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
      default:
        return null
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pending': return 'warning'
      case 'submitting': return 'processing'
      case 'submitted': return 'success'
      case 'failed': return 'error'
      default: return 'default'
    }
  }

  const getPriorityLabel = (priority?: number) => {
    switch (priority) {
      case 1: return 'Highest'
      case 2: return 'High'
      case 3: return 'Normal'
      case 4: return 'Low'
      case 5: return 'Lowest'
      default: return 'Normal'
    }
  }

  const getPriorityColor = (priority?: number) => {
    switch (priority) {
      case 1: return 'red'
      case 2: return 'orange'
      case 3: return 'gold'
      case 4: return 'blue'
      case 5: return 'green'
      default: return 'default'
    }
  }

  return (
    <>
      <Tooltip title={t('queue:queueManager.tooltip')}>
        <Badge count={queueStats.pending} offset={[-5, 5]}>
          <Button
            icon={<ThunderboltOutlined />}
            onClick={() => setDrawerVisible(true)}
            type={queueStats.pending > 0 ? 'primary' : 'default'}
          >
            {t('queue:queueManager.buttonLabel')}
          </Button>
        </Badge>
      </Tooltip>

      <Drawer
        title={
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Title level={4} style={{ margin: 0 }}>{t('queue:queueManager.title')}</Title>
            <Space>
              <Tag color="warning">{queueStats.pending} Pending</Tag>
              <Tag color="processing">{queueStats.submitting} Submitting</Tag>
              <Tag color="success">{queueStats.submitted} Submitted</Tag>
              {queueStats.failed > 0 && <Tag color="error">{queueStats.failed} Failed</Tag>}
            </Space>
          </div>
        }
        placement="right"
        width={600}
        open={drawerVisible}
        onClose={() => setDrawerVisible(false)}
        extra={
          <Space>
            <Button
              size="small"
              onClick={clearCompleted}
              disabled={queueStats.submitted === 0 && queueStats.failed === 0}
            >
              {t('queue:queueManager.clearCompleted')}
            </Button>
          </Space>
        }
      >
        {localQueue.length === 0 ? (
          <Empty
            description={t('queue:queueManager.emptyState')}
            style={{ marginTop: 50 }}
          />
        ) : (
          <>
            <div style={{ marginBottom: 16 }}>
              <Text type="secondary">
                {t('queue:queueManager.description')}
              </Text>
            </div>
            
            {queueStats.pending > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Progress
                  percent={Math.round(((queueStats.submitted + queueStats.failed) / localQueue.length) * 100)}
                  status={queueStats.failed > 0 ? 'exception' : 'active'}
                  format={percent => `${percent}% processed`}
                />
              </div>
            )}

            <List
              dataSource={localQueue}
              renderItem={(item) => {
                const position = getQueuePosition(item.id)
                return (
                  <List.Item
                    actions={[
                      item.status === 'failed' && (
                        <Button
                          size="small"
                          icon={<ReloadOutlined />}
                          onClick={() => retryQueueItem(item.id)}
                        >
                          Retry
                        </Button>
                      ),
                      (item.status === 'submitted' || item.status === 'failed') && (
                        <Button
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={() => removeFromQueue(item.id)}
                        >
                          Remove
                        </Button>
                      )
                    ].filter(Boolean)}
                  >
                    <List.Item.Meta
                      avatar={getStatusIcon(item.status)}
                      title={
                        <Space>
                          <Text strong>{item.data.machineName}</Text>
                          <Tag color={getPriorityColor(item.data.priority)}>
                            {getPriorityLabel(item.data.priority)}
                          </Tag>
                          <Tag color={getStatusColor(item.status)}>
                            {item.status}
                          </Tag>
                          {position > 0 && (
                            <Tag color="blue">Position: {position}</Tag>
                          )}
                        </Space>
                      }
                      description={
                        <Space direction="vertical" size="small">
                          <Text type="secondary">
                            Team: {item.data.teamName} | Bridge: {item.data.bridgeName}
                          </Text>
                          <Text type="secondary">
                            Added {dayjs(item.timestamp).fromNow()}
                          </Text>
                          {item.retryCount > 0 && (
                            <Text type="danger">
                              Retry attempts: {item.retryCount}/3
                            </Text>
                          )}
                        </Space>
                      }
                    />
                  </List.Item>
                )
              }}
            />
          </>
        )}
      </Drawer>
    </>
  )
}

export default QueueManagerStatus