import React from 'react'
import { useSelector, useDispatch } from 'react-redux'
import { Badge, Dropdown, List, Typography, Button, Empty, Tag, Space } from 'antd'
import {
  BellOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  WarningOutlined,
  InfoCircleOutlined,
  DeleteOutlined,
  CheckOutlined,
} from '@ant-design/icons'
import { RootState } from '@/store/store'
import { markMessageAsRead, markAllMessagesAsRead, clearMessages } from '@/store/ui/uiSlice'
import type { Message } from '@/store/ui/uiSlice'

const { Text } = Typography

const MessageHistory: React.FC = () => {
  const dispatch = useDispatch()
  const messages = useSelector((state: RootState) => state.ui.messages)
  const unreadCount = useSelector((state: RootState) => state.ui.unreadMessageCount)

  const getIcon = (type: Message['type']) => {
    switch (type) {
      case 'success':
        return <CheckCircleOutlined style={{ color: '#22c55e' }} />
      case 'error':
        return <CloseCircleOutlined style={{ color: '#ef4444' }} />
      case 'warning':
        return <WarningOutlined style={{ color: '#f59e0b' }} />
      case 'info':
        return <InfoCircleOutlined style={{ color: '#3b82f6' }} />
    }
  }

  const getTypeColor = (type: Message['type']) => {
    switch (type) {
      case 'success':
        return 'success'
      case 'error':
        return 'error'
      case 'warning':
        return 'warning'
      case 'info':
        return 'processing'
    }
  }

  const formatTime = (timestamp: number) => {
    const now = Date.now()
    const diff = now - timestamp
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)

    if (minutes < 1) return 'Just now'
    if (minutes < 60) return `${minutes}m ago`
    if (hours < 24) return `${hours}h ago`
    return `${days}d ago`
  }

  const handleMessageClick = (messageId: string) => {
    dispatch(markMessageAsRead(messageId))
  }

  const menu = {
    items: [
      {
        key: 'header',
        type: 'group',
        label: (
          <div style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0', marginBottom: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text strong style={{ fontSize: 16 }}>Messages</Text>
              <Space>
                {messages.length > 0 && (
                  <>
                    <Button
                      type="text"
                      size="small"
                      icon={<CheckOutlined />}
                      onClick={() => dispatch(markAllMessagesAsRead())}
                    >
                      Mark all read
                    </Button>
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => dispatch(clearMessages())}
                    >
                      Clear all
                    </Button>
                  </>
                )}
              </Space>
            </div>
          </div>
        ),
      },
      {
        key: 'messages',
        type: 'group',
        label: (
          <div style={{ maxHeight: 400, overflowY: 'auto', minWidth: 380 }}>
            {messages.length === 0 ? (
              <Empty
                description="No messages"
                style={{ padding: '32px 0' }}
              />
            ) : (
              <List
                dataSource={messages}
                renderItem={(message) => (
                  <List.Item
                    key={message.id}
                    onClick={() => handleMessageClick(message.id)}
                    style={{
                      padding: '12px',
                      backgroundColor: message.read ? 'transparent' : '#f5f5f5',
                      cursor: 'pointer',
                      borderBottom: '1px solid #f0f0f0',
                    }}
                  >
                    <Space align="start" style={{ width: '100%' }}>
                      {getIcon(message.type)}
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                          <Tag color={getTypeColor(message.type)} style={{ margin: 0 }}>
                            {message.type.toUpperCase()}
                          </Tag>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {formatTime(message.timestamp)}
                          </Text>
                        </div>
                        <Text style={{ fontSize: 13 }}>{message.content}</Text>
                      </div>
                    </Space>
                  </List.Item>
                )}
              />
            )}
          </div>
        ),
      },
    ],
  }

  return (
    <Dropdown
      menu={menu}
      placement="bottomRight"
      arrow
      trigger={['click']}
    >
      <Badge count={unreadCount} offset={[-2, 2]} style={{ cursor: 'pointer' }}>
        <BellOutlined 
          style={{ 
            fontSize: 20, 
            cursor: 'pointer',
            color: unreadCount > 0 ? '#556b2f' : undefined
          }} 
        />
      </Badge>
    </Dropdown>
  )
}

export default MessageHistory