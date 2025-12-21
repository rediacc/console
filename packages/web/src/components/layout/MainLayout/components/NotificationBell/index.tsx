import React, { useState } from 'react';
import { Badge, Button, Dropdown, Empty, Flex, Grid, List, Space, Tag, Typography } from 'antd';
import dayjs from 'dayjs';
import 'dayjs/locale/es';
import relativeTime from 'dayjs/plugin/relativeTime';
import { useTranslation } from 'react-i18next';
import { useDispatch, useSelector } from 'react-redux';
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
      <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
        <IconComponent />
      </div>
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
    <div style={{ maxHeight: 400, minWidth: 320 }} className="notification-dropdown" data-testid="notification-dropdown">
      <Flex align="center" justify="space-between" style={{ padding: '16px 24px', fontWeight: 600 }}>
        <Typography.Text strong>{t('notifications.title', 'Notifications')}</Typography.Text>
        {notifications.length > 0 && (
          <Space>
            <Button
              style={{ padding: '0 12px', fontSize: 12 }}
              onClick={handleMarkAllAsRead}
              disabled={unreadCount === 0}
              data-testid="notification-mark-all-read"
            >
              {t('notifications.markAllRead', 'Mark all as read')}
            </Button>
            <Button
              type="text"
              danger
              style={{ padding: '0 12px', fontSize: 12 }}
              onClick={handleClearAll}
              data-testid="notification-clear-all"
            >
              {t('notifications.clearAll', 'Clear all')}
            </Button>
          </Space>
        )}
      </Flex>

      <div style={{ maxHeight: 320, overflowY: 'auto' }}>
        {notifications.length === 0 ? (
          <div style={{ padding: '40px 0' }}>
            <Empty description={t('notifications.empty', 'No notifications')} />
          </div>
        ) : (
          <List
            dataSource={notifications}
            renderItem={(notification: Notification, index: number) => (
              <div
                key={notification.id}
                style={{ padding: '16px 24px', cursor: 'pointer' }}
                onClick={() => handleMarkAsRead(notification.id)}
                data-testid={`notification-item-${index}`}
              >
                <List.Item.Meta
                  title={
                    <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
                      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flex: 1 }}>
                        <Typography.Text style={{ fontWeight: notification.read ? 400 : 600 }}>
                          {notification.title}
                        </Typography.Text>
                        <span>
                          <Tag color={getTypeColor(notification.type)}>
                            {t(`notifications.types.${notification.type}`).toUpperCase()}
                          </Tag>
                        </span>
                        {getIcon(notification.type)}
                      </div>
                      <Button
                        type="text"
                        icon={<CloseOutlined />}
                        onClick={(e) => handleClear(notification.id, e)}
                        data-testid={`notification-close-${index}`}
                        aria-label="Close notification"
                        style={{ flexShrink: 0 }}
                      />
                    </div>
                  }
                  description={
                    <div>
                      <div style={{ display: 'block', wordBreak: 'break-word' }} className="notification-message">
                        <Typography.Text type="secondary">{notification.message}</Typography.Text>
                      </div>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {dayjs(notification.timestamp).fromNow()}
                      </Typography.Text>
                    </div>
                  }
                />
              </div>
            )}
          />
        )}
      </div>
    </div>
  );

  return (
    <Badge count={unreadCount} offset={[-4, 4]}>
      <Dropdown
        trigger={['click']}
        placement={isMobile ? 'bottomCenter' : 'bottomRight'}
        open={dropdownOpen}
        onOpenChange={setDropdownOpen}
        menu={{ items: [] }}
        dropdownRender={() => dropdownContent}
      >
        <Button
          type="text"
          icon={<BellOutlined />}
          aria-label="Notifications"
          data-testid="notification-bell"
          style={{ width: 40, height: 40 }}
        />
      </Dropdown>
    </Badge>
  );
};

export default NotificationBell;
