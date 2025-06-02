import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDispatch } from 'react-redux'
import { Card, Form, Input, Button, Typography, Space, Alert } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { loginSuccess } from '@/store/auth/authSlice'
import { saveAuthData } from '@/utils/auth'
import { base64HashPassword } from '@/utils/password'
import apiClient from '@/api/client'
import { showMessage } from '@/utils/messages'

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

      showMessage('success', 'Login successful!')
      navigate('/dashboard')
    } catch (error: any) {
      console.error('Login error:', error)
      setError(error.message || 'Login failed. Please check your credentials.')
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
        <div style={{ textAlign: 'center' }}>
          <Title level={2} style={{ marginBottom: 8, color: '#556b2f' }}>
            Rediacc Console
          </Title>
          <Text type="secondary">Sign in to your account</Text>
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
            label="Email"
            rules={[
              { required: true, message: 'Please enter your email' },
              { type: 'email', message: 'Please enter a valid email' },
            ]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="Enter your email"
              size="large"
              autoComplete="email"
            />
          </Form.Item>

          <Form.Item
            name="password"
            label="Password"
            rules={[{ required: true, message: 'Please enter your password' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="Enter your password"
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
              Sign In
            </Button>
          </Form.Item>
        </Form>

        <div style={{ textAlign: 'center' }}>
          <Text type="secondary">
            Don't have an account? Contact your administrator
          </Text>
        </div>
      </Space>
    </Card>
  )
}

export default LoginPage