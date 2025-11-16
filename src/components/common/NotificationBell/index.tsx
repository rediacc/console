import React, { useState } from 'react'
import { Badge, Dropdown, Button, List, Empty, Space, Tag } from 'antd'
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
  NotificationType,
  Notification
} from '@/store/notifications/notificationSlice'
import { useTranslation } from 'react-i18next'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/es'
import {
  NotificationDropdown,
  NotificationHeader,
  NotificationTitle,
  NotificationListWrapper,
  NotificationItem,
  NotificationIconWrapper,
  NotificationTitleRow,
  NotificationTitleContent,
  NotificationText,
  NotificationTag,
  NotificationCloseButton,
  NotificationMessage,
  NotificationTimestamp,
  EmptyWrapper,
  BellButton
} from './styles'

dayjs.extend(relativeTime)

const NotificationBell: React.FC = () => {
  const dispatch = useDispatch()
  const { t, i18n } = useTranslation('common')
  const [dropdownOpen, setDropdownOpen] = useState(false)

  const { notifications, unreadCount } = useSelector((state: RootState) => state.notifications)

  // Update dayjs locale when language changes
  React.useEffect(() => {
    const dayjsLocaleMap: Record<string, string> = {
      en: 'en',
      es: 'es'
    }
    dayjs.locale(dayjsLocaleMap[i18n.language] || 'en')
  }, [i18n.language])

  const getIcon = (type: NotificationType) => {
    const IconComponent = (() => {
      switch (type) {
        case 'success': return CheckCircleOutlined
        case 'error': return ExclamationCircleOutlined
        case 'warning': return WarningOutlined
        case 'info': return InfoCircleOutlined
      }
    })()
    
    return (
      <NotificationIconWrapper $type={type}>
        <IconComponent />
      </NotificationIconWrapper>
    )
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
    <NotificationDropdown 
      className="notification-dropdown" 
      data-testid="notification-dropdown"
    >
      <NotificationHeader>
        <NotificationTitle strong>
          {t('notifications.title', 'Notifications')}
        </NotificationTitle>
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
      </NotificationHeader>
      
      <NotificationListWrapper>
        {notifications.length === 0 ? (
          <EmptyWrapper>
            <Empty description={t('notifications.empty', 'No notifications')} />
          </EmptyWrapper>
        ) : (
          <List
            dataSource={notifications}
            renderItem={(notification: Notification, index: number) => (
              <NotificationItem
                key={notification.id}
                $isRead={notification.read}
                onClick={() => handleMarkAsRead(notification.id)}
                data-testid={`notification-item-${index}`}
              >
                <List.Item.Meta
                  title={
                    <NotificationTitleRow>
                      <NotificationTitleContent>
                        <NotificationText $isRead={notification.read}>
                          {notification.title}
                        </NotificationText>
                        <NotificationTag>
                          <Tag color={getTypeColor(notification.type)}>
                            {t(`notifications.types.${notification.type}`).toUpperCase()}
                          </Tag>
                        </NotificationTag>
                        {getIcon(notification.type)}
                      </NotificationTitleContent>
                      <NotificationCloseButton
                        type="text"
                        size="small"
                        icon={<CloseOutlined />}
                        onClick={(e) => handleClear(notification.id, e)}
                        data-testid={`notification-close-${index}`}
                      />
                    </NotificationTitleRow>
                  }
                  description={
                    <div>
                      <NotificationMessage className="notification-message">
                        {notification.message}
                      </NotificationMessage>
                      <NotificationTimestamp type="secondary">
                        {dayjs(notification.timestamp).fromNow()}
                      </NotificationTimestamp>
                    </div>
                  }
                />
              </NotificationItem>
            )}
          />
        )}
      </NotificationListWrapper>
    </NotificationDropdown>
  )

  return (
    <Badge count={unreadCount} offset={[-4, 4]}>
      <Dropdown
        trigger={['click']}
        placement="bottomRight"
        open={dropdownOpen}
        onOpenChange={setDropdownOpen}
        menu={{ items: [] }}
        popupRender={() => dropdownContent}
      >
        <BellButton
          type='default'
          shape='circle'
          size='large'
          icon={<BellOutlined />}
          data-testid="notification-bell"
        />
      </Dropdown>
    </Badge>
  )
}

export default NotificationBell