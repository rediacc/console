import React, { useState } from 'react';
import { Badge, Dropdown, Empty, Grid, List, Space, Tag } from 'antd';
import dayjs from 'dayjs';
import 'dayjs/locale/es';
import relativeTime from 'dayjs/plugin/relativeTime';
import { useTranslation } from 'react-i18next';
import { useDispatch, useSelector } from 'react-redux';
import { RediaccText } from '@/components/ui';
import {
  clearAllNotifications,
  clearNotification,
  markAllAsRead,
  markAsRead,
  Notification,
  NotificationType,
} from '@/store/notifications/notificationSlice';
import { RootState } from '@/store/store';
import {
  BellOutlined,
  CheckCircleOutlined,
  CloseOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import {
  BellButton,
  EmptyWrapper,
  NotificationActionButton,
  NotificationCloseButton,
  NotificationDropdown,
  NotificationHeader,
  NotificationIconWrapper,
  NotificationItem,
  NotificationListWrapper,
  NotificationMessageWrapper,
  NotificationTag,
  NotificationText,
  NotificationTitleContent,
  NotificationTitleRow,
} from './styles';

dayjs.extend(relativeTime);

const { useBreakpoint } = Grid;

const NotificationBell: React.FC = () => {
  const dispatch = useDispatch();
  const { t, i18n } = useTranslation('common');
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const screens = useBreakpoint();
  const isMobile = !screens.md;

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
        <RediaccText variant="title">{t('notifications.title', 'Notifications')}</RediaccText>
        {notifications.length > 0 && (
          <Space>
            <NotificationActionButton
              onClick={handleMarkAllAsRead}
              disabled={unreadCount === 0}
              data-testid="notification-mark-all-read"
            >
              {t('notifications.markAllRead', 'Mark all as read')}
            </NotificationActionButton>
            <NotificationActionButton
              variant="danger"
              onClick={handleClearAll}
              data-testid="notification-clear-all"
            >
              {t('notifications.clearAll', 'Clear all')}
            </NotificationActionButton>
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
                      <NotificationMessageWrapper className="notification-message">
                        <RediaccText variant="description">{notification.message}</RediaccText>
                      </NotificationMessageWrapper>
                      <RediaccText variant="caption">
                        {dayjs(notification.timestamp).fromNow()}
                      </RediaccText>
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
        placement={isMobile ? 'bottom' : 'bottomRight'}
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
        />
      </Dropdown>
    </Badge>
  );
};

export default NotificationBell;
