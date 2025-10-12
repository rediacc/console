import React, { useState, useEffect } from 'react'
import { Modal, Button, Typography, Space } from 'antd'
import { useDispatch, useSelector } from 'react-redux'
import { ClockCircleOutlined, LogoutOutlined } from '@/utils/optimizedIcons'
import { RootState } from '@/store/store'
import { hideSessionExpiredDialog, setStayLoggedOutMode } from '@/store/auth/authSlice'

const { Text, Title } = Typography

const COUNTDOWN_DURATION = 60 // 60 seconds

export const SessionExpiredDialog: React.FC = () => {
  const dispatch = useDispatch()
  const isVisible = useSelector((state: RootState) => state.auth.showSessionExpiredDialog)

  const [countdown, setCountdown] = useState(COUNTDOWN_DURATION)

  useEffect(() => {
    if (!isVisible) {
      return
    }

    // Reset countdown when dialog opens - use updater function to avoid synchronous setState warning
    setCountdown(() => COUNTDOWN_DURATION)

    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          handleContinueToLogin()
          return 0
        }
        return prev - 1
      })
    }, 1000)

    return () => clearInterval(timer)
  }, [isVisible])

  const handleStayLoggedOut = () => {
    dispatch(setStayLoggedOutMode(true))
    dispatch(hideSessionExpiredDialog())
  }

  const handleContinueToLogin = () => {
    dispatch(hideSessionExpiredDialog())
    const basePath = import.meta.env.BASE_URL || '/'
    const loginPath = `${basePath}login`.replace('//', '/')
    window.location.href = loginPath
  }

  const formatTime = (seconds: number) => {
    if (seconds <= 0) return '0 seconds'
    return seconds === 1 ? '1 second' : `${seconds} seconds`
  }

  return (
    <Modal
      title={
        <Space>
          <ClockCircleOutlined style={{ color: '#ff7875' }} />
          <Title level={4} style={{ margin: 0, color: '#ff7875' }}>
            Session Expired
          </Title>
        </Space>
      }
      open={isVisible}
      onCancel={handleStayLoggedOut}
      closable={true}
      maskClosable={false}
      width={460}
      centered
      footer={[
        <Button
          key="stay"
          onClick={handleStayLoggedOut}
          size="large"
        >
          Stay Logged Out
        </Button>,
        <Button
          key="login"
          type="primary"
          onClick={handleContinueToLogin}
          icon={<LogoutOutlined />}
          size="large"
        >
          Continue to Login
        </Button>,
      ]}
    >
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Text>
          Your session has expired for security reasons. You have been automatically logged out.
        </Text>

        <Text type="secondary">
          You can stay on this page or continue to the login screen to sign in again.
        </Text>

        <div style={{
          background: '#f6f6f6',
          padding: '12px 16px',
          borderRadius: '6px',
          textAlign: 'center'
        }}>
          <Text strong style={{ color: '#ff7875' }}>
            Automatically redirecting in {formatTime(countdown)}
          </Text>
        </div>
      </Space>
    </Modal>
  )
}