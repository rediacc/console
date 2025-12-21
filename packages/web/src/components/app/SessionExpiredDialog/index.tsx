import React, { useEffect, useRef, useState } from 'react';
import { Button, Card, Flex, Modal, Typography } from 'antd';
import { useDispatch, useSelector } from 'react-redux';
import { hideSessionExpiredDialog, setStayLoggedOutMode } from '@/store/auth/authSlice';
import { RootState } from '@/store/store';
import { ModalSize } from '@/types/modal';
import { ClockCircleOutlined, LogoutOutlined } from '@/utils/optimizedIcons';

const COUNTDOWN_DURATION = 60; // 60 seconds

export const SessionExpiredDialog: React.FC = () => {
  const dispatch = useDispatch();
  const isVisible = useSelector((state: RootState) => state.auth.showSessionExpiredDialog);

  const [countdown, setCountdown] = useState(COUNTDOWN_DURATION);
  const isVisibleRef = useRef(isVisible);

  // Reset countdown when dialog opens (synchronously during render)
  if (isVisible && !isVisibleRef.current) {
    // Dialog just opened - reset countdown synchronously
    if (countdown !== COUNTDOWN_DURATION) {
      setCountdown(COUNTDOWN_DURATION);
    }
  }
  isVisibleRef.current = isVisible;

  // Run timer when dialog is visible
  useEffect(() => {
    if (!isVisible) {
      return;
    }

    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          handleContinueToLogin();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isVisible]);

  const handleStayLoggedOut = () => {
    dispatch(setStayLoggedOutMode(true));
    dispatch(hideSessionExpiredDialog());
  };

  const handleContinueToLogin = () => {
    dispatch(hideSessionExpiredDialog());
    const basePath = import.meta.env.BASE_URL || '/';
    const loginPath = `${basePath}login`.replace('//', '/');
    window.location.href = loginPath;
  };

  const formatTime = (seconds: number) => {
    if (seconds <= 0) return '0 seconds';
    return seconds === 1 ? '1 second' : `${seconds} seconds`;
  };

  return (
    <Modal
      title={
        <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
          <ClockCircleOutlined />
          <Typography.Title level={4} style={{ margin: 0 }}>
            Session Expired
          </Typography.Title>
        </Flex>
      }
      open={isVisible}
      onCancel={handleStayLoggedOut}
      closable
      maskClosable={false}
      centered
      className={ModalSize.Small}
      data-testid="session-expired-modal"
      footer={[
        <Button
          key="login"
          type="primary"
          onClick={handleContinueToLogin}
          icon={<LogoutOutlined />}
          data-testid="session-expired-login-button"
        >
          Continue to Login
        </Button>,
        <Button key="stay" onClick={handleStayLoggedOut} data-testid="session-expired-stay-button">
          Stay Logged Out
        </Button>,
      ]}
    >
      <Flex vertical gap={24} style={{ width: '100%' }}>
        <Typography.Text>
          Your session has expired for security reasons. You have been automatically logged out.
        </Typography.Text>

        <Typography.Text>
          You can stay on this page or continue to the login screen to sign in again.
        </Typography.Text>

        <Card>
          <Typography.Text strong type="danger">
            Automatically redirecting in {formatTime(countdown)}
          </Typography.Text>
        </Card>
      </Flex>
    </Modal>
  );
};
