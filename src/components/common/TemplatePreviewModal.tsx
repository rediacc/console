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
import { configService } from '@/services/configService'

const { Title, Text, Paragraph } = Typography

interface TemplateFile {
  name: string
  path: string
  content: string
}

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
  files: TemplateFile[]
}

interface TemplatePreviewModalProps {
  visible: boolean
  template: Template | null
  templateName?: string | null // For backward compatibility with TemplateDetailsModal
  onClose: () => void
  onUseTemplate: (template: Template | string) => void
  context?: 'marketplace' | 'repository-creation'
}

const TemplatePreviewModal: React.FC<TemplatePreviewModalProps> = ({
  visible,
  template,
  templateName,
  onClose,
  onUseTemplate,
  context = 'marketplace'
}) => {
  const { t } = useTranslation(['marketplace', 'resources', 'common'])
  const styles = useComponentStyles()
  const [loading, setLoading] = useState(false)
  const [templateDetails, setTemplateDetails] = useState<TemplateDetails | null>(null)
  const [activeTab, setActiveTab] = useState('overview')
  const [selectedFileIndex, setSelectedFileIndex] = useState(0)
  const [loadedTemplate, setLoadedTemplate] = useState<Template | null>(null)

  // Support both template object and templateName for backward compatibility
  const effectiveTemplate = loadedTemplate || template || (templateName ? { name: templateName, readme: '' } : null)

  useEffect(() => {
    if (!visible) {
      // Reset state when modal is closed
      setTemplateDetails(null)
      setLoadedTemplate(null)
      setLoading(false)
      setActiveTab('overview')
      setSelectedFileIndex(0)
      return
    }

    const fetchTemplateDetails = async () => {
      const baseTemplate = template || (templateName ? { name: templateName, readme: '' } : null)
      if (!baseTemplate) return

      try {
        setLoading(true)

        // For repository creation context, fetch the template from templates.json to get README
        if (context === 'repository-creation' && templateName && !baseTemplate.readme) {
          try {
            const templatesUrl = await configService.getTemplatesUrl()
            const templatesResponse = await fetch(templatesUrl)
            if (templatesResponse.ok) {
              const templatesData = await templatesResponse.json()
              const foundTemplate = templatesData.templates?.find((t: any) => t.name === templateName)
              if (foundTemplate) {
                // Set the loaded template with README content
                setLoadedTemplate({
                  name: foundTemplate.name,
                  readme: foundTemplate.readme,
                  category: foundTemplate.category,
                  tags: foundTemplate.tags,
                  difficulty: foundTemplate.difficulty,
                  iconUrl: foundTemplate.iconUrl
                })
              }
            }
          } catch (templatesError) {
            console.error('Failed to fetch templates.json:', templatesError)
          }
        }

        // Fetch the detailed template data (files, etc.)
        const response = await fetch(`${window.location.origin}/config/template_${baseTemplate.name}.json`)
        if (response.ok) {
          const data = await response.json()
          setTemplateDetails(data)
        }
      } catch (error) {
        // Failed to fetch template details
        console.error('Failed to fetch template details:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchTemplateDetails()
    setActiveTab('overview')
    setSelectedFileIndex(0)
  }, [visible, template?.name, templateName, context])

  if (!effectiveTemplate) return null

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

  const renderFileContent = (file: TemplateFile) => {
    const language = file.name.endsWith('.yaml') || file.name.endsWith('.yml') ? 'yaml' :
                    file.name.endsWith('.json') ? 'json' :
                    file.name.endsWith('.sh') ? 'bash' :
                    file.name.endsWith('.env') ? 'bash' :
                    file.name.endsWith('.md') ? 'markdown' : 'text'

    if (language === 'markdown') {
      return (
        <ReactMarkdown
          components={{
            code(props) {
              const { node, inline, className, children, ...rest } = props
              const match = /language-(\w+)/.exec(className || '')
              return !inline && match ? (
                <SyntaxHighlighter
                  style={vscDarkPlus as any}
                  language={match[1]}
                  PreTag="div"
                  {...rest}
                >
                  {String(children).replace(/\n$/, '')}
                </SyntaxHighlighter>
              ) : (
                <code className={className} {...rest}>
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
      <SyntaxHighlighter language={language} style={vscDarkPlus as any}>
        {file.content}
      </SyntaxHighlighter>
    )
  }

  const getActionButtonText = () => {
    if (context === 'marketplace') {
      return t('marketplace:deployNow')
    }
    return t('resources:templates.useTemplate')
  }

  const getActionButtonIcon = () => {
    if (context === 'marketplace') {
      return <RocketOutlined />
    }
    return <CheckCircleOutlined />
  }

  const handleAction = () => {
    if (context === 'marketplace') {
      onUseTemplate(effectiveTemplate)
    } else {
      // For repository creation, pass the template name
      onUseTemplate(effectiveTemplate.name)
    }
    onClose()
  }

  const modalTitle = context === 'marketplace' ?
    getTemplateTitle(effectiveTemplate.name) :
    t('resources:templates.templateDetails')

  return (
    <Modal
      data-testid={context === 'marketplace' ? "marketplace-preview-modal" : "template-details-modal"}
      title={
        <Space size={spacing('MD')}>
          {effectiveTemplate.iconUrl ? (
            <img
              src={effectiveTemplate.iconUrl}
              alt={effectiveTemplate.name}
              style={{
                width: DESIGN_TOKENS.DIMENSIONS.ICON_XXL,
                height: DESIGN_TOKENS.DIMENSIONS.ICON_XXL,
                objectFit: 'contain',
                filter: 'drop-shadow(0px 2px 4px rgba(0,0,0,0.1))'
              }}
              onError={(e) => {
                e.currentTarget.style.display = 'none'
                e.currentTarget.parentElement?.appendChild(
                  <span>{getTemplateIcon(effectiveTemplate.name)}</span> as any
                )
              }}
            />
          ) : (
            getTemplateIcon(effectiveTemplate.name)
          )}
          <div>
            <Title level={4} style={{ ...styles.heading4, margin: 0 }}>
              {modalTitle}
            </Title>
            {context === 'repository-creation' && (
              <Tag color="blue" data-testid="template-details-name-tag">
                {effectiveTemplate.name.replace(/^(db_|kick_|route_)/, '')}
              </Tag>
            )}
            {context === 'marketplace' && effectiveTemplate.difficulty && (
              <Tag
                color={getDifficultyColor(effectiveTemplate.difficulty)}
                style={{
                  borderRadius: borderRadius('SM'),
                  fontSize: DESIGN_TOKENS.FONT_SIZE.SM,
                  marginTop: spacing('XS')
                }}
              >
                {t(`difficulty${effectiveTemplate.difficulty?.charAt(0).toUpperCase()}${effectiveTemplate.difficulty?.slice(1)}`)}
              </Tag>
            )}
          </div>
        </Space>
      }
      open={visible}
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
          data-testid={context === 'marketplace' ? "marketplace-preview-close-button" : "template-details-close-button"}
          style={{
            ...styles.buttonSecondary,
            marginRight: spacing('SM')
          }}
        >
          {t('common:actions.close')}
        </Button>,
        <Button
          key="action"
          type="primary"
          icon={getActionButtonIcon()}
          onClick={handleAction}
          data-testid={context === 'marketplace' ? "marketplace-preview-deploy-button" : "template-details-select-button"}
          style={styles.buttonPrimary}
        >
          {getActionButtonText()}
        </Button>
      ]}
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        data-testid={context === 'marketplace' ? "marketplace-preview-tabs" : "template-details-tabs"}
        size="large"
        items={[
          {
            key: 'overview',
            label: (
              <span style={styles.flexCenter}>
                <FileTextOutlined style={{ marginRight: spacing('XS') }} />
                {context === 'marketplace' ? t('marketplace:overview') : t('resources:templates.overview')}
              </span>
            ),
            children: (
              <div style={{ height: 'calc(90vh - 340px)', overflow: 'auto' }}>
                <Row gutter={[spacing('XL'), spacing('XL')]}>
                  <Col xs={24} md={context === 'marketplace' ? 16 : 24}>
                    <Card
                      title={<Text strong style={styles.heading5}>
                        {context === 'marketplace' ? t('marketplace:description') : t('resources:templates.overview')}
                      </Text>}
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
                      data-testid={context === 'marketplace' ? undefined : "template-details-readme-content"}
                    >
                      <div style={{ ...styles.body, lineHeight: DESIGN_TOKENS.LINE_HEIGHT.RELAXED }}>
                        <ReactMarkdown>
                          {templateDetails?.readme || effectiveTemplate.readme}
                        </ReactMarkdown>
                      </div>
                    </Card>
                  </Col>
                  {context === 'marketplace' && (
                    <Col xs={24} md={8}>
                      <Card
                        title={<Text strong style={styles.heading5}>{t('marketplace:features')}</Text>}
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
                          {effectiveTemplate.tags?.map(tag => (
                            <Space key={tag} size={spacing('SM')}>
                              <CheckCircleOutlined style={{ color: 'var(--color-success)', fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD }} />
                              <Text style={styles.body}>{tag}</Text>
                            </Space>
                          ))}
                        </Space>
                      </Card>
                    </Col>
                  )}
                </Row>
              </div>
            )
          },
          {
            key: 'files',
            label: (
              <span style={styles.flexCenter}>
                <CodeOutlined style={{ marginRight: spacing('XS') }} />
                {context === 'marketplace' ? t('marketplace:files') : t('resources:templates.files')}
                {templateDetails?.files && ` (${templateDetails.files.length})`}
              </span>
            ),
            disabled: loading || !templateDetails,
            children: loading ? (
              <div style={{ ...styles.flexCenter, padding: spacing('XXXL') }} data-testid={context === 'marketplace' ? undefined : "template-details-loading"}>
                <Spin size="large" />
                <div style={{ marginTop: 16, color: 'var(--ant-color-text-secondary)' }}>
                  {context === 'marketplace' ? t('marketplace:loadingFiles') : t('resources:templates.loadingDetails')}
                </div>
              </div>
            ) : templateDetails && templateDetails.files.length > 0 ? (
              <Row gutter={spacing('MD')} style={{ height: 'calc(90vh - 340px)' }}>
                <Col span={8} style={{ height: '100%' }}>
                  <Card
                    title={
                      <Space size={spacing('XS')}>
                        <FileOutlined style={styles.icon.medium} />
                        <Text strong style={styles.heading6}>
                          {context === 'marketplace' ? t('marketplace:fileList') : t('resources:templates.files')}
                        </Text>
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
                    data-testid={context === 'marketplace' ? undefined : "template-details-files-content"}
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
                          data-testid={context === 'marketplace' ? `marketplace-preview-file-item-${index}` : `template-details-file-header-${index}`}
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
                    data-testid={context === 'marketplace' ? undefined : `template-details-file-content-${selectedFileIndex}`}
                  >
                    {templateDetails.files[selectedFileIndex] && renderFileContent(templateDetails.files[selectedFileIndex])}
                  </Card>
                </Col>
              </Row>
            ) : (
              <Alert
                message={context === 'marketplace' ? t('marketplace:noFiles') : t('resources:templates.noReadme')}
                description={context === 'marketplace' ? t('marketplace:noFilesDesc') : undefined}
                type="info"
                showIcon
                style={{
                  borderRadius: borderRadius('LG'),
                  padding: spacing('MD')
                }}
                data-testid={context === 'marketplace' ? undefined : "template-details-readme-empty"}
              />
            )
          },
          {
            key: 'security',
            label: (
              <span style={styles.flexCenter}>
                <SafetyOutlined style={{ marginRight: spacing('XS') }} />
                {context === 'marketplace' ? t('marketplace:security') : 'Security'}
              </span>
            ),
            children: (
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
                      message={<Text strong style={styles.body}>
                        {context === 'marketplace' ? t('marketplace:securityReview') : 'Security Review'}
                      </Text>}
                      description={<Text style={styles.body}>
                        {context === 'marketplace' ? t('marketplace:securityReviewDesc') :
                         'Please review the template files for security considerations before deployment.'}
                      </Text>}
                      type="info"
                      showIcon
                      style={{
                        borderRadius: borderRadius('LG'),
                        padding: spacing('MD')
                      }}
                    />

                    <Title level={5} style={styles.heading5}>
                      {context === 'marketplace' ? t('marketplace:bestPractices') : 'Best Practices'}
                    </Title>
                    <ul style={{ marginLeft: spacing('MD') }}>
                      <li style={{ ...styles.body, marginBottom: spacing('XS'), lineHeight: DESIGN_TOKENS.LINE_HEIGHT.RELAXED }}>
                        Review all configuration files before deployment
                      </li>
                      <li style={{ ...styles.body, marginBottom: spacing('XS'), lineHeight: DESIGN_TOKENS.LINE_HEIGHT.RELAXED }}>
                        Update default passwords and credentials
                      </li>
                      <li style={{ ...styles.body, marginBottom: spacing('XS'), lineHeight: DESIGN_TOKENS.LINE_HEIGHT.RELAXED }}>
                        Ensure proper network security configuration
                      </li>
                      <li style={{ ...styles.body, marginBottom: spacing('XS'), lineHeight: DESIGN_TOKENS.LINE_HEIGHT.RELAXED }}>
                        Keep software components up to date
                      </li>
                    </ul>

                    <Divider style={{ margin: `${spacing('LG')}px 0` }} />

                    <Title level={5} style={styles.heading5}>Container Security</Title>
                    <Paragraph style={{ ...styles.body, lineHeight: DESIGN_TOKENS.LINE_HEIGHT.RELAXED }}>
                      Always review container configurations and ensure they follow security best practices for your deployment environment.
                    </Paragraph>
                  </Space>
                </Card>
              </div>
            )
          }
        ]}
      />
    </Modal>
  )
}

export default TemplatePreviewModal