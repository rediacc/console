import React, { useEffect, useState, type ComponentPropsWithoutRef } from 'react';
import { Alert, Button, Card, Col, Divider, Flex, List, Row, Tabs, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import ReactMarkdown, { type Components as MarkdownComponents } from 'react-markdown';
import { Prism as SyntaxHighlighter, type SyntaxHighlighterProps } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { SizedModal } from '@/components/common/SizedModal';
import { templateService } from '@/services/templateService';
import { ModalSize } from '@/types/modal';
import {
  AppstoreOutlined,
  CheckCircleOutlined,
  CodeOutlined,
  FileOutlined,
  FileTextOutlined,
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
}) => {
  const { t } = useTranslation(['resources', 'common']);
  const [loading, setLoading] = useState(false);
  const [templateDetails, setTemplateDetails] = useState<TemplateDetails | null>(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedFileIndex, setSelectedFileIndex] = useState(0);
  const [loadedTemplate, setLoadedTemplate] = useState<Template | null>(null);
  const [iconFailed, setIconFailed] = useState(false);

  const codeTheme = vscDarkPlus as SyntaxHighlighterProps['style'];

  const markdownComponents: MarkdownComponents = {
    code: function CodeRenderer({ inline, className, children }: CodeRendererProps) {
      const match = /language-(\w+)/.exec(className ?? '');

      if (!inline && match) {
        return (
          // eslint-disable-next-line no-restricted-syntax
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
    loadedTemplate ?? template ?? (templateName ? { name: templateName, readme: '' } : null);

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
      let baseTemplate = template ?? (templateName ? { name: templateName, readme: '' } : null);
      if (!baseTemplate) return;

      try {
        setLoading(true);

        // Fetch the template from templates.json to get README if not already provided
        if (templateName && !baseTemplate.readme) {
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

    void fetchTemplateDetails();
    setActiveTab('overview');
    setSelectedFileIndex(0);
  }, [open, template, templateName]);

  useEffect(() => {
    setIconFailed(false);
  }, [effectiveTemplate?.iconUrl]);

  if (!effectiveTemplate) return null;

  // Use generic icon for all templates (backend provides proper names)
  const getTemplateIcon = () => (
    <Typography.Text className="inline-flex text-2xl">
      <AppstoreOutlined />
    </Typography.Text>
  );

  const renderFileContent = (file: TemplateFile) => {
    let language: string;
    if (file.name.endsWith('.yaml') || file.name.endsWith('.yml')) {
      language = 'yaml';
    } else if (file.name.endsWith('.json')) {
      language = 'json';
    } else if (file.name.endsWith('.sh')) {
      language = 'bash';
    } else if (file.name.endsWith('.env')) {
      language = 'bash';
    } else if (file.name.endsWith('.md')) {
      language = 'markdown';
    } else {
      language = 'text';
    }

    if (language === 'markdown') {
      return <ReactMarkdown components={markdownComponents}>{file.content}</ReactMarkdown>;
    }

    return (
      // eslint-disable-next-line no-restricted-syntax
      <SyntaxHighlighter language={language} style={codeTheme}>
        {file.content}
      </SyntaxHighlighter>
    );
  };

  const handleAction = () => {
    onUseTemplate(effectiveTemplate.name);
    onClose();
  };

  const modalTitle = t('resources:templates.templateDetails');

  const overviewContent = (
    <Flex className="overflow-auto">
      <Row gutter={[24, 24]}>
        <Col xs={24}>
          <Card
            title={<Typography.Text strong>{t('resources:templates.overview')}</Typography.Text>}
            data-testid="template-details-readme-content"
          >
            <Flex className="line-height-normal">
              <ReactMarkdown>{templateDetails?.readme ?? effectiveTemplate.readme}</ReactMarkdown>
            </Flex>
          </Card>
        </Col>
      </Row>
    </Flex>
  );

  const filesContent = (() => {
    if (loading) {
      return (
        <Flex
          vertical
          align="center"
          className="gap-sm w-full"
          data-testid="template-details-loading"
        >
          <LoadingWrapper loading centered minHeight={160}>
            <Flex />
          </LoadingWrapper>
          <Typography.Text>{t('resources:templates.loadingDetails')}</Typography.Text>
        </Flex>
      );
    } else if (templateDetails && templateDetails.files.length > 0) {
      return (
        <Flex className="gap-md w-full" wrap>
          <Flex className="w-[32%]">
            <Card
              title={
                <Flex align="center" className="inline-flex">
                  <FileOutlined />
                  {t('resources:templates.files')}
                </Flex>
              }
              data-testid="template-details-files-content"
            >
              <Flex className="h-full">
                <List
                  dataSource={templateDetails.files}
                  renderItem={(file, index) => (
                    <List.Item
                      onClick={() => setSelectedFileIndex(index)}
                      data-testid={`template-details-file-header-${index}`}
                    >
                      <Flex vertical className="gap-sm">
                        <Flex align="center" className="inline-flex">
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
          <Flex className="flex-1">
            <Card
              title={
                <Flex align="center" justify="space-between">
                  <Flex align="center" className="inline-flex">
                    <CodeOutlined />
                    <Typography.Text className="font-mono">
                      {templateDetails.files[selectedFileIndex]?.path ||
                        templateDetails.files[selectedFileIndex]?.name}
                    </Typography.Text>
                  </Flex>
                </Flex>
              }
              data-testid={`template-details-file-content-${selectedFileIndex}`}
            >
              <Flex className="flex-1 overflow-auto">
                {templateDetails.files[selectedFileIndex] &&
                  renderFileContent(templateDetails.files[selectedFileIndex])}
              </Flex>
            </Card>
          </Flex>
        </Flex>
      );
    }
    return (
      <Alert
        message={t('resources:templates.noReadme')}
        type="info"
        data-testid="template-details-readme-empty"
      />
    );
  })();

  const securityContent = (
    <Flex className="overflow-auto">
      <Card>
        <Flex vertical>
          <Alert
            message={
              <Typography.Text strong>{t('resources:templates.securityReview')}</Typography.Text>
            }
            description={
              <Typography.Text>{t('resources:templates.securityReviewDesc')}</Typography.Text>
            }
            type="info"
          />

          <Typography.Title level={5}>{t('resources:templates.bestPractices')}</Typography.Title>
          <ul className="line-height-normal">
            <li>{t('resources:templates.bestPractice1')}</li>
            <li>{t('resources:templates.bestPractice2')}</li>
            <li>{t('resources:templates.bestPractice3')}</li>
            <li>{t('resources:templates.bestPractice4')}</li>
          </ul>

          <Divider className="my-6" />

          <Typography.Title level={5}>
            {t('resources:templates.containerSecurity')}
          </Typography.Title>
          <Typography.Paragraph className="line-height-normal">
            {t('resources:templates.containerSecurityDesc')}
          </Typography.Paragraph>
        </Flex>
      </Card>
    </Flex>
  );

  const tabItems = [
    {
      key: 'overview',
      label: (
        <Flex align="center">
          <FileTextOutlined />
          {t('resources:templates.overview')}
        </Flex>
      ),
      children: overviewContent,
    },
    {
      key: 'files',
      label: (
        <Flex align="center">
          <CodeOutlined />
          {t('resources:templates.files')}
          {templateDetails?.files && ` (${templateDetails.files.length})`}
        </Flex>
      ),
      disabled: loading || !templateDetails,
      children: filesContent,
    },
    {
      key: 'security',
      label: (
        <Flex align="center">
          <SafetyOutlined />
          {t('resources:templates.security')}
        </Flex>
      ),
      children: securityContent,
    },
  ];

  return (
    <SizedModal
      data-testid="template-details-modal"
      title={
        <Flex className="gap-md" align="center">
          {effectiveTemplate.iconUrl && !iconFailed ? (
            <img
              src={effectiveTemplate.iconUrl}
              alt={effectiveTemplate.name}
              onError={() => setIconFailed(true)}
              className="object-contain"
            />
          ) : (
            getTemplateIcon()
          )}
          <Flex vertical>
            <Typography.Title level={4}>{modalTitle}</Typography.Title>
            <Tag data-testid="template-details-name-tag">{effectiveTemplate.name}</Tag>
          </Flex>
        </Flex>
      }
      open={open}
      onCancel={onClose}
      size={ModalSize.Large}
      footer={[
        <Button key="close" onClick={onClose} data-testid="template-details-close-button">
          {t('common:actions.close')}
        </Button>,
        <Button
          key="action"
          icon={<CheckCircleOutlined />}
          onClick={handleAction}
          data-testid="template-details-select-button"
        >
          {t('resources:templates.useTemplate')}
        </Button>,
      ]}
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        size="middle"
        data-testid="template-details-tabs"
      />
    </SizedModal>
  );
};

export default TemplatePreviewModal;
