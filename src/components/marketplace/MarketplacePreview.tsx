import React, { useState, useEffect } from 'react'
import { Modal, Tabs, Typography, Space, Tag, Button, Descriptions, Alert, Spin, Row, Col, Card, Divider } from 'antd'
import {
  RocketOutlined,
  FileTextOutlined,
  CodeOutlined,
  SafetyOutlined,
  ThunderboltOutlined,
  DatabaseOutlined,
  GlobalOutlined,
  CloudOutlined,
  AppstoreOutlined,
  DeploymentUnitOutlined,
  CheckCircleOutlined,
  WarningOutlined
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

const { Title, Text, Paragraph } = Typography
const { TabPane } = Tabs

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

interface TemplateDetails {
  name: string
  readme: string
  files: Array<{
    name: string
    path: string
    content: string
  }>
}

interface MarketplacePreviewProps {
  visible: boolean
  template: Template | null
  onClose: () => void
  onDeploy: (template: Template) => void
  selectedTeam?: string | null
  selectedMachine?: string | null
}

const MarketplacePreview: React.FC<MarketplacePreviewProps> = ({
  visible,
  template,
  onClose,
  onDeploy,
  selectedTeam,
  selectedMachine
}) => {
  const { t } = useTranslation(['marketplace', 'resources'])
  const [loading, setLoading] = useState(false)
  const [templateDetails, setTemplateDetails] = useState<TemplateDetails | null>(null)
  const [activeTab, setActiveTab] = useState('overview')

  useEffect(() => {
    if (visible && template) {
      fetchTemplateDetails()
      setActiveTab('overview')
    }
  }, [visible, template])

  const fetchTemplateDetails = async () => {
    if (!template) return
    
    try {
      setLoading(true)
      const response = await fetch(`${window.location.origin}/config/template_${template.name}.json`)
      if (response.ok) {
        const data = await response.json()
        setTemplateDetails(data)
      }
    } catch (error) {
      console.error('Failed to fetch template details:', error)
    } finally {
      setLoading(false)
    }
  }

  if (!template) return null

  const getTemplateIcon = (name: string) => {
    const lowerName = name.toLowerCase()
    if (lowerName.includes('db_') || lowerName.includes('database') || lowerName.includes('sql')) {
      return <DatabaseOutlined style={{ fontSize: 48 }} />
    }
    if (lowerName.includes('nginx') || lowerName.includes('wordpress') || lowerName.includes('web')) {
      return <GlobalOutlined style={{ fontSize: 48 }} />
    }
    if (lowerName.includes('cloud') || lowerName.includes('route')) {
      return <CloudOutlined style={{ fontSize: 48 }} />
    }
    if (lowerName.includes('monitor') || lowerName.includes('prometheus')) {
      return <DeploymentUnitOutlined style={{ fontSize: 48 }} />
    }
    return <AppstoreOutlined style={{ fontSize: 48 }} />
  }

  const getTemplateTitle = (name: string) => {
    const cleanName = name.replace(/^(db_|kick_|route_|monitor_|cache_|queue_|auth_|search_|dev_|manage_|api_)/, '')
    return cleanName.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
  }

  const getDifficultyColor = (difficulty?: string) => {
    switch (difficulty) {
      case 'beginner': return 'success'
      case 'intermediate': return 'warning'
      case 'advanced': return 'error'
      default: return 'default'
    }
  }

  const canDeploy = selectedTeam && selectedMachine

  const renderFileContent = (file: { name: string; content: string }) => {
    const language = file.name.endsWith('.yaml') || file.name.endsWith('.yml') ? 'yaml' :
                    file.name.endsWith('.json') ? 'json' :
                    file.name.endsWith('.sh') ? 'bash' :
                    file.name.endsWith('.env') ? 'bash' :
                    file.name.endsWith('.md') ? 'markdown' : 'text'

    if (language === 'markdown') {
      return (
        <ReactMarkdown
          components={{
            code({node, inline, className, children, ...props}) {
              const match = /language-(\w+)/.exec(className || '')
              return !inline && match ? (
                <SyntaxHighlighter
                  style={vscDarkPlus}
                  language={match[1]}
                  PreTag="div"
                  {...props}
                >
                  {String(children).replace(/\n$/, '')}
                </SyntaxHighlighter>
              ) : (
                <code className={className} {...props}>
                  {children}
                </code>
              )
            }
          }}
        >
          {file.content}
        </ReactMarkdown>
      )
    }

    return (
      <SyntaxHighlighter language={language} style={vscDarkPlus}>
        {file.content}
      </SyntaxHighlighter>
    )
  }

  return (
    <Modal
      title={
        <Space>
          {template.iconUrl ? (
            <img 
              src={template.iconUrl} 
              alt={template.name}
              style={{ 
                width: 48, 
                height: 48, 
                objectFit: 'contain',
                filter: 'drop-shadow(0px 2px 4px rgba(0,0,0,0.1))'
              }}
              onError={(e) => {
                e.currentTarget.style.display = 'none'
                e.currentTarget.parentElement?.appendChild(
                  <span>{getTemplateIcon(template.name)}</span> as any
                )
              }}
            />
          ) : (
            getTemplateIcon(template.name)
          )}
          <div>
            <Title level={4} style={{ margin: 0 }}>
              {getTemplateTitle(template.name)}
            </Title>
            <Space wrap>
              {template.isFeatured && <Tag color="gold">{t('featured')}</Tag>}
              {template.isNew && <Tag color="blue">{t('new')}</Tag>}
              <Tag>{t(`category.${template.category}`)}</Tag>
              <Tag color={getDifficultyColor(template.difficulty)}>
                {t(`difficulty${template.difficulty?.charAt(0).toUpperCase()}${template.difficulty?.slice(1)}`)}
              </Tag>
            </Space>
          </div>
        </Space>
      }
      visible={visible}
      onCancel={onClose}
      width="90vw"
      style={{ top: 20 }}
      bodyStyle={{ height: 'calc(90vh - 180px)', overflow: 'auto' }}
      footer={[
        <Button key="close" onClick={onClose}>
          {t('close')}
        </Button>,
        <Button
          key="deploy"
          type="primary"
          icon={<RocketOutlined />}
          onClick={() => onDeploy(template)}
          disabled={!canDeploy}
        >
          {canDeploy ? t('deployNow') : t('selectTeamAndMachine')}
        </Button>
      ]}
    >
      {!canDeploy && (
        <Alert
          message={t('deploymentRequirements')}
          description={t('selectTeamAndMachineDesc')}
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          style={{ marginBottom: 16 }}
        />
      )}

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab={<span><FileTextOutlined /> {t('overview')}</span>} key="overview">
          <Row gutter={[24, 24]}>
            <Col xs={24} md={16}>
              <Card title={t('description')}>
                <ReactMarkdown>{template.readme}</ReactMarkdown>
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Card title={t('requirements')}>
                  <Descriptions column={1} size="small">
                    <Descriptions.Item label={t('minCpu')}>
                      <Space>
                        <ThunderboltOutlined />
                        {template.prerequisites?.minCpu || 1} vCPU
                      </Space>
                    </Descriptions.Item>
                    <Descriptions.Item label={t('minMemory')}>
                      <Space>
                        <DatabaseOutlined />
                        {template.prerequisites?.minMemory || '1G'}
                      </Space>
                    </Descriptions.Item>
                    <Descriptions.Item label={t('minStorage')}>
                      <Space>
                        <CloudOutlined />
                        {template.prerequisites?.minStorage || '10G'}
                      </Space>
                    </Descriptions.Item>
                  </Descriptions>
                </Card>

                <Card title={t('features')}>
                  <Space direction="vertical" size="small">
                    {template.tags?.map(tag => (
                      <Space key={tag}>
                        <CheckCircleOutlined style={{ color: '#52c41a' }} />
                        <Text>{tag}</Text>
                      </Space>
                    ))}
                  </Space>
                </Card>

                <Card>
                  <Descriptions column={1} size="small">
                    <Descriptions.Item label={t('popularity')}>
                      {template.popularity || 0} {t('deployments')}
                    </Descriptions.Item>
                    <Descriptions.Item label={t('lastUpdated')}>
                      {t('recently')}
                    </Descriptions.Item>
                  </Descriptions>
                </Card>
              </Space>
            </Col>
          </Row>
        </TabPane>

        <TabPane 
          tab={<span><CodeOutlined /> {t('files')}</span>} 
          key="files"
          disabled={loading || !templateDetails}
        >
          {loading ? (
            <div style={{ textAlign: 'center', padding: '40px 0' }}>
              <Spin tip={t('loadingFiles')} />
            </div>
          ) : templateDetails ? (
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              {templateDetails.files.map((file, index) => (
                <Card
                  key={index}
                  title={
                    <Space>
                      <CodeOutlined />
                      <Text code>{file.path || file.name}</Text>
                    </Space>
                  }
                  size="small"
                >
                  <div style={{ maxHeight: 400, overflow: 'auto' }}>
                    {renderFileContent(file)}
                  </div>
                </Card>
              ))}
            </Space>
          ) : null}
        </TabPane>

        <TabPane tab={<span><SafetyOutlined /> {t('security')}</span>} key="security">
          <Card>
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <Alert
                message={t('securityReview')}
                description={t('securityReviewDesc')}
                type="info"
                showIcon
              />
              
              <Title level={5}>{t('bestPractices')}</Title>
              <ul>
                <li>{t('securityTip1')}</li>
                <li>{t('securityTip2')}</li>
                <li>{t('securityTip3')}</li>
                <li>{t('securityTip4')}</li>
              </ul>

              <Divider />
              
              <Title level={5}>{t('containerSecurity')}</Title>
              <Paragraph>
                {t('containerSecurityDesc')}
              </Paragraph>
            </Space>
          </Card>
        </TabPane>
      </Tabs>
    </Modal>
  )
}

export default MarketplacePreview