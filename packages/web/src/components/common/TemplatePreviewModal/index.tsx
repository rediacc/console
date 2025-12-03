import React, { useState, useEffect } from 'react'
import type { ComponentPropsWithoutRef } from 'react'
import { Tag, Row, Col, List } from 'antd'
import { ModalSize } from '@/types/modal'
import {
  RocketOutlined,
  FileTextOutlined,
  CodeOutlined,
  SafetyOutlined,
  AppstoreOutlined,
  CheckCircleOutlined,
  FileOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import type { Components as MarkdownComponents } from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import type { SyntaxHighlighterProps } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { templateService } from '@/services/templateService'
import LoadingWrapper from '@/components/common/LoadingWrapper'
import { TabLabel } from '@/styles/primitives'
import {
  StyledModal,
  TitleStack,
  TemplateAvatar,
  TemplateIconWrapper,
  TemplateHeading,
  DifficultyTag,
  StyledTabs,
  OverviewScroll,
  DescriptionCard,
  FeatureCard,
  CardTitle,
  MarkdownContent,
  FeatureList,
  FeatureItem,
  FeatureText,
  LoadingContainer,
  LoadingText,
  FilesLayout,
  FileListColumn,
  FilePreviewColumn,
  FileListCard,
  FileListItem,
  FileMeta,
  FileName,
  FilePreviewCard,
  FilePreviewHeader,
  FilePath,
  FilePreviewBody,
  SecurityScroll,
  SecurityCard,
  AlertStack,
  RoundedAlert,
  Checklist,
  ChecklistItem,
  BodyParagraph,
  BodyText,
  SectionDivider,
  SecurityTitle,
  PrimaryActionButton,
  SecondaryActionButton,
  IconLabel,
  SuccessIcon,
} from './styles'

interface TemplateFile {
  name: string
  path: string
  content: string
}

interface Template {
  id?: string
  name: string
  readme: string
  category?: string
  tags?: string[]
  difficulty?: 'beginner' | 'intermediate' | 'advanced'
  iconUrl?: string
  download_url?: string
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
  context?: 'marketplace' | 'repo-creation'
}

type CodeRendererProps = ComponentPropsWithoutRef<'code'> & {
  inline?: boolean
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
  const [loading, setLoading] = useState(false)
  const [templateDetails, setTemplateDetails] = useState<TemplateDetails | null>(null)
  const [activeTab, setActiveTab] = useState('overview')
  const [selectedFileIndex, setSelectedFileIndex] = useState(0)
  const [loadedTemplate, setLoadedTemplate] = useState<Template | null>(null)
  const [iconFailed, setIconFailed] = useState(false)

  const codeTheme = vscDarkPlus as SyntaxHighlighterProps['style']

  const markdownComponents: MarkdownComponents = {
    code({ inline, className, children }: CodeRendererProps) {
      const match = /language-(\w+)/.exec(className ?? '')

      if (!inline && match) {
        return (
          <SyntaxHighlighter
            style={codeTheme}
            language={match[1]}
            PreTag="div"
          >
            {String(children).replace(/\n$/, '')}
          </SyntaxHighlighter>
        )
      }

      return (
        <code className={className}>
          {children}
        </code>
      )
    },
  }

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
      let baseTemplate = template || (templateName ? { name: templateName, readme: '' } : null)
      if (!baseTemplate) return

      try {
        setLoading(true)

        // For repo creation context, fetch the template from templates.json to get README
        if (context === 'repo-creation' && templateName && !baseTemplate.readme) {
          try {
            const templates: Template[] = await templateService.fetchTemplates()
            const foundTemplate = templates.find((templateItem) => templateItem.name === templateName)
            if (foundTemplate) {
              // Set the loaded template with README content
              const fullTemplate = {
                id: foundTemplate.id,
                name: foundTemplate.name,
                readme: foundTemplate.readme,
                category: foundTemplate.category,
                tags: foundTemplate.tags,
                difficulty: foundTemplate.difficulty,
                download_url: foundTemplate.download_url
              }
              setLoadedTemplate(fullTemplate)
              baseTemplate = fullTemplate // Use the full template for fetching details
            }
          } catch (templatesError) {
            console.error('Failed to fetch templates:', templatesError)
          }
        }

        // Fetch the detailed template data (files, etc.)
        const data = await templateService.fetchTemplateData(baseTemplate)
        setTemplateDetails(data)
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
  }, [visible, template, templateName, context])

  useEffect(() => {
    setIconFailed(false)
  }, [effectiveTemplate?.iconUrl])

  if (!effectiveTemplate) return null

  // Use generic icon for all templates (backend provides proper names)
  const getTemplateIcon = () => (
    <TemplateIconWrapper>
      <AppstoreOutlined />
    </TemplateIconWrapper>
  )

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
        <ReactMarkdown components={markdownComponents}>
          {file.content}
        </ReactMarkdown>
      )
    }

    return (
      <SyntaxHighlighter language={language} style={codeTheme}>
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
      // For repo creation, pass the template name
      onUseTemplate(effectiveTemplate.name)
    }
    onClose()
  }

  const modalTitle =
    context === 'marketplace' ? effectiveTemplate.name : t('resources:templates.templateDetails')

  const overviewContent = (
    <OverviewScroll>
      <Row gutter={[24, 24]}>
        <Col xs={24} md={context === 'marketplace' ? 16 : 24}>
          <DescriptionCard
            title={
              <CardTitle>
                {context === 'marketplace' ? t('marketplace:description') : t('resources:templates.overview')}
              </CardTitle>
            }
            data-testid={context === 'marketplace' ? undefined : 'template-details-readme-content'}
          >
            <MarkdownContent>
              <ReactMarkdown>
                {templateDetails?.readme || effectiveTemplate.readme}
              </ReactMarkdown>
            </MarkdownContent>
          </DescriptionCard>
        </Col>
        {context === 'marketplace' && (
          <Col xs={24} md={8}>
            <FeatureCard
              title={<CardTitle>{t('marketplace:features')}</CardTitle>}
            >
              <FeatureList direction="vertical" size="small">
                {effectiveTemplate.tags?.map((tag) => (
                  <FeatureItem key={tag} size="small">
                    <SuccessIcon>
                      <CheckCircleOutlined />
                    </SuccessIcon>
                    <FeatureText>{tag}</FeatureText>
                  </FeatureItem>
                ))}
              </FeatureList>
            </FeatureCard>
          </Col>
        )}
      </Row>
    </OverviewScroll>
  )

  const filesContent = loading ? (
    <LoadingContainer data-testid={context === 'marketplace' ? undefined : 'template-details-loading'}>
      <LoadingWrapper loading centered minHeight={160}>
        <div />
      </LoadingWrapper>
      <LoadingText>
        {context === 'marketplace' ? t('marketplace:loadingFiles') : t('resources:templates.loadingDetails')}
      </LoadingText>
    </LoadingContainer>
  ) : templateDetails && templateDetails.files.length > 0 ? (
    <FilesLayout>
      <FileListColumn>
        <FileListCard
          title={
            <IconLabel>
              <FileOutlined />
              {context === 'marketplace' ? t('marketplace:fileList') : t('resources:templates.files')}
            </IconLabel>
          }
          data-testid={context === 'marketplace' ? undefined : 'template-details-files-content'}
        >
          <List
            dataSource={templateDetails.files}
            renderItem={(file, index) => (
              <FileListItem
                $active={selectedFileIndex === index}
                onClick={() => setSelectedFileIndex(index)}
                data-testid={
                  context === 'marketplace'
                    ? `marketplace-preview-file-item-${index}`
                    : `template-details-file-header-${index}`
                }
              >
                <FileMeta>
                  <IconLabel>
                    <CodeOutlined />
                    <FileName code>{file.path || file.name}</FileName>
                  </IconLabel>
                </FileMeta>
              </FileListItem>
            )}
            style={{ height: '100%' }}
          />
        </FileListCard>
      </FileListColumn>
      <FilePreviewColumn>
        <FilePreviewCard
          title={
            <FilePreviewHeader size="small">
              <IconLabel>
                <CodeOutlined />
                <FilePath code>
                  {templateDetails.files[selectedFileIndex]?.path ||
                    templateDetails.files[selectedFileIndex]?.name}
                </FilePath>
              </IconLabel>
            </FilePreviewHeader>
          }
          data-testid={
            context === 'marketplace' ? undefined : `template-details-file-content-${selectedFileIndex}`
          }
        >
          <FilePreviewBody>
            {templateDetails.files[selectedFileIndex] &&
              renderFileContent(templateDetails.files[selectedFileIndex])}
          </FilePreviewBody>
        </FilePreviewCard>
      </FilePreviewColumn>
    </FilesLayout>
  ) : (
    <RoundedAlert
      message={context === 'marketplace' ? t('marketplace:noFiles') : t('resources:templates.noReadme')}
      description={context === 'marketplace' ? t('marketplace:noFilesDesc') : undefined}
      type="info"
      showIcon
      data-testid={context === 'marketplace' ? undefined : 'template-details-readme-empty'}
    />
  )

  const securityContent = (
    <SecurityScroll>
      <SecurityCard>
        <AlertStack>
          <RoundedAlert
            message={
              <BodyText strong>
                {context === 'marketplace' ? t('marketplace:securityReview') : 'Security Review'}
              </BodyText>
            }
            description={
              <BodyText>
                {context === 'marketplace'
                  ? t('marketplace:securityReviewDesc')
                  : 'Please review the template files for security considerations before deployment.'}
              </BodyText>
            }
            type="info"
            showIcon
          />

          <SecurityTitle>
            {context === 'marketplace' ? t('marketplace:bestPractices') : 'Best Practices'}
          </SecurityTitle>
          <Checklist>
            <ChecklistItem>Review all configuration files before deployment</ChecklistItem>
            <ChecklistItem>Update default passwords and credentials</ChecklistItem>
            <ChecklistItem>Ensure proper network security configuration</ChecklistItem>
            <ChecklistItem>Keep software components up to date</ChecklistItem>
          </Checklist>

          <SectionDivider />

          <SecurityTitle>Container Security</SecurityTitle>
          <BodyParagraph>
            Always review container configurations and ensure they follow security best practices for your deployment
            environment.
          </BodyParagraph>
        </AlertStack>
      </SecurityCard>
    </SecurityScroll>
  )

  const tabItems = [
    {
      key: 'overview',
      label: (
        <TabLabel>
          <FileTextOutlined />
          {context === 'marketplace' ? t('marketplace:overview') : t('resources:templates.overview')}
        </TabLabel>
      ),
      children: overviewContent,
    },
    {
      key: 'files',
      label: (
        <TabLabel>
          <CodeOutlined />
          {context === 'marketplace' ? t('marketplace:files') : t('resources:templates.files')}
          {templateDetails?.files && ` (${templateDetails.files.length})`}
        </TabLabel>
      ),
      disabled: loading || !templateDetails,
      children: filesContent,
    },
    {
      key: 'security',
      label: (
        <TabLabel>
          <SafetyOutlined />
          {context === 'marketplace' ? t('marketplace:security') : 'Security'}
        </TabLabel>
      ),
      children: securityContent,
    },
  ]

  return (
    <StyledModal
      data-testid={context === 'marketplace' ? 'marketplace-preview-modal' : 'template-details-modal'}
      title={
        <TitleStack>
          {effectiveTemplate.iconUrl && !iconFailed ? (
            <TemplateAvatar
              src={effectiveTemplate.iconUrl}
              alt={effectiveTemplate.name}
              onError={() => setIconFailed(true)}
            />
          ) : (
            getTemplateIcon()
          )}
          <div>
            <TemplateHeading level={4}>{modalTitle}</TemplateHeading>
            {context === 'repo-creation' && (
              <Tag color="blue" data-testid="template-details-name-tag">
                {effectiveTemplate.name}
              </Tag>
            )}
            {context === 'marketplace' && effectiveTemplate.difficulty && (
              <DifficultyTag color={getDifficultyColor(effectiveTemplate.difficulty)}>
                {t(
                  `difficulty${effectiveTemplate.difficulty?.charAt(0).toUpperCase()}${effectiveTemplate.difficulty?.slice(
                    1
                  )}`
                )}
              </DifficultyTag>
            )}
          </div>
        </TitleStack>
      }
      open={visible}
      onCancel={onClose}
      className={ModalSize.ExtraLarge}
      footer={[
        <SecondaryActionButton
          key="close"
          onClick={onClose}
          data-testid={context === 'marketplace' ? 'marketplace-preview-close-button' : 'template-details-close-button'}
        >
          {t('common:actions.close')}
        </SecondaryActionButton>,
        <PrimaryActionButton
          key="action"
          type="primary"
          icon={getActionButtonIcon()}
          onClick={handleAction}
          data-testid={context === 'marketplace' ? 'marketplace-preview-deploy-button' : 'template-details-select-button'}
        >
          {getActionButtonText()}
        </PrimaryActionButton>,
      ]}
    >
      <StyledTabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        size="large"
        data-testid={context === 'marketplace' ? 'marketplace-preview-tabs' : 'template-details-tabs'}
      />
    </StyledModal>
  )
}

export default TemplatePreviewModal
