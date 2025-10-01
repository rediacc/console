import React, { useState, useEffect } from 'react'
import { Modal, Tabs, Typography, Space, Tag, Button, Alert, Spin, Row, Col, Card, Divider, List } from 'antd'
import { ModalSize } from '@/types/modal'
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
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing, borderRadius } from '@/utils/styleConstants'

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
  const styles = useComponentStyles()
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
      const response = await fetch(`${window.location.origin}/configs/template_${template.name}.json`)
      if (response.ok) {
        const data = await response.json()
        setTemplateDetails(data)
      }
    } catch (error) {
      // Failed to fetch template details
    } finally {
      setLoading(false)
    }
  }

  if (!template) return null

  const getTemplateIcon = (name: string) => {
    const lowerName = name.toLowerCase()
    if (lowerName.includes('db_') || lowerName.includes('database') || lowerName.includes('sql')) {
      return <DatabaseOutlined style={styles.icon.xxlarge} />
    }
    if (lowerName.includes('nginx') || lowerName.includes('wordpress') || lowerName.includes('web')) {
      return <GlobalOutlined style={styles.icon.xxlarge} />
    }
    if (lowerName.includes('cloud') || lowerName.includes('route')) {
      return <CloudOutlined style={styles.icon.xxlarge} />
    }
    if (lowerName.includes('monitor') || lowerName.includes('prometheus')) {
      return <DeploymentUnitOutlined style={styles.icon.xxlarge} />
    }
    return <AppstoreOutlined style={styles.icon.xxlarge} />
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
      data-testid="marketplace-preview-modal"
      title={
        <Space size={spacing('MD')}>
          {template.iconUrl ? (
            <img 
              src={template.iconUrl} 
              alt={template.name}
              style={{ 
                width: DESIGN_TOKENS.DIMENSIONS.ICON_XXL, 
                height: DESIGN_TOKENS.DIMENSIONS.ICON_XXL, 
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
            <Title level={4} style={{ ...styles.heading4, margin: 0 }}>
              {getTemplateTitle(template.name)}
            </Title>
            <Tag 
              color={getDifficultyColor(template.difficulty)}
              style={{
                borderRadius: borderRadius('SM'),
                fontSize: DESIGN_TOKENS.FONT_SIZE.SM,
                marginTop: spacing('XS')
              }}
            >
              {t(`difficulty${template.difficulty?.charAt(0).toUpperCase()}${template.difficulty?.slice(1)}`)}
            </Tag>
          </div>
        </Space>
      }
      visible={visible}
      onCancel={onClose}
      className={ModalSize.ExtraLarge}
      style={{ 
        top: 20,
        ...styles.modalXLarge
      }}
      styles={{
        body: {
          height: 'calc(90vh - 180px)',
          padding: spacing('MD')
        }
      }}
      footer={[
        <Button 
          key="close" 
          onClick={onClose}
          data-testid="marketplace-preview-close-button"
          style={{
            ...styles.buttonSecondary,
            marginRight: spacing('SM')
          }}
        >
          {t('close')}
        </Button>,
        <Button
          key="deploy"
          type="primary"
          icon={<RocketOutlined />}
          onClick={() => onDeploy(template)}
          data-testid="marketplace-preview-deploy-button"
          style={styles.buttonPrimary}
        >
          {t('deployNow')}
        </Button>
      ]}
    >
      <Tabs 
        activeKey={activeTab} 
        onChange={setActiveTab} 
        data-testid="marketplace-preview-tabs"
        size="large"
        style={{
          '.ant-tabs-tab': {
            minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
            display: 'flex',
            alignItems: 'center'
          }
        }}
      >
        <TabPane 
          tab={
            <span style={styles.flexCenter}>
              <FileTextOutlined style={{ marginRight: spacing('XS') }} /> 
              {t('overview')}
            </span>
          } 
          key="overview" 
          data-testid="marketplace-preview-tab-overview"
        >
          <div style={{ height: 'calc(90vh - 340px)', overflow: 'auto' }}>
            <Row gutter={[spacing('XL'), spacing('XL')]}>
              <Col xs={24} md={16}>
                <Card
                  title={<Text strong style={styles.heading5}>{t('description')}</Text>}
                  styles={{
                    body: {
                      maxHeight: 'calc(90vh - 420px)',
                      overflow: 'auto',
                      padding: spacing('MD')
                    }
                  }}
                  style={{
                    borderRadius: borderRadius('LG'),
                    boxShadow: DESIGN_TOKENS.SHADOWS.CARD
                  }}
                >
                  <div style={{ ...styles.body, lineHeight: DESIGN_TOKENS.LINE_HEIGHT.RELAXED }}>
                    <ReactMarkdown>{template.readme}</ReactMarkdown>
                  </div>
                </Card>
              </Col>
              <Col xs={24} md={8}>
                <Card
                  title={<Text strong style={styles.heading5}>{t('features')}</Text>}
                  styles={{
                    body: {
                      maxHeight: 'calc(90vh - 420px)',
                      overflow: 'auto',
                      padding: spacing('MD')
                    }
                  }}
                  style={{
                    borderRadius: borderRadius('LG'),
                    boxShadow: DESIGN_TOKENS.SHADOWS.CARD
                  }}
                >
                  <Space direction="vertical" size={spacing('SM')}>
                    {template.tags?.map(tag => (
                      <Space key={tag} size={spacing('SM')}>
                        <CheckCircleOutlined style={{ color: 'var(--color-success)', fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD }} />
                        <Text style={styles.body}>{tag}</Text>
                      </Space>
                    ))}
                  </Space>
                </Card>
              </Col>
            </Row>
          </div>
        </TabPane>

        <TabPane 
          tab={
            <span style={styles.flexCenter}>
              <CodeOutlined style={{ marginRight: spacing('XS') }} /> 
              {t('files')}
            </span>
          } 
          key="files"
          disabled={loading || !templateDetails}
          data-testid="marketplace-preview-tab-files"
        >
          {loading ? (
            <div style={{ ...styles.flexCenter, padding: spacing('XXXL') }}>
              <Spin size="large" />
              <div style={{ marginTop: 16, color: 'var(--ant-color-text-secondary)' }}>
                {t('loadingFiles')}
              </div>
            </div>
          ) : templateDetails && templateDetails.files.length > 0 ? (
            <Row gutter={spacing('MD')} style={{ height: 'calc(90vh - 340px)' }}>
              <Col span={8} style={{ height: '100%' }}>
                <Card 
                  title={
                    <Space size={spacing('XS')}>
                      <FileOutlined style={styles.icon.medium} />
                      <Text strong style={styles.heading6}>{t('fileList')}</Text>
                    </Space>
                  }
                  styles={{ body: { padding: 0, height: 'calc(100% - 38px)' } }}
                  style={{ 
                    height: '100%', 
                    display: 'flex', 
                    flexDirection: 'column',
                    borderRadius: borderRadius('LG'),
                    boxShadow: DESIGN_TOKENS.SHADOWS.CARD
                  }}
                >
                  <List
                    dataSource={templateDetails.files}
                    renderItem={(file, index) => (
                      <List.Item
                        style={{ 
                          padding: spacing('SM'), 
                          cursor: 'pointer',
                          backgroundColor: selectedFileIndex === index ? 'rgba(85, 107, 47, 0.1)' : 'transparent',
                          borderLeft: selectedFileIndex === index ? '3px solid var(--color-primary)' : '3px solid transparent',
                          transition: DESIGN_TOKENS.TRANSITIONS.DEFAULT,
                          minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
                          display: 'flex',
                          alignItems: 'center'
                        }}
                        onClick={() => setSelectedFileIndex(index)}
                        data-testid={`marketplace-preview-file-item-${index}`}
                      >
                        <Space size={spacing('SM')}>
                          <CodeOutlined style={styles.icon.medium} />
                          <Text 
                            code 
                            style={{ 
                              fontWeight: selectedFileIndex === index ? DESIGN_TOKENS.FONT_WEIGHT.MEDIUM : DESIGN_TOKENS.FONT_WEIGHT.NORMAL,
                              color: selectedFileIndex === index ? 'var(--color-primary)' : 'var(--color-text-primary)',
                              fontSize: DESIGN_TOKENS.FONT_SIZE.SM
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
                  title={
                    <Space size={spacing('SM')}>
                      <CodeOutlined style={styles.icon.medium} />
                      <Text code style={styles.body}>{templateDetails.files[selectedFileIndex]?.path || templateDetails.files[selectedFileIndex]?.name}</Text>
                    </Space>
                  }
                  style={{ 
                    height: '100%', 
                    display: 'flex', 
                    flexDirection: 'column',
                    borderRadius: borderRadius('LG'),
                    boxShadow: DESIGN_TOKENS.SHADOWS.CARD
                  }}
                  styles={{ body: { flex: 1, overflow: 'auto', padding: spacing('MD') } }}
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
              style={{
                borderRadius: borderRadius('LG'),
                padding: spacing('MD')
              }}
            />
          )}
        </TabPane>

        <TabPane 
          tab={
            <span style={styles.flexCenter}>
              <SafetyOutlined style={{ marginRight: spacing('XS') }} /> 
              {t('security')}
            </span>
          } 
          key="security" 
          data-testid="marketplace-preview-tab-security"
        >
          <div style={{ height: 'calc(90vh - 340px)', overflow: 'auto' }}>
            <Card
              style={{
                borderRadius: borderRadius('LG'),
                boxShadow: DESIGN_TOKENS.SHADOWS.CARD
              }}
              styles={{ body: { padding: spacing('MD') } }}
            >
              <Space direction="vertical" size={spacing('LG')} style={{ width: '100%' }}>
                <Alert
                  message={<Text strong style={styles.body}>{t('securityReview')}</Text>}
                  description={<Text style={styles.body}>{t('securityReviewDesc')}</Text>}
                  type="info"
                  showIcon
                  style={{
                    borderRadius: borderRadius('LG'),
                    padding: spacing('MD')
                  }}
                />
                
                <Title level={5} style={styles.heading5}>{t('bestPractices')}</Title>
                <ul style={{ marginLeft: spacing('MD') }}>
                  <li style={{ ...styles.body, marginBottom: spacing('XS'), lineHeight: DESIGN_TOKENS.LINE_HEIGHT.RELAXED }}>{t('securityTip1')}</li>
                  <li style={{ ...styles.body, marginBottom: spacing('XS'), lineHeight: DESIGN_TOKENS.LINE_HEIGHT.RELAXED }}>{t('securityTip2')}</li>
                  <li style={{ ...styles.body, marginBottom: spacing('XS'), lineHeight: DESIGN_TOKENS.LINE_HEIGHT.RELAXED }}>{t('securityTip3')}</li>
                  <li style={{ ...styles.body, marginBottom: spacing('XS'), lineHeight: DESIGN_TOKENS.LINE_HEIGHT.RELAXED }}>{t('securityTip4')}</li>
                </ul>

                <Divider style={{ margin: `${spacing('LG')}px 0` }} />
                
                <Title level={5} style={styles.heading5}>{t('containerSecurity')}</Title>
                <Paragraph style={{ ...styles.body, lineHeight: DESIGN_TOKENS.LINE_HEIGHT.RELAXED }}>
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