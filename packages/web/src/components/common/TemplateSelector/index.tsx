import React, { useState, useEffect, useMemo } from 'react'
import { Col, Empty, message } from 'antd'
import {
  DatabaseOutlined,
  GlobalOutlined,
  CloudOutlined,
  CheckCircleOutlined,
  InfoCircleOutlined,
  AppstoreOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { DESIGN_TOKENS } from '@/utils/styleConstants'
import { templateService } from '@/services/templateService'
import {
  SelectorContainer,
  HeaderStack,
  HelperRow,
  HelperText,
  ClearButton,
  SearchInput,
  ResultCount,
  NoResultsEmpty,
  TemplateGrid,
  TemplateCard,
  SelectionIndicator,
  CardStack,
  TemplateIconWrapper,
  TemplateTitle,
  TemplateDescription,
  DetailsButton,
  DefaultTag,
  LoadingState,
  LoadingText,
  ErrorState,
} from './styles'
import LoadingWrapper from '@/components/common/LoadingWrapper'

interface Template {
  id?: string
  name: string
  readme: string
}

interface TemplateSelectorProps {
  value?: string | string[] | null
  onChange?: (templateId: string | string[] | null) => void
  onViewDetails?: (templateName: string) => void
  multiple?: boolean
}

const GRID_GUTTER: [number, number] = [
  DESIGN_TOKENS.SPACING.MD,
  DESIGN_TOKENS.SPACING.MD,
]

const TemplateSelector: React.FC<TemplateSelectorProps> = ({
  value,
  onChange,
  onViewDetails,
  multiple = false
}) => {
  const { t } = useTranslation(['resources', 'common'])
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    fetchTemplates()
  }, [])

  const fetchTemplates = async () => {
    try {
      setLoading(true)
      setError(null)

      const fetchedTemplates = await templateService.fetchTemplates()
      // Sort templates alphabetically by name
      const sortedTemplates = fetchedTemplates.sort((a, b) => {
        return a.name.localeCompare(b.name)
      })
      setTemplates(sortedTemplates)
    } catch (err) {
      console.error('Failed to fetch templates:', err)
      setError('Unable to load templates. Please check your connection.')
      message.error('Unable to load templates. Please check your connection.')
    } finally {
      setLoading(false)
    }
  }

  const getTemplateIcon = (name: string) => {
    const lowerName = name.toLowerCase()
    if (lowerName.includes('db_') || lowerName.includes('database') || lowerName.includes('sql')) {
      return DatabaseOutlined
    }
    if (lowerName.includes('nginx') || lowerName.includes('wordpress') || lowerName.includes('web')) {
      return GlobalOutlined
    }
    if (lowerName.includes('cloud') || lowerName.includes('route')) {
      return CloudOutlined
    }
    return AppstoreOutlined
  }

  const getTemplateTitle = (name: string) => {
    // Extract meaningful title from template name
    const cleanName = name.replace(/^(db_|kick_|route_)/, '')
    return cleanName.charAt(0).toUpperCase() + cleanName.slice(1)
  }

  const getTemplateDescription = (readme: string) => {
    // Extract first meaningful line from README
    const lines = readme.split('\n').filter(line => line.trim() && !line.startsWith('#'))
    return lines[0] || 'Template for quick deployment'
  }

  // Filter templates based on search query
  const filteredTemplates = useMemo(() => {
    if (!searchQuery.trim()) {
      return templates
    }

    const lowerQuery = searchQuery.toLowerCase()
    return templates.filter(template => {
      const templateName = getTemplateTitle(template.name).toLowerCase()
      const templateDescription = getTemplateDescription(template.readme).toLowerCase()

      return templateName.includes(lowerQuery) || templateDescription.includes(lowerQuery)
    })
  }, [templates, searchQuery])

  if (loading) {
    return (
      <LoadingState>
        <LoadingWrapper loading centered minHeight={160}>
          <div />
        </LoadingWrapper>
        <LoadingText>
          {t('resources:templates.loading')}
        </LoadingText>
      </LoadingState>
    )
  }

  if (error) {
    return (
      <ErrorState>
        <Empty description={error} />
      </ErrorState>
    )
  }

  return (
    <SelectorContainer>
      <HeaderStack direction="vertical" size="middle">
        <HelperRow>
          <HelperText>
            {multiple
              ? t('resources:templates.selectMultiple', { defaultValue: 'Select templates (optional, multiple allowed)' })
              : t('resources:templates.selectOptional')}
          </HelperText>
          {((multiple && Array.isArray(value) && value.length > 0) || (!multiple && value)) && (
            <ClearButton
              size="small"
              data-testid="resource-modal-template-clear-button"
              onClick={() => onChange?.(multiple ? [] : null)}
            >
              {t('resources:templates.clearSelection')}
            </ClearButton>
          )}
        </HelperRow>

        <SearchInput
          placeholder={t('resources:templates.searchPlaceholder', { defaultValue: 'Search templates by name or description...' })}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          allowClear
          data-testid="resource-modal-template-search-input"
        />
      </HeaderStack>

      {searchQuery.trim() && (
        <ResultCount>
          {t('resources:templates.showingResults', {
            defaultValue: `Showing ${filteredTemplates.length} of ${templates.length} templates`,
            count: filteredTemplates.length,
            total: templates.length
          })}
        </ResultCount>
      )}

      {searchQuery.trim() && filteredTemplates.length === 0 && (
        <NoResultsEmpty
          description={t('resources:templates.noResults', {
            defaultValue: `No templates found matching "${searchQuery}"`,
            query: searchQuery
          })}
        />
      )}

      <TemplateGrid gutter={GRID_GUTTER}>
        {filteredTemplates.map((template) => {
          const templateId = template.id || template.name
          const isSelected = multiple
            ? Array.isArray(value) && value.includes(templateId)
            : value === templateId

          const handleClick = () => {
            if (multiple) {
              const currentSelection = Array.isArray(value) ? value : []
              if (isSelected) {
                // Deselect
                onChange?.(currentSelection.filter(id => id !== templateId))
              } else {
                // Select
                onChange?.([...currentSelection, templateId])
              }
            } else {
              // Single selection mode
              onChange?.(isSelected ? null : templateId)
            }
          }

          const TemplateIconComponent = getTemplateIcon(template.name)

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
                
                <CardStack direction="vertical" size="small">
                  <TemplateIconWrapper>
                    <TemplateIconComponent />
                  </TemplateIconWrapper>
                  
                  <TemplateTitle strong>
                    {getTemplateTitle(template.name)}
                  </TemplateTitle>
                  
                  <TemplateDescription
                    ellipsis={{ rows: 2 }} 
                    type="secondary"
                  >
                    {getTemplateDescription(template.readme)}
                  </TemplateDescription>
                  
                  <DetailsButton
                    type="link"
                    size="small"
                    data-testid={`resource-modal-template-details-button-${template.name}`}
                    icon={<InfoCircleOutlined />}
                    onClick={(e) => {
                      e.stopPropagation()
                      onViewDetails?.(template.name)
                    }}
                  >
                    {t('resources:templates.viewDetails')}
                  </DetailsButton>
                </CardStack>
              </TemplateCard>
            </Col>
          )
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
            
            <CardStack direction="vertical" size="small">
              <TemplateIconWrapper $muted>
                <AppstoreOutlined />
              </TemplateIconWrapper>
              
              <TemplateTitle strong>
                {t('resources:templates.noTemplate')}
              </TemplateTitle>
              
              <TemplateDescription type="secondary">
                {t('resources:templates.startEmpty')}
              </TemplateDescription>
              
              <DefaultTag color="default">
                {t('resources:templates.default')}
              </DefaultTag>
            </CardStack>
          </TemplateCard>
        </Col>
        )}
      </TemplateGrid>
    </SelectorContainer>
  )
}

export default TemplateSelector
