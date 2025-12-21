import React, { useEffect, useMemo, useState } from 'react';
import { Button, Card, Col, Empty, Flex, Input, Row, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { useAsyncAction } from '@/hooks/useAsyncAction';
import { templateService } from '@/services/templateService';
import {
  AppstoreOutlined,
  CheckCircleOutlined,
  CloudOutlined,
  DatabaseOutlined,
  GlobalOutlined,
  InfoCircleOutlined,
} from '@/utils/optimizedIcons';

interface Template {
  id?: string;
  name: string;
  readme: string;
}

interface TemplateSelectorProps {
  value?: string | string[] | null;
  onChange?: (templateId: string | string[] | null) => void;
  onViewDetails?: (templateName: string) => void;
  multiple?: boolean;
}

const GRID_GUTTER: [number, number] = [16, 16];

const TemplateSelector: React.FC<TemplateSelectorProps> = ({
  value,
  onChange,
  onViewDetails,
  multiple = false,
}) => {
  const { t } = useTranslation(['resources', 'common']);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const { execute, isExecuting: loading, error } = useAsyncAction();

  useEffect(() => {
    fetchTemplates();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchTemplates = async () => {
    const result = await execute(
      async () => {
        const fetchedTemplates = await templateService.fetchTemplates();
        // Sort templates alphabetically by name
        const sortedTemplates = fetchedTemplates.sort((a, b) => {
          return a.name.localeCompare(b.name);
        });
        return sortedTemplates;
      },
      {
        errorMessage: 'Unable to load templates. Please check your connection.',
      }
    );

    if (result.success && result.data) {
      setTemplates(result.data);
    }
  };

  const getTemplateIcon = (name: string) => {
    const lowerName = name.toLowerCase();
    if (lowerName.includes('db_') || lowerName.includes('database') || lowerName.includes('sql')) {
      return DatabaseOutlined;
    }
    if (
      lowerName.includes('nginx') ||
      lowerName.includes('wordpress') ||
      lowerName.includes('web')
    ) {
      return GlobalOutlined;
    }
    if (lowerName.includes('cloud') || lowerName.includes('route')) {
      return CloudOutlined;
    }
    return AppstoreOutlined;
  };

  const getTemplateTitle = (name: string) => {
    // Extract meaningful title from template name
    const cleanName = name.replace(/^(db_|kick_|route_)/, '');
    return cleanName.charAt(0).toUpperCase() + cleanName.slice(1);
  };

  const getTemplateDescription = (readme: string) => {
    // Extract first meaningful line from README
    const lines = readme.split('\n').filter((line) => line.trim() && !line.startsWith('#'));
    return lines[0] || 'Template for quick deployment';
  };

  // Filter templates based on search query
  const filteredTemplates = useMemo(() => {
    if (!searchQuery.trim()) {
      return templates;
    }

    const lowerQuery = searchQuery.toLowerCase();
    return templates.filter((template) => {
      const templateName = getTemplateTitle(template.name).toLowerCase();
      const templateDescription = getTemplateDescription(template.readme).toLowerCase();

      return templateName.includes(lowerQuery) || templateDescription.includes(lowerQuery);
    });
  }, [templates, searchQuery]);

  if (loading) {
    return (
      <LoadingWrapper
        loading
        centered
        minHeight={160}
        tip={t('resources:templates.loading')}
        showTextBelow
      >
        <Flex />
      </LoadingWrapper>
    );
  }

  if (error) {
    return (
      <Flex style={{ textAlign: 'center' }}>
        <Empty description={error} />
      </Flex>
    );
  }

  return (
    <Flex vertical style={{ width: '100%' }}>
      <Flex vertical>
        <Flex vertical gap={16} style={{ width: '100%' }}>
          <Flex align="center" justify="space-between" wrap gap={12}>
            <Typography.Text>
              {multiple
                ? t('resources:templates.selectMultiple')
                : t('resources:templates.selectOptional')}
            </Typography.Text>
            {((multiple && Array.isArray(value) && value.length > 0) || (!multiple && value)) && (
              <Button
                data-testid="resource-modal-template-clear-button"
                onClick={() => onChange?.(multiple ? [] : null)}
              >
                {t('resources:templates.clearSelection')}
              </Button>
            )}
          </Flex>

          <Input
            placeholder={t('resources:templates.searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            allowClear
            data-testid="resource-modal-template-search-input"
          />
        </Flex>
      </Flex>

      {searchQuery.trim() && (
        <Typography.Text style={{ display: 'block' }}>
          {t('resources:templates.showingResults', {
            count: filteredTemplates.length,
            total: templates.length,
          })}
        </Typography.Text>
      )}

      {searchQuery.trim() && filteredTemplates.length === 0 && (
        <Flex>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t('resources:templates.noResults', {
              query: searchQuery,
            })}
          />
        </Flex>
      )}

      <Row gutter={GRID_GUTTER}>
        {filteredTemplates.map((template) => {
          const templateId = template.id || template.name;
          const isSelected = multiple
            ? Array.isArray(value) && value.includes(templateId)
            : value === templateId;

          const handleClick = () => {
            if (multiple) {
              const currentSelection = Array.isArray(value) ? value : [];
              if (isSelected) {
                // Deselect
                onChange?.(currentSelection.filter((id) => id !== templateId));
              } else {
                // Select
                onChange?.([...currentSelection, templateId]);
              }
            } else {
              // Single selection mode
              onChange?.(isSelected ? null : templateId);
            }
          };

          const TemplateIconComponent = getTemplateIcon(template.name);

          return (
            <Col key={template.name} xs={24} sm={12} md={6}>
              <Card
                hoverable
                data-testid={`resource-modal-template-card-${template.name}`}
                onClick={handleClick}
              >
                {isSelected && (
                  <Typography.Text
                    style={{ position: 'absolute', top: 12, right: 12, fontSize: 16 }}
                  >
                    <CheckCircleOutlined />
                  </Typography.Text>
                )}

                <Flex vertical gap={8} style={{ width: '100%' }}>
                  <Flex style={{ textAlign: 'center' }}>
                    <TemplateIconComponent />
                  </Flex>

                  <Typography.Text strong>{getTemplateTitle(template.name)}</Typography.Text>

                  <Typography.Text style={{ display: 'block' }}>
                    <Typography.Paragraph ellipsis={{ rows: 2 }} style={{ margin: 0 }}>
                      {getTemplateDescription(template.readme)}
                    </Typography.Paragraph>
                  </Typography.Text>

                  <Button
                    type="link"
                    data-testid={`resource-modal-template-details-button-${template.name}`}
                    icon={<InfoCircleOutlined />}
                    onClick={(e: React.MouseEvent<HTMLButtonElement>) => {
                      e.stopPropagation();
                      onViewDetails?.(template.name);
                    }}
                  >
                    {t('resources:templates.viewDetails')}
                  </Button>
                </Flex>
              </Card>
            </Col>
          );
        })}

        {/* No Template Option - only show when not filtering or when search returns results */}
        {!multiple && !searchQuery.trim() && (
          <Col xs={24} sm={12} md={6}>
            <Card
              hoverable
              data-testid="resource-modal-template-card-none"
              onClick={() => onChange?.(null)}
            >
              {!value && (
                <Typography.Text style={{ position: 'absolute', top: 12, right: 12, fontSize: 16 }}>
                  <CheckCircleOutlined />
                </Typography.Text>
              )}

              <Flex vertical gap={8} style={{ width: '100%' }}>
                <Flex style={{ textAlign: 'center' }}>
                  <AppstoreOutlined />
                </Flex>

                <Typography.Text strong>{t('resources:templates.noTemplate')}</Typography.Text>

                <Typography.Text>{t('resources:templates.startEmpty')}</Typography.Text>

                <Tag color="default">{t('resources:templates.default')}</Tag>
              </Flex>
            </Card>
          </Col>
        )}
      </Row>
    </Flex>
  );
};

export default TemplateSelector;
