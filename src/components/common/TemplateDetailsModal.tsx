import React, { useState, useEffect } from 'react'
import { Modal, Tabs, Typography, List, Card, Space, Spin, Empty, Tag, Button, Collapse, message } from 'antd'
import { 
  FileTextOutlined, 
  CodeOutlined, 
  FolderOutlined,
  CheckCircleOutlined 
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'

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
      console.error('Error fetching template details:', err)
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
        <div style={{ padding: '16px', lineHeight: 1.6 }}>
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
              return <li key={idx} style={{ marginLeft: 20 }}>{line.substring(2)}</li>
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
              <Paragraph key={idx} style={{ marginBottom: 8 }}>
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
            padding: '16px',
            backgroundColor: '#f5f5f5',
            overflow: 'auto',
            fontSize: '13px',
            lineHeight: 1.5,
            fontFamily: 'Consolas, Monaco, "Andale Mono", "Ubuntu Mono", monospace'
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
      title={
        <Space>
          <Text strong>{t('resources:templates.templateDetails')}</Text>
          {templateName && (
            <Tag color="blue">{templateName.replace(/^(db_|kick_|route_)/, '')}</Tag>
          )}
        </Space>
      }
      open={visible}
      onCancel={onClose}
      width={800}
      footer={[
        <Button key="cancel" onClick={onClose}>
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
          >
            {t('resources:templates.useTemplate')}
          </Button>
        )
      ]}
    >
      {loading && (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin tip={t('resources:templates.loadingDetails')} />
        </div>
      )}

      {error && (
        <Empty description={error} />
      )}

      {!loading && !error && templateData && (
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'readme',
              label: (
                <Space>
                  <FileTextOutlined />
                  {t('resources:templates.overview')}
                </Space>
              ),
              children: readmeFile ? (
                <Card 
                  size="small" 
                  style={{ maxHeight: '500px', overflow: 'auto' }}
                  bodyStyle={{ padding: 0 }}
                >
                  {renderFileContent(readmeFile)}
                </Card>
              ) : (
                <Empty description={t('resources:templates.noReadme')} />
              )
            },
            {
              key: 'files',
              label: (
                <Space>
                  <FolderOutlined />
                  {t('resources:templates.files')} ({otherFiles.length})
                </Space>
              ),
              children: (
                <div style={{ maxHeight: '500px', overflow: 'auto' }}>
                  {Object.keys(groupedFiles).length === 1 && groupedFiles['root'] ? (
                    // If all files are in root, show them directly
                    <Collapse defaultActiveKey={groupedFiles['root'].map((_, idx) => idx.toString())}>
                      {groupedFiles['root'].map((file, idx) => (
                        <Panel
                          key={idx}
                          header={
                            <Space>
                              {getFileIcon(file.name)}
                              <Text code>{file.name}</Text>
                              <Tag color="blue" style={{ marginLeft: 'auto' }}>
                                {getFileLanguage(file.name)}
                              </Tag>
                            </Space>
                          }
                        >
                          <div style={{ maxHeight: '400px', overflow: 'auto' }}>
                            {renderFileContent(file)}
                          </div>
                        </Panel>
                      ))}
                    </Collapse>
                  ) : (
                    // If files are in directories, group them
                    <Collapse defaultActiveKey={['root']}>
                      {Object.entries(groupedFiles).map(([dir, files]) => (
                        <Panel
                          key={dir}
                          header={
                            <Space>
                              <FolderOutlined />
                              <Text strong>{dir === 'root' ? t('resources:templates.rootFiles') : dir}</Text>
                              <Tag>{files.length} {t('resources:templates.filesCount')}</Tag>
                            </Space>
                          }
                        >
                          <Collapse>
                            {files.map((file, idx) => (
                              <Panel
                                key={`${dir}-${idx}`}
                                header={
                                  <Space>
                                    {getFileIcon(file.name)}
                                    <Text code>{file.name}</Text>
                                    <Tag color="blue">
                                      {getFileLanguage(file.name)}
                                    </Tag>
                                  </Space>
                                }
                              >
                                <div style={{ maxHeight: '400px', overflow: 'auto' }}>
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