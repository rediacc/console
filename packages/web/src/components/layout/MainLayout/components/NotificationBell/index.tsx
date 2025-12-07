import React, { useState } from 'react';
import { Badge, Dropdown, List, Empty, Space, Tag } from 'antd';
import { RootState } from '@/store/store';
import {
  markAsRead,
  markAllAsRead,
  clearNotification,
  clearAllNotifications,
  NotificationType,
  Notification,
} from '@/store/notifications/notificationSlice';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { useTranslation } from 'react-i18next';
import { useSelector, useDispatch } from 'react-redux';
import 'dayjs/locale/es';
import { RediaccButton } from '@/components/ui';
import {
  BellOutlined,
  CloseOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  WarningOutlined,
  CheckCircleOutlined,
} from '@/utils/optimizedIcons';
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
  BellButton,
} from './styles';

dayjs.extend(relativeTime);

const NotificationBell: React.FC = () => {
  const dispatch = useDispatch();
  const { t, i18n } = useTranslation('common');
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const { notifications, unreadCount } = useSelector((state: RootState) => state.notifications);

  // Update dayjs locale when language changes
  React.useEffect(() => {
    const dayjsLocaleMap: Record<string, string> = {
      en: 'en',
      es: 'es',
    };
    dayjs.locale(dayjsLocaleMap[i18n.language] || 'en');
  }, [i18n.language]);

  const getIcon = (type: NotificationType) => {
    const IconComponent = (() => {
      switch (type) {
        case 'success':
          return CheckCircleOutlined;
        case 'error':
          return ExclamationCircleOutlined;
        case 'warning':
          return WarningOutlined;
        case 'info':
          return InfoCircleOutlined;
      }
    })();

    return (
      <NotificationIconWrapper $type={type}>
        <IconComponent />
      </NotificationIconWrapper>
    );
  };

  const getTypeColor = (type: NotificationType) => {
    switch (type) {
      case 'success':
        return 'success';
      case 'error':
        return 'error';
      case 'warning':
        return 'warning';
      case 'info':
        return 'processing';
    }
  };

  const handleMarkAsRead = (id: string) => {
    dispatch(markAsRead(id));
  };

  const handleClear = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    dispatch(clearNotification(id));
  };

  const handleMarkAllAsRead = () => {
    dispatch(markAllAsRead());
  };

  const handleClearAll = () => {
    dispatch(clearAllNotifications());
  };

  const dropdownContent = (
    <NotificationDropdown className="notification-dropdown" data-testid="notification-dropdown">
      <NotificationHeader>
        <NotificationTitle>{t('notifications.title', 'Notifications')}</NotificationTitle>
        {notifications.length > 0 && (
          <Space>
            <RediaccButton
              size="sm"
              onClick={handleMarkAllAsRead}
              disabled={unreadCount === 0}
              data-testid="notification-mark-all-read"
              style={{ padding: '0 8px', fontSize: '13px' }}
            >
              {t('notifications.markAllRead', 'Mark all as read')}
            </RediaccButton>
            <RediaccButton
              size="sm"
              variant="danger"
              onClick={handleClearAll}
              data-testid="notification-clear-all"
              style={{ padding: '0 8px', fontSize: '13px' }}
            >
              {t('notifications.clearAll', 'Clear all')}
            </RediaccButton>
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
                        size="sm"
                        iconOnly
                        icon={<CloseOutlined />}
                        onClick={(e) => handleClear(notification.id, e)}
                        data-testid={`notification-close-${index}`}
                        aria-label="Close notification"
                      />
                    </NotificationTitleRow>
                  }
                  description={
                    <div>
                      <NotificationMessage className="notification-message">
                        {notification.message}
                      </NotificationMessage>
                      <NotificationTimestamp>
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
  );

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
          iconOnly
          icon={<BellOutlined />}
          aria-label="Notifications"
          data-testid="notification-bell"
          style={{ borderRadius: '50%', width: '40px', height: '40px' }}
        />
      </Dropdown>
    </Badge>
  );
};

export default NotificationBell;
