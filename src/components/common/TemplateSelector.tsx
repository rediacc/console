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
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing, borderRadius, fontSize } from '@/utils/styleConstants'
import { configService } from '@/services/configService'

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
  const styles = useComponentStyles()

  useEffect(() => {
    fetchTemplates()
  }, [])

  const fetchTemplates = async () => {
    try {
      setLoading(true)
      setError(null)

      const templatesUrl = await configService.getTemplatesUrl()
      const response = await fetch(templatesUrl)
      if (!response.ok) {
        throw new Error('Failed to fetch templates')
      }

      const data = await response.json()
      setTemplates(data.templates || [])
    } catch (err) {
      console.error('Failed to fetch templates:', err)
      setError('Unable to load templates. Please check your connection.')
      message.error('Unable to load templates. Please check your connection.')
    } finally {
      setLoading(false)
    }
  }

  const getTemplateIcon = (name: string) => {
    const iconStyle = { fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_LG }
    const lowerName = name.toLowerCase()
    if (lowerName.includes('db_') || lowerName.includes('database') || lowerName.includes('sql')) {
      return <DatabaseOutlined style={iconStyle} />
    }
    if (lowerName.includes('nginx') || lowerName.includes('wordpress') || lowerName.includes('web')) {
      return <GlobalOutlined style={iconStyle} />
    }
    if (lowerName.includes('cloud') || lowerName.includes('route')) {
      return <CloudOutlined style={iconStyle} />
    }
    return <AppstoreOutlined style={iconStyle} />
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
        <Spin />
        <div style={{ marginTop: 16, color: 'var(--ant-color-text-secondary)' }}>
          {t('resources:templates.loading')}
        </div>
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
      <Space direction="vertical" size="middle" style={{ width: '100%', marginBottom: spacing('MD') }}>
        <div style={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center',
          marginBottom: spacing('SM')
        }}>
          <Text type="secondary" style={{ fontSize: fontSize('SM') }}>
            {t('resources:templates.selectOptional')}
          </Text>
          {value && (
            <Button 
              size="small" 
              style={{
                // Height managed by CSS
                borderRadius: borderRadius('MD'),
                fontSize: fontSize('SM')
              }}
              data-testid="resource-modal-template-clear-button"
              onClick={() => onChange?.(null)}
            >
              {t('resources:templates.clearSelection')}
            </Button>
          )}
        </div>
      </Space>

      <Row gutter={[spacing('MD'), spacing('MD')]}>
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
                  borderColor: isSelected ? 'var(--color-primary)' : 'var(--color-border-secondary)',
                  borderWidth: isSelected ? 2 : 1,
                  borderRadius: borderRadius('LG'),
                  position: 'relative',
                  cursor: 'pointer',
                  transition: DESIGN_TOKENS.TRANSITIONS.HOVER,
                  padding: spacing('MD')
                }}
                onClick={() => onChange?.(isSelected ? null : template.name)}
              >
                {isSelected && (
                  <CheckCircleOutlined 
                    style={{ 
                      position: 'absolute', 
                      top: spacing('SM'), 
                      right: spacing('SM'), 
                      color: 'var(--color-primary)',
                      fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD
                    }} 
                  />
                )}
                
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  <div style={{ 
                    textAlign: 'center', 
                    marginBottom: spacing('XS'),
                    padding: spacing('SM')
                  }}>
                    {getTemplateIcon(template.name)}
                  </div>
                  
                  <Text strong style={{ fontSize: fontSize('BASE') }}>
                    {getTemplateTitle(template.name)}
                  </Text>
                  
                  <Paragraph 
                    ellipsis={{ rows: 2 }} 
                    type="secondary"
                    style={{ 
                      marginBottom: spacing('SM'), 
                      // Height managed by CSS
                      fontSize: fontSize('SM'),
                      lineHeight: DESIGN_TOKENS.LINE_HEIGHT.RELAXED
                    }}
                  >
                    {getTemplateDescription(template.readme)}
                  </Paragraph>
                  
                  <Button
                    type="link"
                    size="small"
                    data-testid={`resource-modal-template-details-button-${template.name}`}
                    icon={<InfoCircleOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_SM }} />}
                    onClick={(e) => {
                      e.stopPropagation()
                      onViewDetails?.(template.name)
                    }}
                    style={{ 
                      padding: 0,
                      // Height managed by CSS
                      fontSize: fontSize('SM')
                    }}
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
              borderColor: !value ? 'var(--color-success)' : 'var(--color-border-secondary)',
              borderWidth: !value ? 2 : 1,
              borderStyle: 'dashed',
              borderRadius: borderRadius('LG'),
              position: 'relative',
              cursor: 'pointer',
              transition: DESIGN_TOKENS.TRANSITIONS.HOVER,
              padding: spacing('MD')
            }}
            onClick={() => onChange?.(null)}
          >
            {!value && (
              <CheckCircleOutlined 
                style={{ 
                  position: 'absolute', 
                  top: spacing('SM'), 
                  right: spacing('SM'), 
                  color: 'var(--color-success)',
                  fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD
                }} 
              />
            )}
            
            <Space direction="vertical" size="small" style={{ width: '100%' }}>
              <div style={{ 
                textAlign: 'center', 
                marginBottom: spacing('XS'),
                padding: spacing('SM')
              }}>
                <AppstoreOutlined style={{ 
                  fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_LG, 
                  color: 'var(--color-text-tertiary)' 
                }} />
              </div>
              
              <Text strong style={{ fontSize: fontSize('BASE') }}>
                {t('resources:templates.noTemplate')}
              </Text>
              
              <Paragraph 
                type="secondary"
                style={{ 
                  marginBottom: spacing('SM'), 
                  // Height managed by CSS
                  fontSize: fontSize('SM'),
                  lineHeight: DESIGN_TOKENS.LINE_HEIGHT.RELAXED
                }}
              >
                {t('resources:templates.startEmpty')}
              </Paragraph>
              
              <Tag 
                color="default" 
                style={{ 
                  margin: 0,
                  borderRadius: borderRadius('SM'),
                  fontSize: fontSize('XS')
                }}
              >
                {t('resources:templates.default')}
              </Tag>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  )
}

export default TemplateSelector