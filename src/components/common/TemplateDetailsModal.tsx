import React, { useState, useEffect } from 'react'
import { Modal, Tabs, Typography, List, Card, Space, Spin, Empty, Tag, Button, Collapse, message } from 'antd'
import { 
  FileTextOutlined, 
  CodeOutlined, 
  FolderOutlined,
  CheckCircleOutlined 
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { ModalSize } from '@/types/modal'

const { Text, Title, Paragraph } = Typography
const { Panel } = Collapse

interface TemplateFile {
  name: string
  path: string
  content: string
}

interface TemplateDetails {
  template_name: string
  files: TemplateFile[]
}

interface TemplateDetailsModalProps {
  visible: boolean
  templateName: string | null
  onClose: () => void
  onUseTemplate?: (templateName: string) => void
}

const TemplateDetailsModal: React.FC<TemplateDetailsModalProps> = ({
  visible,
  templateName,
  onClose,
  onUseTemplate
}) => {
  const { t } = useTranslation(['resources', 'common'])
  const [templateData, setTemplateData] = useState<TemplateDetails | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('readme')

  useEffect(() => {
    if (visible && templateName) {
      fetchTemplateDetails()
    }
  }, [visible, templateName])

  const fetchTemplateDetails = async () => {
    if (!templateName) return

    try {
      setLoading(true)
      setError(null)
      
      const response = await fetch(`${window.location.origin}/config/template_${templateName}.json`)
      if (!response.ok) {
        throw new Error('Failed to fetch template details')
      }
      
      const data = await response.json()
      setTemplateData(data)
    } catch (err) {
      setError('Failed to load template details')
      message.error('Failed to load template details')
    } finally {
      setLoading(false)
    }
  }

  const getFileIcon = (fileName: string) => {
    const lowerName = fileName.toLowerCase()
    if (lowerName === 'readme.md') return <FileTextOutlined />
    if (lowerName.includes('.sh') || lowerName.includes('file')) return <CodeOutlined />
    if (lowerName.includes('.yaml') || lowerName.includes('.yml')) return <CodeOutlined />
    if (lowerName.includes('.json')) return <CodeOutlined />
    if (fileName.includes('/')) return <FolderOutlined />
    return <FileTextOutlined />
  }

  const getFileLanguage = (fileName: string): string => {
    const lowerName = fileName.toLowerCase()
    if (lowerName.endsWith('.sh') || lowerName === 'rediaccfile') return 'bash'
    if (lowerName.endsWith('.yaml') || lowerName.endsWith('.yml')) return 'yaml'
    if (lowerName.endsWith('.json')) return 'json'
    if (lowerName.endsWith('.py')) return 'python'
    if (lowerName.endsWith('.js')) return 'javascript'
    if (lowerName.endsWith('.ts') || lowerName.endsWith('.tsx')) return 'typescript'
    if (lowerName.endsWith('.md')) return 'markdown'
    if (lowerName === 'dockerfile') return 'dockerfile'
    return 'text'
  }

  const renderFileContent = (file: TemplateFile) => {
    const language = getFileLanguage(file.name)
    
    if (file.name.toLowerCase() === 'readme.md') {
      // Simple markdown rendering for README
      const lines = file.content.split('\n')
      return (
        <div style={{ padding: 'var(--space-md)', lineHeight: 1.6 }}>
          {lines.map((line, idx) => {
            // Basic markdown parsing
            if (line.startsWith('# ')) {
              return <Title key={idx} level={3}>{line.substring(2)}</Title>
            }
            if (line.startsWith('## ')) {
              return <Title key={idx} level={4}>{line.substring(3)}</Title>
            }
            if (line.startsWith('### ')) {
              return <Title key={idx} level={5}>{line.substring(4)}</Title>
            }
            if (line.startsWith('- ')) {
              return <li key={idx} style={{ marginLeft: 'var(--space-lg)' }}>{line.substring(2)}</li>
            }
            if (line.startsWith('```')) {
              return null // Skip code blocks for now
            }
            if (line.trim() === '') {
              return <br key={idx} />
            }
            // Handle inline code with backticks
            const codeRegex = /`([^`]+)`/g
            const parts = line.split(codeRegex)
            return (
              <Paragraph key={idx} style={{ marginBottom: 'var(--space-sm)' }}>
                {parts.map((part, i) => 
                  i % 2 === 1 ? <Text key={i} code>{part}</Text> : part
                )}
              </Paragraph>
            )
          })}
        </div>
      )
    }

    // For other files, show code in a pre block with syntax highlighting
    return (
      <div style={{ position: 'relative' }}>
        <Tag 
          color="blue" 
          style={{ 
            position: 'absolute', 
            top: 8, 
            right: 8, 
            zIndex: 1 
          }}
        >
          {language}
        </Tag>
        <pre
          style={{
            margin: 0,
            padding: 'var(--space-md)',
            backgroundColor: 'var(--color-bg-tertiary)',
            overflow: 'auto',
            fontSize: '13px',
            lineHeight: 1.5,
            fontFamily: 'Consolas, Monaco, "Andale Mono", "Ubuntu Mono", monospace',
            borderRadius: '6px',
            border: '1px solid var(--color-border-secondary)',
            color: 'var(--color-text-primary)'
          }}
        >
          <code>{file.content}</code>
        </pre>
      </div>
    )
  }

  const readmeFile = templateData?.files.find(f => f.name.toLowerCase() === 'readme.md')
  const otherFiles = templateData?.files.filter(f => f.name.toLowerCase() !== 'readme.md') || []

  // Group files by directory
  const groupedFiles = otherFiles.reduce((acc, file) => {
    const dir = file.path.includes('/') ? file.path.split('/')[0] : 'root'
    if (!acc[dir]) acc[dir] = []
    acc[dir].push(file)
    return acc
  }, {} as Record<string, TemplateFile[]>)

  return (
    <Modal
      data-testid="template-details-modal"
      title={
        <Space>
          <Text strong>{t('resources:templates.templateDetails')}</Text>
          {templateName && (
            <Tag color="blue" data-testid="template-details-name-tag">{templateName.replace(/^(db_|kick_|route_)/, '')}</Tag>
          )}
        </Space>
      }
      open={visible}
      onCancel={onClose}
      className={ModalSize.Large}
      footer={[
        <Button key="cancel" onClick={onClose} data-testid="template-details-close-button">
          {t('common:actions.close')}
        </Button>,
        onUseTemplate && (
          <Button 
            key="use" 
            type="primary" 
            icon={<CheckCircleOutlined />}
            onClick={() => {
              onUseTemplate(templateName!)
              onClose()
            }}
            data-testid="template-details-select-button"
          >
            {t('resources:templates.useTemplate')}
          </Button>
        )
      ]}
    >
      {loading && (
        <div style={{ textAlign: 'center', padding: 'var(--space-5xl) 0' }} data-testid="template-details-loading">
          <Spin tip={t('resources:templates.loadingDetails')} />
        </div>
      )}

      {error && (
        <Empty description={error} data-testid="template-details-error" />
      )}

      {!loading && !error && templateData && (
        <Tabs
          data-testid="template-details-tabs"
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'readme',
              label: (
                <Space data-testid="template-details-tab-overview">
                  <FileTextOutlined />
                  {t('resources:templates.overview')}
                </Space>
              ),
              children: readmeFile ? (
                <Card 
                  size="small" 
                  style={{ 
                    maxHeight: '500px', 
                    overflow: 'auto',
                    border: '1px solid var(--color-border-secondary)',
                    borderRadius: '8px',
                    boxShadow: 'var(--shadow-sm)'
                  }}
                  bodyStyle={{ padding: 0 }}
                  data-testid="template-details-readme-content"
                >
                  {renderFileContent(readmeFile)}
                </Card>
              ) : (
                <Empty description={t('resources:templates.noReadme')} data-testid="template-details-readme-empty" />
              )
            },
            {
              key: 'files',
              label: (
                <Space data-testid="template-details-tab-files">
                  <FolderOutlined />
                  {t('resources:templates.files')} ({otherFiles.length})
                </Space>
              ),
              children: (
                <div style={{ 
                  maxHeight: '500px', 
                  overflow: 'auto',
                  padding: 'var(--space-sm)',
                  backgroundColor: 'var(--color-bg-secondary)',
                  borderRadius: '8px',
                  border: '1px solid var(--color-border-secondary)'
                }} data-testid="template-details-files-content">
                  {Object.keys(groupedFiles).length === 1 && groupedFiles['root'] ? (
                    // If all files are in root, show them directly
                    <Collapse defaultActiveKey={groupedFiles['root'].map((_, idx) => idx.toString())} data-testid="template-details-files-collapse">
                      {groupedFiles['root'].map((file, idx) => (
                        <Panel
                          key={idx}
                          header={
                            <Space data-testid={`template-details-file-header-${idx}`}>
                              {getFileIcon(file.name)}
                              <Text code>{file.name}</Text>
                              <Tag color="blue" style={{ marginLeft: 'auto' }}>
                                {getFileLanguage(file.name)}
                              </Tag>
                            </Space>
                          }
                          data-testid={`template-details-file-panel-${idx}`}
                        >
                          <div style={{ 
                            maxHeight: '400px', 
                            overflow: 'auto',
                            padding: 'var(--space-xs)',
                            backgroundColor: 'var(--color-bg-primary)',
                            borderRadius: '6px',
                            border: '1px solid var(--color-border-primary)'
                          }} data-testid={`template-details-file-content-${idx}`}>
                            {renderFileContent(file)}
                          </div>
                        </Panel>
                      ))}
                    </Collapse>
                  ) : (
                    // If files are in directories, group them
                    <Collapse defaultActiveKey={['root']} data-testid="template-details-folders-collapse">
                      {Object.entries(groupedFiles).map(([dir, files]) => (
                        <Panel
                          key={dir}
                          header={
                            <Space data-testid={`template-details-folder-header-${dir}`}>
                              <FolderOutlined />
                              <Text strong>{dir === 'root' ? t('resources:templates.rootFiles') : dir}</Text>
                              <Tag>{files.length} {t('resources:templates.filesCount')}</Tag>
                            </Space>
                          }
                          data-testid={`template-details-folder-panel-${dir}`}
                        >
                          <Collapse data-testid={`template-details-folder-files-collapse-${dir}`}>
                            {files.map((file, idx) => (
                              <Panel
                                key={`${dir}-${idx}`}
                                header={
                                  <Space data-testid={`template-details-folder-file-header-${dir}-${idx}`}>
                                    {getFileIcon(file.name)}
                                    <Text code>{file.name}</Text>
                                    <Tag color="blue">
                                      {getFileLanguage(file.name)}
                                    </Tag>
                                  </Space>
                                }
                                data-testid={`template-details-folder-file-panel-${dir}-${idx}`}
                              >
                                <div style={{ 
                                  maxHeight: '400px', 
                                  overflow: 'auto',
                                  padding: 'var(--space-xs)',
                                  backgroundColor: 'var(--color-bg-primary)',
                                  borderRadius: '6px',
                                  border: '1px solid var(--color-border-primary)'
                                }} data-testid={`template-details-folder-file-content-${dir}-${idx}`}>
                                  {renderFileContent(file)}
                                </div>
                              </Panel>
                            ))}
                          </Collapse>
                        </Panel>
                      ))}
                    </Collapse>
                  )}
                </div>
              )
            }
          ]}
        />
      )}
    </Modal>
  )
}

export default TemplateDetailsModal