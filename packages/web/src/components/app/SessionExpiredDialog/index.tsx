import React, { useState, useEffect, useRef } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { InlineStack } from '@/components/common/styled';
import { IconWrapper, RediaccText, RediaccStack } from '@/components/ui';
import { hideSessionExpiredDialog, setStayLoggedOutMode } from '@/store/auth/authSlice';
import { RootState } from '@/store/store';
import { ModalSize } from '@/types/modal';
import { ClockCircleOutlined, LogoutOutlined } from '@/utils/optimizedIcons';
import { StyledModal, CountdownCard, FooterButton } from './styles';

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
    <StyledModal
      title={
        <InlineStack>
          <IconWrapper $tone="danger">
            <ClockCircleOutlined />
          </IconWrapper>
          <RediaccText
            size="xl"
            weight="semibold"
            style={{ margin: 0, color: 'var(--color-error)' }}
          >
            Session Expired
          </RediaccText>
        </InlineStack>
      }
      open={isVisible}
      onCancel={handleStayLoggedOut}
      closable
      maskClosable={false}
      centered
      className={ModalSize.Small}
      footer={[
        <FooterButton key="stay" onClick={handleStayLoggedOut}>
          Stay Logged Out
        </FooterButton>,
        <FooterButton
          key="login"
          variant="primary"
          onClick={handleContinueToLogin}
          icon={<LogoutOutlined />}
        >
          Continue to Login
        </FooterButton>,
      ]}
    >
      <RediaccStack variant="spaced-column" fullWidth>
        <span>
          Your session has expired for security reasons. You have been automatically logged out.
        </span>

        <RediaccText color="secondary">
          You can stay on this page or continue to the login screen to sign in again.
        </RediaccText>

        <CountdownCard>
          <RediaccText weight="semibold" style={{ color: 'var(--color-error)' }}>
            Automatically redirecting in {formatTime(countdown)}
          </RediaccText>
        </CountdownCard>
      </RediaccStack>
    </StyledModal>
  );
};
