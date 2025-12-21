import React, { useEffect, useState, type ComponentPropsWithoutRef } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Flex,
  List,
  Modal,
  Row,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import { useTranslation } from 'react-i18next';
import ReactMarkdown, { type Components as MarkdownComponents } from 'react-markdown';
import { Prism as SyntaxHighlighter, type SyntaxHighlighterProps } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { templateService } from '@/services/templateService';
import { ModalSize } from '@/types/modal';
import {
  AppstoreOutlined,
  CheckCircleOutlined,
  CodeOutlined,
  FileOutlined,
  FileTextOutlined,
  RocketOutlined,
  SafetyOutlined,
} from '@/utils/optimizedIcons';

interface TemplateFile {
  name: string;
  path: string;
  content: string;
}

interface Template {
  id?: string;
  name: string;
  readme: string;
  category?: string;
  tags?: string[];
  difficulty?: 'beginner' | 'intermediate' | 'advanced';
  iconUrl?: string;
  download_url?: string;
}

interface TemplateDetails {
  name: string;
  readme: string;
  files: TemplateFile[];
}

interface TemplatePreviewModalProps {
  open: boolean;
  template: Template | null;
  templateName?: string | null; // For backward compatibility with TemplateDetailsModal
  onClose: () => void;
  onUseTemplate: (template: Template | string) => void;
  context?: 'marketplace' | 'repository-creation';
}

type CodeRendererProps = ComponentPropsWithoutRef<'code'> & {
  inline?: boolean;
};

