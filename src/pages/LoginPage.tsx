import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDispatch } from 'react-redux'
import { Card, Form, Input, Button, Typography, Space, Alert } from 'antd'
import { UserOutlined, LockOutlined, GlobalOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { loginSuccess } from '@/store/auth/authSlice'
import { saveAuthData } from '@/utils/auth'
import { base64HashPassword } from '@/utils/password'
import apiClient from '@/api/client'
import { showMessage } from '@/utils/messages'
import { useTheme } from '@/context/ThemeContext'
import LanguageSelector from '@/components/common/LanguageSelector'
import logoBlack from '@/assets/logo_black.png'
import logoWhite from '@/assets/logo_white.png'

const { Title, Text } = Typography

interface LoginForm {
  email: string
  password: string
}

const LoginPage: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  const dispatch = useDispatch()
  const [form] = Form.useForm<LoginForm>()
  const { theme } = useTheme()
  const { t } = useTranslation(['auth', 'common'])

  const handleLogin = async (values: LoginForm) => {
    setLoading(true)
    setError(null)

    try {
      // Hash password
      const passwordHash = await base64HashPassword(values.password)

      // Attempt login
      const loginResponse = await apiClient.login(values.email, passwordHash)
      
      if (loginResponse.failure !== 0) {
        throw new Error(loginResponse.errors?.join('; ') || 'Login failed')
      }

      // Extract token
      const token = loginResponse.tables[0].data[0].nextRequestCredential
      if (!token) {
        throw new Error('No authentication token received')
      }

      // Get company info
      let company: string | undefined
      try {
        const companyResponse = await apiClient.getCompany(values.email, passwordHash)
        if (companyResponse.tables?.[0]?.data?.[0]) {
          company = companyResponse.tables[0].data[0].name
        }
      } catch (error) {
        console.error('Failed to get company info:', error)
      }

      // Save auth data
      saveAuthData(token, values.email, company)

      // Update Redux store
      dispatch(loginSuccess({
        user: { email: values.email, company },
        token,
        company,
      }))

      showMessage('success', t('common:messages.success'))
      navigate('/dashboard')
    } catch (error: any) {
      console.error('Login error:', error)
      setError(error.message || t('auth:login.errors.invalidCredentials'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card
      style={{
        width: 400,
        boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
      }}
    >
      <Space direction="vertical" size={24} style={{ width: '100%' }}>
        <div style={{ 
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: 96,
        }}>
          <img
            src={theme === 'dark' ? logoWhite : logoBlack}
            alt="Rediacc Logo"
            style={{
              height: 32,
              width: 'auto',
              maxWidth: 150,
              objectFit: 'contain',
            }}
          />
        </div>

        {error && (
          <Alert
            message={error}
            type="error"
            showIcon
            closable
            onClose={() => setError(null)}
          />
        )}

        <Form
          form={form}
          name="login"
          onFinish={handleLogin}
          layout="vertical"
          requiredMark={false}
        >
          <Form.Item
            name="email"
            label={t('auth:login.email')}
            rules={[
              { required: true, message: t('common:messages.required') },
              { type: 'email', message: t('common:messages.invalidEmail') },
            ]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder={t('auth:login.emailPlaceholder')}
              size="large"
              autoComplete="email"
            />
          </Form.Item>

          <Form.Item
            name="password"
            label={t('auth:login.password')}
            rules={[{ required: true, message: t('common:messages.required') }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={t('auth:login.passwordPlaceholder')}
              size="large"
              autoComplete="current-password"
            />
          </Form.Item>

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              size="large"
              block
              loading={loading}
              style={{
                background: '#556b2f',
                borderColor: '#556b2f',
                height: 48,
              }}
            >
              {t('auth:login.signIn')}
            </Button>
          </Form.Item>
          
          <div style={{ display: 'flex', justifyContent: 'center', marginTop: 16 }}>
            <LanguageSelector />
          </div>
        </Form>

        <div style={{ textAlign: 'center' }}>
          <Text type="secondary">
            {t('auth:login.noAccount')} {t('auth:login.register')}
          </Text>
        </div>
      </Space>
    </Card>
  )
}

export default LoginPage