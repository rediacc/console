import React, { useState, useEffect } from 'react'
import { Card, Row, Col, Button, Space, Typography, Spin, Empty, Tag, message } from 'antd'
import { 
  DatabaseOutlined, 
  GlobalOutlined, 
  CloudOutlined, 
  CheckCircleOutlined,
  InfoCircleOutlined,
  AppstoreOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'

const { Text, Paragraph } = Typography

interface Template {
  name: string
  readme: string
}

interface TemplateSelectorProps {
  value?: string | null
  onChange?: (templateName: string | null) => void
  onViewDetails?: (templateName: string) => void
}

const TemplateSelector: React.FC<TemplateSelectorProps> = ({ 
  value, 
  onChange, 
  onViewDetails 
}) => {
  const { t } = useTranslation(['resources', 'common'])
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchTemplates()
  }, [])

  const fetchTemplates = async () => {
    try {
      setLoading(true)
      setError(null)
      
      const response = await fetch(`${window.location.origin}/config/templates.json`)
      if (!response.ok) {
        throw new Error('Failed to fetch templates')
      }
      
      const data = await response.json()
      setTemplates(data.templates || [])
    } catch (err) {
      setError('Failed to load templates')
      message.error('Failed to load templates')
    } finally {
      setLoading(false)
    }
  }

  const getTemplateIcon = (name: string) => {
    const lowerName = name.toLowerCase()
    if (lowerName.includes('db_') || lowerName.includes('database') || lowerName.includes('sql')) {
      return <DatabaseOutlined style={{ fontSize: 24 }} />
    }
    if (lowerName.includes('nginx') || lowerName.includes('wordpress') || lowerName.includes('web')) {
      return <GlobalOutlined style={{ fontSize: 24 }} />
    }
    if (lowerName.includes('cloud') || lowerName.includes('route')) {
      return <CloudOutlined style={{ fontSize: 24 }} />
    }
    return <AppstoreOutlined style={{ fontSize: 24 }} />
  }

  const getTemplateTitle = (name: string) => {
    // Extract meaningful title from template name
    const cleanName = name.replace(/^(db_|kick_|route_)/, '')
    return cleanName.charAt(0).toUpperCase() + cleanName.slice(1)
  }

  const getTemplateDescription = (readme: string) => {
    // Extract first meaningful line from README
    const lines = readme.split('\n').filter(line => line.trim() && !line.startsWith('#'))
    return lines[0] || 'Template for quick deployment'
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 0' }}>
        <Spin tip={t('resources:templates.loading')} />
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ textAlign: 'center', padding: '20px 0' }}>
        <Empty description={error} />
      </div>
    )
  }

  return (
    <div>
      <Space direction="vertical" size="middle" style={{ width: '100%', marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text type="secondary">
            {t('resources:templates.selectOptional')}
          </Text>
          {value && (
            <Button 
              size="small" 
              data-testid="resource-modal-template-clear-button"
              onClick={() => onChange?.(null)}
            >
              {t('resources:templates.clearSelection')}
            </Button>
          )}
        </div>
      </Space>

      <Row gutter={[16, 16]}>
        {templates.map((template) => {
          const isSelected = value === template.name
          
          return (
            <Col key={template.name} xs={24} sm={12} md={8}>
              <Card
                hoverable
                data-testid={`resource-modal-template-card-${template.name}`}
                className={isSelected ? 'template-card-selected' : 'template-card'}
                style={{
                  height: '100%',
                  borderColor: isSelected ? '#1890ff' : undefined,
                  borderWidth: isSelected ? 2 : 1,
                  position: 'relative'
                }}
                onClick={() => onChange?.(isSelected ? null : template.name)}
              >
                {isSelected && (
                  <CheckCircleOutlined 
                    style={{ 
                      position: 'absolute', 
                      top: 8, 
                      right: 8, 
                      color: '#1890ff',
                      fontSize: 20
                    }} 
                  />
                )}
                
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  <div style={{ textAlign: 'center', marginBottom: 8 }}>
                    {getTemplateIcon(template.name)}
                  </div>
                  
                  <Text strong style={{ fontSize: 16 }}>
                    {getTemplateTitle(template.name)}
                  </Text>
                  
                  <Paragraph 
                    ellipsis={{ rows: 2 }} 
                    type="secondary"
                    style={{ marginBottom: 12, minHeight: 44 }}
                  >
                    {getTemplateDescription(template.readme)}
                  </Paragraph>
                  
                  <Button
                    type="link"
                    size="small"
                    data-testid={`resource-modal-template-details-button-${template.name}`}
                    icon={<InfoCircleOutlined />}
                    onClick={(e) => {
                      e.stopPropagation()
                      onViewDetails?.(template.name)
                    }}
                    style={{ padding: 0 }}
                  >
                    {t('resources:templates.viewDetails')}
                  </Button>
                </Space>
              </Card>
            </Col>
          )
        })}
        
        {/* No Template Option */}
        <Col xs={24} sm={12} md={8}>
          <Card
            hoverable
            data-testid="resource-modal-template-card-none"
            className={!value ? 'template-card-selected' : 'template-card'}
            style={{
              height: '100%',
              borderColor: !value ? '#52c41a' : undefined,
              borderWidth: !value ? 2 : 1,
              borderStyle: 'dashed',
              position: 'relative'
            }}
            onClick={() => onChange?.(null)}
          >
            {!value && (
              <CheckCircleOutlined 
                style={{ 
                  position: 'absolute', 
                  top: 8, 
                  right: 8, 
                  color: '#52c41a',
                  fontSize: 20
                }} 
              />
            )}
            
            <Space direction="vertical" size="small" style={{ width: '100%' }}>
              <div style={{ textAlign: 'center', marginBottom: 8 }}>
                <AppstoreOutlined style={{ fontSize: 24, color: '#999' }} />
              </div>
              
              <Text strong style={{ fontSize: 16 }}>
                {t('resources:templates.noTemplate')}
              </Text>
              
              <Paragraph 
                type="secondary"
                style={{ marginBottom: 12, minHeight: 44 }}
              >
                {t('resources:templates.startEmpty')}
              </Paragraph>
              
              <Tag color="default" style={{ margin: 0 }}>
                {t('resources:templates.default')}
              </Tag>
            </Space>
          </Card>
        </Col>
      </Row>
      
      <style jsx>{`
        .template-card:hover {
          border-color: #40a9ff;
        }
        .template-card-selected {
          background-color: #f0f5ff;
        }
      `}</style>
    </div>
  )
}

export default TemplateSelector