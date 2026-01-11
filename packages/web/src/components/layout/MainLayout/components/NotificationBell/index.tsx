import React, { useState } from 'react';
import {
  Badge,
  Button,
  Card,
  Dropdown,
  Empty,
  Flex,
  Grid,
  List,
  Space,
  Tag,
  Typography,
} from 'antd';
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
      <Flex align="center" justify="center" className="inline-flex">
        <IconComponent />
      </Flex>
    );
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
    <Card data-testid="notification-dropdown">
      <Flex vertical className="notification-dropdown max-h-scroll-md min-w-dropdown">
        <Flex align="center" justify="space-between">
          <Typography.Text strong>{t('notifications.title', 'Notifications')}</Typography.Text>
          {notifications.length > 0 && (
            <Space>
              <Button
                onClick={handleMarkAllAsRead}
                disabled={unreadCount === 0}
                data-testid="notification-mark-all-read"
              >
                {t('notifications.markAllRead', 'Mark all as read')}
              </Button>
              <Button
                type="text"
                danger
                onClick={handleClearAll}
                data-testid="notification-clear-all"
              >
                {t('notifications.clearAll', 'Clear all')}
              </Button>
            </Space>
          )}
        </Flex>

        <Flex vertical className="max-h-scroll-sm">
          {notifications.length === 0 ? (
            <Flex
              // eslint-disable-next-line no-restricted-syntax
              style={{ padding: '40px 0' }}
            >
              <Empty description={t('notifications.empty', 'No notifications')} />
            </Flex>
          ) : (
            <List
              dataSource={notifications}
              renderItem={(notification: Notification, index: number) => (
                <Flex
                  key={notification.id}
                  className="cursor-pointer"
                  onClick={() => handleMarkAsRead(notification.id)}
                  data-testid={`notification-item-${index}`}
                >
                  <List.Item.Meta
                    title={
                      <Flex justify="space-between" className="w-full">
                        <Flex align="center" className="inline-flex flex-1">
                          <Typography.Text>{notification.title}</Typography.Text>
                          <Typography.Text>
                            <Tag>{t(`notifications.types.${notification.type}`).toUpperCase()}</Tag>
                          </Typography.Text>
                          {getIcon(notification.type)}
                        </Flex>
                        <Button
                          type="text"
                          icon={<CloseOutlined />}
                          onClick={(e) => handleClear(notification.id, e)}
                          data-testid={`notification-close-${index}`}
                          aria-label={t('common:aria.closeNotification')}
                          className="flex-shrink-0"
                        />
                      </Flex>
                    }
                    description={
                      <Flex vertical>
                        <Flex className="notification-message">
                          <Typography.Text type="secondary">{notification.message}</Typography.Text>
                        </Flex>
                        <Typography.Text type="secondary">
                          {dayjs(notification.timestamp).fromNow()}
                        </Typography.Text>
                      </Flex>
                    }
                  />
                </Flex>
              )}
            />
          )}
        </Flex>
      </Flex>
    </Card>
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
        <Button
          type="text"
          icon={<BellOutlined />}
          aria-label={t('common:aria.notifications')}
          data-testid="notification-bell"
        />
      </Dropdown>
    </Badge>
  );
};

export default NotificationBell;
