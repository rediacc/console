import React, { useEffect, useMemo, useState } from 'react';
import { Col, Empty } from 'antd';
import { useTranslation } from 'react-i18next';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { RediaccEmpty, RediaccStack, RediaccText } from '@/components/ui';
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
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import {
  ClearButton,
  DefaultTag,
  DetailsButton,
  EmptyResultsContainer,
  ErrorState,
  HelperRow,
  ResultCount,
  SearchContainer,
  SearchInput,
  SelectionIndicator,
  SelectorContainer,
  TemplateCard,
  TemplateDescription,
  TemplateGrid,
  TemplateIconWrapper,
} from './styles';

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

const GRID_GUTTER: [number, number] = [DESIGN_TOKENS.SPACING.MD, DESIGN_TOKENS.SPACING.MD];

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
        <div />
      </LoadingWrapper>
    );
  }

  if (error) {
    return (
      <ErrorState>
        <Empty description={error} />
      </ErrorState>
    );
  }

  return (
    <SelectorContainer>
      <SearchContainer>
        <RediaccStack direction="vertical" gap="md" fullWidth>
          <HelperRow>
            <RediaccText variant="caption">
              {multiple
                ? t('resources:templates.selectMultiple', {
                    defaultValue: 'Select templates (optional, multiple allowed)',
                  })
                : t('resources:templates.selectOptional')}
            </RediaccText>
            {((multiple && Array.isArray(value) && value.length > 0) || (!multiple && value)) && (
              <ClearButton
                data-testid="resource-modal-template-clear-button"
                onClick={() => onChange?.(multiple ? [] : null)}
              >
                {t('resources:templates.clearSelection')}
              </ClearButton>
            )}
          </HelperRow>

          <SearchInput
            placeholder={t('resources:templates.searchPlaceholder', {
              defaultValue: 'Search templates by name or description...',
            })}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            allowClear
            data-testid="resource-modal-template-search-input"
          />
        </RediaccStack>
      </SearchContainer>

      {searchQuery.trim() && (
        <ResultCount>
          {t('resources:templates.showingResults', {
            defaultValue: `Showing ${filteredTemplates.length} of ${templates.length} templates`,
            count: filteredTemplates.length,
            total: templates.length,
          })}
        </ResultCount>
      )}

      {searchQuery.trim() && filteredTemplates.length === 0 && (
        <EmptyResultsContainer>
          <RediaccEmpty
            variant="minimal"
            description={t('resources:templates.noResults', {
              defaultValue: `No templates found matching "${searchQuery}"`,
              query: searchQuery,
            })}
          />
        </EmptyResultsContainer>
      )}

      <TemplateGrid gutter={GRID_GUTTER}>
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
              <TemplateCard
                hoverable
                data-testid={`resource-modal-template-card-${template.name}`}
                $selected={isSelected}
                onClick={handleClick}
              >
                {isSelected && (
                  <SelectionIndicator>
                    <CheckCircleOutlined />
                  </SelectionIndicator>
                )}

                <RediaccStack direction="vertical" gap="sm" fullWidth>
                  <TemplateIconWrapper>
                    <TemplateIconComponent />
                  </TemplateIconWrapper>

                  <RediaccText variant="title" weight="bold">
                    {getTemplateTitle(template.name)}
                  </RediaccText>

                  <TemplateDescription>
                    <RediaccText variant="description" truncate maxLines={2}>
                      {getTemplateDescription(template.readme)}
                    </RediaccText>
                  </TemplateDescription>

                  <DetailsButton
                    variant="link"
                    data-testid={`resource-modal-template-details-button-${template.name}`}
                    icon={<InfoCircleOutlined />}
                    onClick={(e) => {
                      e.stopPropagation();
                      onViewDetails?.(template.name);
                    }}
                  >
                    {t('resources:templates.viewDetails')}
                  </DetailsButton>
                </RediaccStack>
              </TemplateCard>
            </Col>
          );
        })}

        {/* No Template Option - only show when not filtering or when search returns results */}
        {!multiple && !searchQuery.trim() && (
          <Col xs={24} sm={12} md={6}>
            <TemplateCard
              hoverable
              data-testid="resource-modal-template-card-none"
              $selected={!value}
              $variant="none"
              onClick={() => onChange?.(null)}
            >
              {!value && (
                <SelectionIndicator $variant="none">
                  <CheckCircleOutlined />
                </SelectionIndicator>
              )}

              <RediaccStack direction="vertical" gap="sm" fullWidth>
                <TemplateIconWrapper $muted>
                  <AppstoreOutlined />
                </TemplateIconWrapper>

                <RediaccText variant="title" weight="bold">
                  {t('resources:templates.noTemplate')}
                </RediaccText>

                <RediaccText variant="description">
                  {t('resources:templates.startEmpty')}
                </RediaccText>

                <DefaultTag variant="default">{t('resources:templates.default')}</DefaultTag>
              </RediaccStack>
            </TemplateCard>
          </Col>
        )}
      </TemplateGrid>
    </SelectorContainer>
  );
};

export default TemplateSelector;
