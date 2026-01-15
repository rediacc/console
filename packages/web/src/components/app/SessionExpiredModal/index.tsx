import { Button, Card, Flex, Typography } from 'antd';
import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useDispatch, useSelector } from 'react-redux';
import { SizedModal } from '@/components/common/SizedModal';
import { hideSessionExpiredModal, setStayLoggedOutMode } from '@/store/auth/authSlice';
import { RootState } from '@/store/store';
import { ModalSize } from '@/types/modal';
import { ClockCircleOutlined, LogoutOutlined } from '@/utils/optimizedIcons';

const COUNTDOWN_DURATION = 60; // 60 seconds

export const SessionExpiredModal: React.FC = () => {
  const { t } = useTranslation('auth');
  const dispatch = useDispatch();
  const isVisible = useSelector((state: RootState) => state.auth.showSessionExpiredModal);

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
    dispatch(hideSessionExpiredModal());
  };

  const handleContinueToLogin = () => {
    dispatch(hideSessionExpiredModal());
    const basePath = import.meta.env.BASE_URL || '/';
    const loginPath = `${basePath}login`.replace('//', '/');
    window.location.href = loginPath;
  };

  const formatTime = (seconds: number) => {
    if (seconds <= 0) return t('sessionExpired.zeroSeconds');
    return t('sessionExpired.seconds', { count: seconds });
  };

  return (
    <SizedModal
      title={
        <Flex align="center" wrap className="inline-flex">
          <ClockCircleOutlined />
          <Typography.Title level={4}>{t('sessionExpired.title')}</Typography.Title>
        </Flex>
      }
      open={isVisible}
      onCancel={handleStayLoggedOut}
      closable
      maskClosable={false}
      centered
      size={ModalSize.Small}
      data-testid="session-expired-modal"
      footer={[
        <Button
          key="login"
          type="primary"
          onClick={handleContinueToLogin}
          icon={<LogoutOutlined />}
          data-testid="session-expired-login-button"
        >
          {t('sessionExpired.continueToLogin')}
        </Button>,
        <Button key="stay" onClick={handleStayLoggedOut} data-testid="session-expired-stay-button">
          {t('sessionExpired.stayLoggedOut')}
        </Button>,
      ]}
    >
      <Flex vertical className="w-full">
        <Typography.Text>{t('sessionExpired.message')}</Typography.Text>

        <Typography.Text>{t('sessionExpired.subMessage')}</Typography.Text>

        <Card>
          <Typography.Text strong type="danger">
            {t('sessionExpired.redirectingIn', { time: formatTime(countdown) })}
          </Typography.Text>
        </Card>
      </Flex>
    </SizedModal>
  );
};
