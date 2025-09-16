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
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing } from '@/utils/styleConstants'

dayjs.extend(relativeTime)

const { Text } = Typography

const NotificationBell: React.FC = () => {
  const dispatch = useDispatch()
  const { t } = useTranslation('common')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const styles = useComponentStyles()
  
  const { notifications, unreadCount } = useSelector((state: RootState) => state.notifications)

  const getIcon = (type: NotificationType) => {
    switch (type) {
      case 'success':
        return <CheckCircleOutlined style={{ color: 'var(--color-success)' }} />
      case 'error':
        return <ExclamationCircleOutlined style={{ color: 'var(--color-error)' }} />
      case 'warning':
        return <WarningOutlined style={{ color: 'var(--color-warning)' }} />
      case 'info':
        return <InfoCircleOutlined style={{ color: 'var(--color-info)' }} />
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
    <div 
      className="notification-dropdown" 
      data-testid="notification-dropdown"
      style={{ 
        ...styles.modal,
        maxHeight: 500, 
      }}
    >
      <div className="notification-dropdown-header" style={{ 
        ...styles.flexBetween,
        padding: `${spacing('SM')}px ${spacing('MD')}px`, 
      }}>
        <Text strong style={styles.heading4}>
          {t('notifications.title', 'Notifications')}
        </Text>
        {notifications.length > 0 && (
          <Space>
            <Button 
              type="link" 
              size="small" 
              onClick={handleMarkAllAsRead}
              disabled={unreadCount === 0}
              data-testid="notification-mark-all-read"
            >
              {t('notifications.markAllRead', 'Mark all as read')}
            </Button>
            <Button 
              type="link" 
              size="small" 
              danger 
              onClick={handleClearAll}
              data-testid="notification-clear-all"
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
            style={{ padding: `${spacing('XXL')}px 0` }}
          />
        ) : (
          <List
            dataSource={notifications}
            renderItem={(notification, index) => (
              <List.Item
                key={notification.id}
                className={notification.read ? 'ant-list-item-read' : 'ant-list-item-unread'}
                style={{ 
                  padding: `${spacing('SM')}px ${spacing('MD')}px`,
                  cursor: 'pointer',
                  transition: DESIGN_TOKENS.TRANSITIONS.DEFAULT
                }}
                onClick={() => handleMarkAsRead(notification.id)}
                data-testid={`notification-item-${index}`}
              >
                <List.Item.Meta
                  avatar={getIcon(notification.type)}
                  title={
                    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                      <Space>
                        <Text strong={!notification.read}>{notification.title}</Text>
                        <Tag color={getTypeColor(notification.type)} style={{ marginLeft: spacing('XS') }}>
                          {notification.type.toUpperCase()}
                        </Tag>
                      </Space>
                      <Button
                        type="text"
                        size="small"
                        icon={<CloseOutlined />}
                        onClick={(e) => handleClear(notification.id, e)}
                        style={{ marginLeft: 'auto' }}
                        data-testid={`notification-close-${index}`}
                      />
                    </Space>
                  }
                  description={
                    <div>
                      <Text className="notification-message" style={{ 
                        ...styles.body,
                        display: 'block',
                        marginBottom: spacing('XS'),
                        wordBreak: 'break-word'
                      }}>
                        {notification.message}
                      </Text>
                      <Text type="secondary" style={styles.caption}>
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
      popupRender={() => dropdownContent}
    >
      <Badge count={unreadCount} size="small">
        <Button
          type="text"
          icon={<BellOutlined style={styles.icon.medium} />}
          style={styles.touchTarget}
          data-testid="notification-bell"
        />
      </Badge>
    </Dropdown>
  )
}

export default NotificationBell