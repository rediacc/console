import React from 'react'
import { Card, Tag, Space, Button, Typography, Row, Col } from 'antd'
import {
  DatabaseOutlined,
  GlobalOutlined,
  CloudOutlined,
  AppstoreOutlined,
  DeploymentUnitOutlined,
  RocketOutlined,
  EyeOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'

const { Text, Paragraph } = Typography

interface Template {
  name: string
  readme: string
  category?: string
  tags?: string[]
  difficulty?: 'beginner' | 'intermediate' | 'advanced'
  iconUrl?: string
}

interface MarketplaceCardProps {
  template: Template
  viewMode: 'grid' | 'list'
  onDeploy: () => void
  onPreview: () => void
}

const MarketplaceCard: React.FC<MarketplaceCardProps> = ({
  template,
  viewMode,
  onDeploy,
  onPreview
}) => {
  const { t } = useTranslation(['marketplace', 'resources'])

  const getTemplateIcon = (name: string) => {
    const lowerName = name.toLowerCase()
    if (lowerName.includes('db_') || lowerName.includes('database') || lowerName.includes('sql')) {
      return <DatabaseOutlined style={{ fontSize: viewMode === 'list' ? 20 : 32 }} />
    }
    if (lowerName.includes('nginx') || lowerName.includes('wordpress') || lowerName.includes('web')) {
      return <GlobalOutlined style={{ fontSize: viewMode === 'list' ? 20 : 32 }} />
    }
    if (lowerName.includes('cloud') || lowerName.includes('route')) {
      return <CloudOutlined style={{ fontSize: viewMode === 'list' ? 20 : 32 }} />
    }
    if (lowerName.includes('monitor') || lowerName.includes('prometheus')) {
      return <DeploymentUnitOutlined style={{ fontSize: viewMode === 'list' ? 20 : 32 }} />
    }
    return <AppstoreOutlined style={{ fontSize: viewMode === 'list' ? 20 : 32 }} />
  }

  const getTemplateTitle = (name: string) => {
    const cleanName = name.replace(/^(db_|kick_|route_|monitor_|cache_|queue_|auth_|search_|dev_|manage_|api_)/, '')
    return cleanName.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
  }

  const getTemplateDescription = (readme: string) => {
    const lines = readme.split('\n').filter(line => line.trim() && !line.startsWith('#'))
    return lines[0] || 'Template for quick deployment'
  }

  const getDifficultyColor = (difficulty?: string) => {
    switch (difficulty) {
      case 'beginner': return 'success'
      case 'intermediate': return 'warning'
      case 'advanced': return 'error'
      default: return 'default'
    }
  }

  const getDifficultyText = (difficulty?: string) => {
    switch (difficulty) {
      case 'beginner': return t('marketplace:difficultyBeginner')
      case 'intermediate': return t('marketplace:difficultyIntermediate')
      case 'advanced': return t('marketplace:difficultyAdvanced')
      default: return ''
    }
  }

  const canDeploy = true // Always allow deploy, machine will be selected in modal

  if (viewMode === 'list') {
    return (
      <Card hoverable>
        <Row gutter={16} align="middle">
          <Col flex="auto">
            <Space direction="vertical" size={0} style={{ width: '100%' }}>
              <Space>
                <Text strong style={{ fontSize: 16 }}>
                  {getTemplateTitle(template.name)}
                </Text>
                <Tag color={getDifficultyColor(template.difficulty)}>
                  {getDifficultyText(template.difficulty)}
                </Tag>
              </Space>
              <div style={{ display: 'flex', alignItems: 'center', marginTop: 4 }}>
                <Paragraph ellipsis={{ rows: 1 }} style={{ marginBottom: 0, flex: 1, marginRight: 8 }}>
                  {getTemplateDescription(template.readme)}
                </Paragraph>
                <div style={{ 
                  width: 40, 
                  height: 40, 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center',
                  background: '#f0f0f0',
                  borderRadius: 6,
                  overflow: 'hidden',
                  flexShrink: 0
                }}>
                  {template.iconUrl ? (
                    <img 
                      src={template.iconUrl} 
                      alt={template.name}
                      style={{ width: 40, height: 40, objectFit: 'contain' }}
                      onError={(e) => {
                        e.currentTarget.style.display = 'none'
                        const icon = document.createElement('div')
                        icon.innerHTML = getTemplateIcon(template.name) as any
                        e.currentTarget.parentElement?.appendChild(icon)
                      }}
                    />
                  ) : (
                    getTemplateIcon(template.name)
                  )}
                </div>
              </div>
              <Space wrap style={{ marginTop: 8 }}>
                {template.tags?.slice(0, 3).map(tag => (
                  <Tag key={tag}>{tag}</Tag>
                ))}
                {template.tags && template.tags.length > 3 && (
                  <Tag>+{template.tags.length - 3}</Tag>
                )}
              </Space>
            </Space>
          </Col>
          <Col flex="none">
            <Space>
              <Button icon={<EyeOutlined />} onClick={onPreview}>
                {t('marketplace:preview')}
              </Button>
              <Button 
                type="primary"
                icon={<RocketOutlined />}
                onClick={onDeploy}
              >
                {t('marketplace:deploy')}
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>
    )
  }

  // Grid view
  return (
    <Card
        hoverable
        cover={
          <div style={{
            height: 120,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'linear-gradient(135deg, #f5f5f5 0%, #e8e8e8 100%)',
            position: 'relative',
            overflow: 'hidden'
          }}>
            {template.iconUrl ? (
              <img 
                src={template.iconUrl} 
                alt={template.name}
                style={{ 
                  width: 80, 
                  height: 80, 
                  objectFit: 'contain',
                  filter: 'drop-shadow(0px 2px 4px rgba(0,0,0,0.1))'
                }}
                onError={(e) => {
                  e.currentTarget.style.display = 'none'
                  const icon = document.createElement('div')
                  icon.innerHTML = getTemplateIcon(template.name) as any
                  e.currentTarget.parentElement?.appendChild(icon)
                }}
              />
            ) : (
              getTemplateIcon(template.name)
            )}
          </div>
        }
        actions={[
          <Button key="preview" type="text" icon={<EyeOutlined />} onClick={onPreview}>
            {t('marketplace:preview')}
          </Button>,
          <Button 
            key="deploy"
            type="text"
            icon={<RocketOutlined />}
            onClick={onDeploy}
            style={{ color: '#1890ff' }}
          >
            {t('marketplace:deploy')}
          </Button>
        ]}
      >
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          <div>
            <Text strong style={{ fontSize: 16 }}>
              {getTemplateTitle(template.name)}
            </Text>
          </div>
          
          <Paragraph 
            ellipsis={{ rows: 2 }} 
            type="secondary"
            style={{ marginBottom: 12, minHeight: 44 }}
          >
            {getTemplateDescription(template.readme)}
          </Paragraph>

          <Space wrap size={4}>
            <Tag color={getDifficultyColor(template.difficulty)}>
              {getDifficultyText(template.difficulty)}
            </Tag>
            {template.tags?.slice(0, 2).map(tag => (
              <Tag key={tag}>{tag}</Tag>
            ))}
          </Space>

        </Space>
      </Card>
  )
}

export default MarketplaceCard