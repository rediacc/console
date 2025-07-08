import React, { useState } from 'react'
import { Badge, Dropdown, Button, List, Empty, Typography, Space, Tag } from 'antd'
import { 
  BellOutlined, 
  CloseOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  WarningOutlined,
  CheckCircleOutlined
} from '@/utils/optimizedIcons'
import { useSelector, useDispatch } from 'react-redux'
import { RootState } from '@/store/store'
import { 
  markAsRead, 
  markAllAsRead, 
  clearNotification, 
  clearAllNotifications,
  NotificationType 
} from '@/store/notifications/notificationSlice'
import { useTranslation } from 'react-i18next'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'

dayjs.extend(relativeTime)

const { Text } = Typography

const NotificationBell: React.FC = () => {
  const dispatch = useDispatch()
  const { t } = useTranslation('common')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  
  const { notifications, unreadCount } = useSelector((state: RootState) => state.notifications)

  const getIcon = (type: NotificationType) => {
    switch (type) {
      case 'success':
        return <CheckCircleOutlined style={{ color: '#52c41a' }} />
      case 'error':
        return <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />
      case 'warning':
        return <WarningOutlined style={{ color: '#faad14' }} />
      case 'info':
        return <InfoCircleOutlined style={{ color: '#1890ff' }} />
    }
  }

  const getTypeColor = (type: NotificationType) => {
    switch (type) {
      case 'success': return 'success'
      case 'error': return 'error'
      case 'warning': return 'warning'
      case 'info': return 'processing'
    }
  }

  const handleMarkAsRead = (id: string) => {
    dispatch(markAsRead(id))
  }

  const handleClear = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    dispatch(clearNotification(id))
  }

  const handleMarkAllAsRead = () => {
    dispatch(markAllAsRead())
  }

  const handleClearAll = () => {
    dispatch(clearAllNotifications())
  }

  const dropdownContent = (
    <div className="notification-dropdown" style={{ 
      width: 400, 
      maxHeight: 500, 
      borderRadius: 8,
    }}>
      <div className="notification-dropdown-header" style={{ 
        padding: '12px 16px', 
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <Text strong style={{ fontSize: 16 }}>
          {t('notifications.title', 'Notifications')}
        </Text>
        {notifications.length > 0 && (
          <Space>
            <Button 
              type="link" 
              size="small" 
              onClick={handleMarkAllAsRead}
              disabled={unreadCount === 0}
            >
              {t('notifications.markAllRead', 'Mark all as read')}
            </Button>
            <Button 
              type="link" 
              size="small" 
              danger 
              onClick={handleClearAll}
            >
              {t('notifications.clearAll', 'Clear all')}
            </Button>
          </Space>
        )}
      </div>
      
      <div style={{ maxHeight: 400, overflowY: 'auto' }}>
        {notifications.length === 0 ? (
          <Empty 
            description={t('notifications.empty', 'No notifications')}
            style={{ padding: '40px 0' }}
          />
        ) : (
          <List
            dataSource={notifications}
            renderItem={(notification) => (
              <List.Item
                key={notification.id}
                className={notification.read ? 'ant-list-item-read' : 'ant-list-item-unread'}
                style={{ 
                  padding: '12px 16px',
                  cursor: 'pointer',
                  transition: 'background-color 0.3s'
                }}
                onClick={() => handleMarkAsRead(notification.id)}
              >
                <List.Item.Meta
                  avatar={getIcon(notification.type)}
                  title={
                    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                      <Space>
                        <Text strong={!notification.read}>{notification.title}</Text>
                        <Tag color={getTypeColor(notification.type)} style={{ marginLeft: 8 }}>
                          {notification.type.toUpperCase()}
                        </Tag>
                      </Space>
                      <Button
                        type="text"
                        size="small"
                        icon={<CloseOutlined />}
                        onClick={(e) => handleClear(notification.id, e)}
                        style={{ marginLeft: 'auto' }}
                      />
                    </Space>
                  }
                  description={
                    <div>
                      <Text className="notification-message" style={{ 
                        fontSize: 13, 
                        display: 'block',
                        marginBottom: 4,
                        wordBreak: 'break-word'
                      }}>
                        {notification.message}
                      </Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {dayjs(notification.timestamp).fromNow()}
                      </Text>
                    </div>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </div>
    </div>
  )

  return (
    <Dropdown
      trigger={['click']}
      placement="bottomRight"
      open={dropdownOpen}
      onOpenChange={setDropdownOpen}
      menu={{ items: [] }}
      dropdownRender={() => dropdownContent}
    >
      <Badge count={unreadCount} size="small">
        <Button
          type="text"
          icon={<BellOutlined style={{ fontSize: 20 }} />}
          style={{ 
            height: 40,
            width: 40,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}
        />
      </Badge>
    </Dropdown>
  )
}

export default NotificationBell