const TemplatePreviewModal: React.FC<TemplatePreviewModalProps> = ({
  open,
  template,
  templateName,
  onClose,
  onUseTemplate,
  context = 'marketplace',
}) => {
  const { t } = useTranslation(['marketplace', 'resources', 'common']);
  const [loading, setLoading] = useState(false);
  const [templateDetails, setTemplateDetails] = useState<TemplateDetails | null>(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedFileIndex, setSelectedFileIndex] = useState(0);
  const [loadedTemplate, setLoadedTemplate] = useState<Template | null>(null);
  const [iconFailed, setIconFailed] = useState(false);

  const codeTheme = vscDarkPlus as SyntaxHighlighterProps['style'];

  const markdownComponents: MarkdownComponents = {
    code({ inline, className, children }: CodeRendererProps) {
      const match = /language-(\w+)/.exec(className ?? '');

      if (!inline && match) {
        return (
          <SyntaxHighlighter style={codeTheme} language={match[1]} PreTag="div">
            {String(children).replace(/\n$/, '')}
          </SyntaxHighlighter>
        );
      }

      return <code className={className}>{children}</code>;
    },
  };

  // Support both template object and templateName for backward compatibility
  const effectiveTemplate =
    loadedTemplate || template || (templateName ? { name: templateName, readme: '' } : null);

  useEffect(() => {
    if (!open) {
      // Reset state when modal is closed
      setTemplateDetails(null);
      setLoadedTemplate(null);
      setLoading(false);
      setActiveTab('overview');
      setSelectedFileIndex(0);
      return;
    }

    const fetchTemplateDetails = async () => {
      let baseTemplate = template || (templateName ? { name: templateName, readme: '' } : null);
      if (!baseTemplate) return;

      try {
        setLoading(true);

        // For repository creation context, fetch the template from templates.json to get README
        if (context === 'repository-creation' && templateName && !baseTemplate.readme) {
          try {
            const templates: Template[] = await templateService.fetchTemplates();
            const foundTemplate = templates.find(
              (templateItem) => templateItem.name === templateName
            );
            if (foundTemplate) {
              // Set the loaded template with README content
              const fullTemplate = {
                id: foundTemplate.id,
                name: foundTemplate.name,
                readme: foundTemplate.readme,
                category: foundTemplate.category,
                tags: foundTemplate.tags,
                difficulty: foundTemplate.difficulty,
                download_url: foundTemplate.download_url,
              };
              setLoadedTemplate(fullTemplate);
              baseTemplate = fullTemplate; // Use the full template for fetching details
            }
          } catch (templatesError) {
            console.error('Failed to fetch templates:', templatesError);
          }
        }

        // Fetch the detailed template data (files, etc.)
        const data = await templateService.fetchTemplateData(baseTemplate);
        setTemplateDetails(data as unknown as TemplateDetails);
      } catch (error) {
        // Failed to fetch template details
        console.error('Failed to fetch template details:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchTemplateDetails();
    setActiveTab('overview');
    setSelectedFileIndex(0);
  }, [open, template, templateName, context]);

  useEffect(() => {
    setIconFailed(false);
  }, [effectiveTemplate?.iconUrl]);

  if (!effectiveTemplate) return null;

  // Use generic icon for all templates (backend provides proper names)
  const getTemplateIcon = () => (
    <Typography.Text style={{ display: 'inline-flex', fontSize: 32 }}>
      <AppstoreOutlined />
    </Typography.Text>
  );

  const getDifficultyColor = (difficulty?: string) => {
    switch (difficulty) {
      case 'beginner':
        return 'success';
      case 'intermediate':
        return 'warning';
      case 'advanced':
        return 'error';
      default:
        return 'neutral';
    }
  };

  const renderFileContent = (file: TemplateFile) => {
    const language =
      file.name.endsWith('.yaml') || file.name.endsWith('.yml')
        ? 'yaml'
        : file.name.endsWith('.json')
          ? 'json'
          : file.name.endsWith('.sh')
            ? 'bash'
            : file.name.endsWith('.env')
              ? 'bash'
              : file.name.endsWith('.md')
                ? 'markdown'
                : 'text';

    if (language === 'markdown') {
      return <ReactMarkdown components={markdownComponents}>{file.content}</ReactMarkdown>;
    }

    return (
      <SyntaxHighlighter language={language} style={codeTheme}>
        {file.content}
      </SyntaxHighlighter>
    );
  };

  const getActionButtonText = () => {
    if (context === 'marketplace') {
      return t('marketplace:deployNow');
    }
    return t('resources:templates.useTemplate');
  };

  const getActionButtonIcon = () => {
    if (context === 'marketplace') {
      return <RocketOutlined />;
    }
    return <CheckCircleOutlined />;
  };

  const handleAction = () => {
    if (context === 'marketplace') {
      onUseTemplate(effectiveTemplate);
    } else {
      // For repository creation, pass the template name
      onUseTemplate(effectiveTemplate.name);
    }
    onClose();
  };

  const modalTitle =
    context === 'marketplace' ? effectiveTemplate.name : t('resources:templates.templateDetails');

  const overviewContent = (
    <Flex style={{ overflow: 'auto' }}>
      <Row gutter={[24, 24]}>
        <Col xs={24} md={context === 'marketplace' ? 16 : 24}>
          <Card
            title={
              <Typography.Text strong>
                {context === 'marketplace'
                  ? t('marketplace:description')
                  : t('resources:templates.overview')}
              </Typography.Text>
            }
            data-testid={context === 'marketplace' ? undefined : 'template-details-readme-content'}
          >
            <Flex style={{ lineHeight: 1.5 }}>
              <ReactMarkdown>{templateDetails?.readme || effectiveTemplate.readme}</ReactMarkdown>
            </Flex>
          </Card>
        </Col>
        {context === 'marketplace' && (
          <Col xs={24} md={8}>
            <Card title={<Typography.Text strong>{t('marketplace:features')}</Typography.Text>}>
              <Flex vertical gap={8} style={{ width: '100%' }}>
                {effectiveTemplate.tags?.map((tag) => (
                  <Flex key={tag} gap={8} align="center" style={{ width: '100%' }}>
                    <Flex align="center" style={{ display: 'inline-flex' }}>
                      <CheckCircleOutlined />
                    </Flex>
                    <Typography.Text>{tag}</Typography.Text>
                  </Flex>
                ))}
              </Flex>
            </Card>
          </Col>
        )}
      </Row>
    </Flex>
  );

  const filesContent = loading ? (
    <Flex
      vertical
      align="center"
      gap={8}
      style={{ width: '100%' }}
      data-testid={context === 'marketplace' ? undefined : 'template-details-loading'}
    >
      <LoadingWrapper loading centered minHeight={160}>
        <Flex />
      </LoadingWrapper>
      <Typography.Text>
        {context === 'marketplace'
          ? t('marketplace:loadingFiles')
          : t('resources:templates.loadingDetails')}
      </Typography.Text>
    </Flex>
  ) : templateDetails && templateDetails.files.length > 0 ? (
    <Flex gap={16} wrap style={{ width: '100%' }}>
      <Flex style={{ width: '32%' }}>
        <Card
          title={
            <Flex align="center" gap={8} style={{ display: 'inline-flex' }}>
              <FileOutlined />
              {context === 'marketplace'
                ? t('marketplace:fileList')
                : t('resources:templates.files')}
            </Flex>
          }
          data-testid={context === 'marketplace' ? undefined : 'template-details-files-content'}
        >
          <Flex style={{ height: '100%' }}>
            <List
              dataSource={templateDetails.files}
              renderItem={(file, index) => (
                <List.Item
                  onClick={() => setSelectedFileIndex(index)}
                  data-testid={
                    context === 'marketplace'
                      ? `marketplace-preview-file-item-${index}`
                      : `template-details-file-header-${index}`
                  }
                >
                  <Flex vertical gap={4}>
                    <Flex align="center" gap={8} style={{ display: 'inline-flex' }}>
                      <CodeOutlined />
                      <Typography.Text code>{file.path || file.name}</Typography.Text>
                    </Flex>
                  </Flex>
                </List.Item>
              )}
            />
          </Flex>
        </Card>
      </Flex>
      <Flex style={{ flex: '1 1 auto' }}>
        <Card
          title={
            <Flex gap={8} align="center" justify="space-between">
              <Flex align="center" gap={8} style={{ display: 'inline-flex' }}>
                <CodeOutlined />
                <Typography.Text style={{ fontFamily: 'monospace' }}>
                  {templateDetails.files[selectedFileIndex]?.path ||
                    templateDetails.files[selectedFileIndex]?.name}
                </Typography.Text>
              </Flex>
            </Flex>
          }
          data-testid={
            context === 'marketplace'
              ? undefined
              : `template-details-file-content-${selectedFileIndex}`
          }
        >
          <Flex style={{ flex: '1 1 auto', overflow: 'auto' }}>
            {templateDetails.files[selectedFileIndex] &&
              renderFileContent(templateDetails.files[selectedFileIndex])}
          </Flex>
        </Card>
      </Flex>
    </Flex>
  ) : (
    <Alert
      message={
        context === 'marketplace' ? t('marketplace:noFiles') : t('resources:templates.noReadme')
      }
      description={context === 'marketplace' ? t('marketplace:noFilesDesc') : undefined}
      type="info"
      showIcon
      data-testid={context === 'marketplace' ? undefined : 'template-details-readme-empty'}
    />
  );

  const securityContent = (
    <Flex style={{ overflow: 'auto' }}>
      <Card>
        <Flex vertical gap={16}>
          <Alert
            message={
              <Typography.Text strong>
                {context === 'marketplace' ? t('marketplace:securityReview') : 'Security Review'}
              </Typography.Text>
            }
            description={
              <Typography.Text>
                {context === 'marketplace'
                  ? t('marketplace:securityReviewDesc')
                  : 'Please review the template files for security considerations before deployment.'}
              </Typography.Text>
            }
            type="info"
            showIcon
          />

          <Typography.Title level={5}>
            {context === 'marketplace' ? t('marketplace:bestPractices') : 'Best Practices'}
          </Typography.Title>
          <ul>
            <li style={{ lineHeight: 1.5 }}>Review all configuration files before deployment</li>
            <li style={{ lineHeight: 1.5 }}>Update default passwords and credentials</li>
            <li style={{ lineHeight: 1.5 }}>Ensure proper network security configuration</li>
            <li style={{ lineHeight: 1.5 }}>Keep software components up to date</li>
          </ul>

          <Divider style={{ margin: '24px 0' }} />

          <Typography.Title level={5}>Container Security</Typography.Title>
          <Typography.Paragraph style={{ lineHeight: 1.5 }}>
            Always review container configurations and ensure they follow security best practices
            for your deployment environment.
          </Typography.Paragraph>
        </Flex>
      </Card>
    </Flex>
  );

  const tabItems = [
    {
      key: 'overview',
      label: (
        <Flex align="center" gap={8}>
          <FileTextOutlined />
          {context === 'marketplace'
            ? t('marketplace:overview')
            : t('resources:templates.overview')}
        </Flex>
      ),
      children: overviewContent,
    },
    {
      key: 'files',
      label: (
        <Flex align="center" gap={8}>
          <CodeOutlined />
          {context === 'marketplace' ? t('marketplace:files') : t('resources:templates.files')}
          {templateDetails?.files && ` (${templateDetails.files.length})`}
        </Flex>
      ),
      disabled: loading || !templateDetails,
      children: filesContent,
    },
    {
      key: 'security',
      label: (
        <Flex align="center" gap={8}>
          <SafetyOutlined />
          {context === 'marketplace' ? t('marketplace:security') : 'Security'}
        </Flex>
      ),
      children: securityContent,
    },
  ];

  return (
    <Modal
      data-testid={
        context === 'marketplace' ? 'marketplace-preview-modal' : 'template-details-modal'
      }
      title={
        <Flex gap={16} align="center">
          {effectiveTemplate.iconUrl && !iconFailed ? (
            <img
              src={effectiveTemplate.iconUrl}
              alt={effectiveTemplate.name}
              onError={() => setIconFailed(true)}
              style={{ width: 40, height: 40, objectFit: 'contain' }}
            />
          ) : (
            getTemplateIcon()
          )}
          <Flex vertical>
            <Typography.Title level={4}>{modalTitle}</Typography.Title>
            {context === 'repository-creation' && (
              <Tag data-testid="template-details-name-tag" color="processing">
                {effectiveTemplate.name}
              </Tag>
            )}
            {context === 'marketplace' && effectiveTemplate.difficulty && (
              <Tag color={getDifficultyColor(effectiveTemplate.difficulty)}>
                {t(
                  `difficulty${effectiveTemplate.difficulty?.charAt(0).toUpperCase()}${effectiveTemplate.difficulty?.slice(
                    1
                  )}`
                )}
              </Tag>
            )}
          </Flex>
        </Flex>
      }
      open={open}
      onCancel={onClose}
      className={ModalSize.Large}
      footer={[
        <Button
          key="close"
          onClick={onClose}
          data-testid={
            context === 'marketplace'
              ? 'marketplace-preview-close-button'
              : 'template-details-close-button'
          }
        >
          {t('common:actions.close')}
        </Button>,
        <Button
          key="action"
          icon={getActionButtonIcon()}
          onClick={handleAction}
          data-testid={
            context === 'marketplace'
              ? 'marketplace-preview-deploy-button'
              : 'template-details-select-button'
          }
        >
          {getActionButtonText()}
        </Button>,
      ]}
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        size="middle"
        data-testid={
          context === 'marketplace' ? 'marketplace-preview-tabs' : 'template-details-tabs'
        }
      />
    </Modal>
  );
};

export default TemplatePreviewModal;
