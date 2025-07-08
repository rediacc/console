import React, { useState, useEffect } from 'react'
import { Modal, Tabs, Typography, Space, Tag, Button, Alert, Spin, Row, Col, Card, Divider, List } from 'antd'
import {
  RocketOutlined,
  FileTextOutlined,
  CodeOutlined,
  SafetyOutlined,
  DatabaseOutlined,
  GlobalOutlined,
  CloudOutlined,
  AppstoreOutlined,
  DeploymentUnitOutlined,
  CheckCircleOutlined,
  FileOutlined
} from '@/utils/optimizedIcons'
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
}

const MarketplacePreview: React.FC<MarketplacePreviewProps> = ({
  visible,
  template,
  onClose,
  onDeploy
}) => {
  const { t } = useTranslation(['marketplace', 'resources'])
  const [loading, setLoading] = useState(false)
  const [templateDetails, setTemplateDetails] = useState<TemplateDetails | null>(null)
  const [activeTab, setActiveTab] = useState('overview')
  const [selectedFileIndex, setSelectedFileIndex] = useState(0)

  useEffect(() => {
    if (visible && template) {
      fetchTemplateDetails()
      setActiveTab('overview')
      setSelectedFileIndex(0)
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

  const canDeploy = true // Team selection happens in deployment modal

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
            <Tag color={getDifficultyColor(template.difficulty)}>
              {t(`difficulty${template.difficulty?.charAt(0).toUpperCase()}${template.difficulty?.slice(1)}`)}
            </Tag>
          </div>
        </Space>
      }
      visible={visible}
      onCancel={onClose}
      width="90vw"
      style={{ top: 20 }}
      bodyStyle={{ height: 'calc(90vh - 180px)', padding: '12px' }}
      footer={[
        <Button key="close" onClick={onClose}>
          {t('close')}
        </Button>,
        <Button
          key="deploy"
          type="primary"
          icon={<RocketOutlined />}
          onClick={() => onDeploy(template)}
        >
          {t('deployNow')}
        </Button>
      ]}
    >
      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab={<span><FileTextOutlined /> {t('overview')}</span>} key="overview">
          <div style={{ height: 'calc(90vh - 340px)', overflow: 'auto' }}>
            <Row gutter={[24, 24]}>
              <Col xs={24} md={16}>
                <Card 
                  title={t('description')}
                  bodyStyle={{ maxHeight: 'calc(90vh - 420px)', overflow: 'auto' }}
                >
                  <ReactMarkdown>{template.readme}</ReactMarkdown>
                </Card>
              </Col>
              <Col xs={24} md={8}>
                <Card 
                  title={t('features')}
                  bodyStyle={{ maxHeight: 'calc(90vh - 420px)', overflow: 'auto' }}
                >
                  <Space direction="vertical" size="small">
                    {template.tags?.map(tag => (
                      <Space key={tag}>
                        <CheckCircleOutlined style={{ color: '#52c41a' }} />
                        <Text>{tag}</Text>
                      </Space>
                    ))}
                  </Space>
                </Card>
              </Col>
            </Row>
          </div>
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
          ) : templateDetails && templateDetails.files.length > 0 ? (
            <Row gutter={16} style={{ height: 'calc(90vh - 340px)' }}>
              <Col span={8} style={{ height: '100%' }}>
                <Card 
                  size="small" 
                  title={<span><FileOutlined /> {t('fileList')}</span>}
                  bodyStyle={{ padding: 0, height: 'calc(100% - 38px)' }}
                  style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
                >
                  <List
                    size="small"
                    dataSource={templateDetails.files}
                    renderItem={(file, index) => (
                      <List.Item
                        style={{ 
                          padding: '8px 16px', 
                          cursor: 'pointer',
                          backgroundColor: selectedFileIndex === index ? '#1890ff20' : 'transparent',
                          borderLeft: selectedFileIndex === index ? '3px solid #1890ff' : '3px solid transparent',
                          transition: 'all 0.2s'
                        }}
                        onClick={() => setSelectedFileIndex(index)}
                      >
                        <Space>
                          <CodeOutlined />
                          <Text 
                            code 
                            style={{ 
                              fontWeight: selectedFileIndex === index ? 600 : 400,
                              color: selectedFileIndex === index ? '#1890ff' : undefined
                            }}
                          >
                            {file.path || file.name}
                          </Text>
                        </Space>
                      </List.Item>
                    )}
                    style={{ height: '100%', overflow: 'auto' }}
                  />
                </Card>
              </Col>
              <Col span={16} style={{ height: '100%' }}>
                <Card
                  size="small"
                  title={
                    <Space>
                      <CodeOutlined />
                      <Text code>{templateDetails.files[selectedFileIndex]?.path || templateDetails.files[selectedFileIndex]?.name}</Text>
                    </Space>
                  }
                  style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
                  bodyStyle={{ flex: 1, overflow: 'auto', padding: '12px' }}
                >
                  {templateDetails.files[selectedFileIndex] && renderFileContent(templateDetails.files[selectedFileIndex])}
                </Card>
              </Col>
            </Row>
          ) : (
            <Alert
              message={t('noFiles')}
              description={t('noFilesDesc')}
              type="info"
              showIcon
            />
          )}
        </TabPane>

        <TabPane tab={<span><SafetyOutlined /> {t('security')}</span>} key="security">
          <div style={{ height: 'calc(90vh - 340px)', overflow: 'auto' }}>
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
          </div>
        </TabPane>
      </Tabs>
    </Modal>
  )
}

export default MarketplacePreview