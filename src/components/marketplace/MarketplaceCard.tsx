import React from 'react'
import { Card, Tag, Space, Button, Typography, Badge, Tooltip, Row, Col } from 'antd'
import {
  DatabaseOutlined,
  GlobalOutlined,
  CloudOutlined,
  AppstoreOutlined,
  StarOutlined,
  DeploymentUnitOutlined,
  ThunderboltOutlined,
  RocketOutlined,
  EyeOutlined
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'

const { Text, Paragraph } = Typography

interface Template {
  name: string
  readme: string
  category?: string
  tags?: string[]
  difficulty?: 'beginner' | 'intermediate' | 'advanced'
  popularity?: number
  isNew?: boolean
  isFeatured?: boolean
  prerequisites?: {
    minCpu?: number
    minMemory?: string
    minStorage?: string
  }
  iconUrl?: string
}

interface MarketplaceCardProps {
  template: Template
  viewMode: 'grid' | 'list'
  onDeploy: () => void
  onPreview: () => void
  selectedTeam?: string | null
  selectedMachine?: string | null
}

const MarketplaceCard: React.FC<MarketplaceCardProps> = ({
  template,
  viewMode,
  onDeploy,
  onPreview,
  selectedTeam,
  selectedMachine
}) => {
  const { t } = useTranslation(['marketplace', 'resources'])

  const getTemplateIcon = (name: string) => {
    const lowerName = name.toLowerCase()
    if (lowerName.includes('db_') || lowerName.includes('database') || lowerName.includes('sql')) {
      return <DatabaseOutlined style={{ fontSize: viewMode === 'list' ? 24 : 32 }} />
    }
    if (lowerName.includes('nginx') || lowerName.includes('wordpress') || lowerName.includes('web')) {
      return <GlobalOutlined style={{ fontSize: viewMode === 'list' ? 24 : 32 }} />
    }
    if (lowerName.includes('cloud') || lowerName.includes('route')) {
      return <CloudOutlined style={{ fontSize: viewMode === 'list' ? 24 : 32 }} />
    }
    if (lowerName.includes('monitor') || lowerName.includes('prometheus')) {
      return <DeploymentUnitOutlined style={{ fontSize: viewMode === 'list' ? 24 : 32 }} />
    }
    return <AppstoreOutlined style={{ fontSize: viewMode === 'list' ? 24 : 32 }} />
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

  const getCategoryText = (category?: string) => {
    return category ? t(`marketplace:category.${category}`) : ''
  }

  const canDeploy = true // Always allow deploy, machine will be selected in modal

  if (viewMode === 'list') {
    return (
      <Card hoverable>
        <Row gutter={16} align="middle">
          <Col flex="none">
            <div style={{ 
              width: 60, 
              height: 60, 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              background: '#f0f0f0',
              borderRadius: 8,
              overflow: 'hidden'
            }}>
              {template.iconUrl ? (
                <img 
                  src={template.iconUrl} 
                  alt={template.name}
                  style={{ width: 60, height: 60, objectFit: 'contain' }}
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
          </Col>
          <Col flex="auto">
            <Space direction="vertical" size={0} style={{ width: '100%' }}>
              <Space>
                <Text strong style={{ fontSize: 16 }}>
                  {getTemplateTitle(template.name)}
                </Text>
                {template.isFeatured && <Tag color="gold">{t('marketplace:featured')}</Tag>}
                {template.isNew && <Tag color="blue">{t('marketplace:new')}</Tag>}
                <Tag>{getCategoryText(template.category)}</Tag>
                <Tag color={getDifficultyColor(template.difficulty)}>
                  {getDifficultyText(template.difficulty)}
                </Tag>
              </Space>
              <Paragraph ellipsis={{ rows: 1 }} style={{ marginBottom: 8 }}>
                {getTemplateDescription(template.readme)}
              </Paragraph>
              <Space wrap>
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
            <Space direction="vertical" align="end">
              <Space>
                <StarOutlined /> {template.popularity || 0}
              </Space>
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
            </Space>
          </Col>
        </Row>
      </Card>
    )
  }

  // Grid view
  return (
    <Badge.Ribbon 
      text={template.isFeatured ? t('marketplace:featured') : template.isNew ? t('marketplace:new') : null} 
      color={template.isFeatured ? 'gold' : 'blue'}
      style={{ display: template.isFeatured || template.isNew ? 'block' : 'none' }}
    >
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
            <div style={{
              position: 'absolute',
              top: 8,
              right: 8,
              display: 'flex',
              gap: 4
            }}>
              <Tag>{getCategoryText(template.category)}</Tag>
            </div>
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

          <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between' }}>
            <Space size="small">
              <ThunderboltOutlined />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {template.prerequisites?.minCpu || 1} CPU
              </Text>
            </Space>
            <Space size="small">
              <StarOutlined />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {template.popularity || 0}
              </Text>
            </Space>
          </div>
        </Space>
      </Card>
    </Badge.Ribbon>
  )
}

export default MarketplaceCard