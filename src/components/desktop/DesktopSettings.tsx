import React, { useEffect, useState } from 'react'
import { Form, Input, Button, Card, message, InputNumber, Alert } from 'antd'
import { SaveOutlined, ReloadOutlined } from '@ant-design/icons'
import { configService } from '@/services/configService'
import { apiClient } from '@/api/client'
import { useDesktopMode } from '@/hooks/useDesktopMode'

interface SettingsForm {
  domain: string
  httpPort: number
}

const DesktopSettings: React.FC = () => {
  const [form] = Form.useForm<SettingsForm>()
  const [loading, setLoading] = useState(false)
  const [currentApiUrl, setCurrentApiUrl] = useState('')
  const isDesktop = useDesktopMode()

  useEffect(() => {
    loadCurrentSettings()
  }, [])

  const loadCurrentSettings = async () => {
    try {
      const config = await configService.getConfig()
      form.setFieldsValue({
        domain: config.domain,
        httpPort: config.httpPort
      })
      setCurrentApiUrl(config.apiUrl)
    } catch (error) {
      message.error('Failed to load current settings')
    }
  }

  const handleSave = async (values: SettingsForm) => {
    setLoading(true)
    try {
      const newApiUrl = `http://${values.domain}:${values.httpPort}/api`
      
      // Update config service
      await configService.updateConfig({
        domain: values.domain,
        httpPort: values.httpPort,
        apiUrl: newApiUrl
      })
      
      // Update API client
      apiClient.updateApiUrl(newApiUrl)
      
      setCurrentApiUrl(newApiUrl)
      message.success('Settings saved successfully')
    } catch (error) {
      message.error('Failed to save settings')
    } finally {
      setLoading(false)
    }
  }

  const handleReset = () => {
    loadCurrentSettings()
  }

  if (!isDesktop) {
    return (
      <Alert
        message="Desktop Only Feature"
        description="These settings are only available in the desktop application."
        type="info"
        showIcon
      />
    )
  }

  return (
    <Card title="Desktop Application Settings" style={{ maxWidth: 600 }}>
      <Form
        form={form}
        layout="vertical"
        onFinish={handleSave}
        initialValues={{
          domain: 'localhost',
          httpPort: 7322
        }}
      >
        <Form.Item
          label="API Domain"
          name="domain"
          rules={[{ required: true, message: 'Please enter the API domain' }]}
          help="The domain where your Rediacc API is hosted"
        >
          <Input placeholder="localhost" />
        </Form.Item>

        <Form.Item
          label="API Port"
          name="httpPort"
          rules={[{ required: true, message: 'Please enter the API port' }]}
          help="The port number for the Rediacc API"
        >
          <InputNumber min={1} max={65535} style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item>
          <Alert
            message="Current API URL"
            description={currentApiUrl}
            type="info"
            style={{ marginBottom: 16 }}
          />
        </Form.Item>

        <Form.Item>
          <Button 
            type="primary" 
            htmlType="submit" 
            loading={loading}
            icon={<SaveOutlined />}
          >
            Save Settings
          </Button>
          <Button 
            style={{ marginLeft: 8 }}
            onClick={handleReset}
            icon={<ReloadOutlined />}
          >
            Reset
          </Button>
        </Form.Item>
      </Form>

      <Alert
        message="Note"
        description="These settings are saved locally on your computer. If you don't have a .env file, the desktop app will use these settings to connect to the API."
        type="warning"
        showIcon
        style={{ marginTop: 16 }}
      />
    </Card>
  )
}

export default DesktopSettings