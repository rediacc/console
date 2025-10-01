import React, { useState, useEffect, useMemo } from 'react'
import { Card, Row, Col, Input, Space, Typography, Spin, Empty, Segmented, Divider, message } from 'antd'
import {
  SearchOutlined,
  AppstoreOutlined,
  UnorderedListOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import MarketplaceCard from '@/components/marketplace/MarketplaceCard'
import TemplatePreviewModal from '@/components/common/TemplatePreviewModal'
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal'
import { useCreateRepository } from '@/api/queries/repositories'
import { configService } from '@/services/configService'

const { Title, Text } = Typography
const { Search } = Input

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

interface CategoryGroup {
  key: string
  title: string
  description: string
  templates: Template[]
}

const MarketplacePage: React.FC = () => {
  const { t } = useTranslation(['marketplace', 'resources', 'common'])
  const navigate = useNavigate()
  const styles = useComponentStyles()
  // const { data: dropdownData } = useDropdownData() // Not used in marketplace
  const createRepositoryMutation = useCreateRepository()
  
  const [loading, setLoading] = useState(true)
  const [templates, setTemplates] = useState<Template[]>([])
  const [searchTerm, setSearchTerm] = useState('')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [previewTemplate, setPreviewTemplate] = useState<Template | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [deployingTemplate, setDeployingTemplate] = useState<Template | null>(null)

  // Fetch templates
  useEffect(() => {
    fetchTemplates()
  }, [])

  const fetchTemplates = async () => {
    try {
      setLoading(true)
      const templatesUrl = await configService.getTemplatesUrl()
      const response = await fetch(templatesUrl)
      if (!response.ok) throw new Error('Failed to fetch templates')

      const data = await response.json()
      // Enhance templates with marketplace metadata
      const enhancedTemplates = (data.templates || []).map((template: any) => ({
        ...template,
        // Use backend category, fallback to deriving from ID if not provided
        category: template.category || getTemplateCategoryFromId(template.id),
        tags: getTemplateTags(template.id, template.readme),
        difficulty: getTemplateDifficulty(template.id),
        iconUrl: `${window.location.origin}/configs/template_${template.id}_icon.svg`
      }))
      setTemplates(enhancedTemplates)
    } catch (err) {
      console.error('Failed to fetch templates:', err)
      message.error('Unable to load templates. Please check your connection.')
    } finally {
      setLoading(false)
    }
  }

  // Helper function to derive category from template ID (fallback only)
  const getTemplateCategoryFromId = (id: string): string => {
    // Extract category from ID format: "category_name"
    const parts = id.split('_')
    if (parts.length >= 2) {
      return parts[0] // First part is the category
    }
    return 'other'
  }

  const getTemplateTags = (id: string, readme: string): string[] => {
    const tags = []
    const lowerId = id.toLowerCase()
    const lowerReadme = readme.toLowerCase()

    // Technology tags
    if (lowerId.includes('mysql')) tags.push('MySQL')
    if (lowerId.includes('postgres')) tags.push('PostgreSQL')
    if (lowerId.includes('mongo')) tags.push('MongoDB')
    if (lowerId.includes('redis')) tags.push('Redis')
    if (lowerId.includes('nginx')) tags.push('Nginx')
    if (lowerId.includes('wordpress')) tags.push('WordPress')
    if (lowerId.includes('docker')) tags.push('Docker')

    // Use case tags
    if (lowerReadme.includes('production')) tags.push('Production Ready')
    if (lowerReadme.includes('development')) tags.push('Development')
    if (lowerReadme.includes('high availability')) tags.push('HA')
    if (lowerReadme.includes('cluster')) tags.push('Clustered')

    return tags
  }

  const getTemplateDifficulty = (id: string): 'beginner' | 'intermediate' | 'advanced' => {
    if (['networking_nginx', 'databases_mysql', 'caching_redis'].includes(id)) return 'beginner'
    if (['monitoring_prometheus-grafana', 'messaging_kafka', 'security_keycloak'].includes(id)) return 'advanced'
    return 'intermediate'
  }

  // Auto-generate category metadata from category key (fully maintainable)
  const getCategoryMetadata = (categoryKey: string) => {
    // Convert category key to readable label: "api-gateway" → "Api Gateway"
    const label = categoryKey
      .split(/[-_]/)
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ')

    return {
      label,
      description: `${label} templates and solutions`
    }
  }


  // Group templates by category - dynamically generated from actual templates
  const categoryGroups = useMemo((): CategoryGroup[] => {
    // Filter templates based on search
    const filteredTemplates = templates.filter(template => {
      if (searchTerm) {
        const search = searchTerm.toLowerCase()
        return template.name.toLowerCase().includes(search) ||
               template.readme.toLowerCase().includes(search) ||
               (template.tags || []).some(tag => tag.toLowerCase().includes(search))
      }
      return true
    })

    // Dynamically build groups based on templates' categories
    const groups: Record<string, CategoryGroup> = {}

    filteredTemplates.forEach(template => {
      const categoryKey = template.category || 'other'

      if (!groups[categoryKey]) {
        const metadata = getCategoryMetadata(categoryKey)
        groups[categoryKey] = {
          key: categoryKey,
          title: metadata.label,
          description: metadata.description,
          templates: []
        }
      }

      groups[categoryKey].templates.push(template)
    })

    // Return all groups with templates, sorted by key
    return Object.values(groups).sort((a, b) => a.key.localeCompare(b.key))
  }, [templates, searchTerm, t])

  const handleDeployTemplate = (template: Template) => {
    setDeployingTemplate(template)
    setShowCreateModal(true)
  }

  const handleCreateRepository = async (data: any) => {
    try {
      await createRepositoryMutation.mutateAsync(data)
      message.success(t('resources:repository.created'))
      setShowCreateModal(false)
      setDeployingTemplate(null)
      
      // Optionally navigate to resources page to see the new repository
      setTimeout(() => {
        navigate('/resources')
      }, 1000)
    } catch (error) {
      message.error(t('resources:repository.createError'))
    }
  }

  return (
    <div>
      {/* Header */}
      <Row gutter={[24, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24}>
          <Space direction="vertical" size="small" style={{ width: '100%' }}>
            <Title level={2} style={{ ...styles.heading2, margin: 0 }}>
              {t('marketplace:title')}
            </Title>
            <Text type="secondary">
              {t('marketplace:subtitle')}
            </Text>
          </Space>
        </Col>
      </Row>

      {/* Search and Controls */}
      <Row gutter={[16, 16]} style={{ marginBottom: 32 }}>
        <Col xs={24} sm={12} md={8}>
          <Search
            placeholder={t('marketplace:searchPlaceholder')}
            allowClear
            size="large"
            style={styles.inputLarge}
            prefix={<SearchOutlined />}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            autoComplete="off"
            data-testid="marketplace-search-input"
          />
        </Col>
        <Col xs={24} sm={12} md={16}>
          <Space style={{ width: '100%', justifyContent: 'flex-end' }} wrap>
            <Segmented
              value={viewMode}
              onChange={setViewMode as any}
              options={[
                { value: 'grid', icon: <AppstoreOutlined /> },
                { value: 'list', icon: <UnorderedListOutlined /> }
              ]}
              data-testid="marketplace-view-mode-toggle"
            />
          </Space>
        </Col>
      </Row>

      {/* Main Content - Templates by Category */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '60px 0' }} data-testid="marketplace-loading">
          <Spin size="large" />
          <div style={{ marginTop: 16, color: 'var(--ant-color-text-secondary)' }}>
            {t('marketplace:loading')}
          </div>
        </div>
      ) : categoryGroups.length === 0 ? (
        <Card style={styles.card} data-testid="marketplace-empty-state">
          <Empty
            description={
              searchTerm ? (
                <Space direction="vertical" align="center" size="middle" style={{ textAlign: 'center' }}>
                  <Text>{t('marketplace:noTemplatesFound')}</Text>
                  <Text type="secondary" style={{ fontSize: 14 }}>
                    Try adjusting your search terms or browse all available templates
                  </Text>
                  <Space>
                    <button 
                      type="button"
                      onClick={() => setSearchTerm('')}
                      style={{
                        ...styles.buttonPrimary,
                        ...styles.touchTarget,
                        background: 'var(--color-primary)',
                        color: 'white',
                        border: 'none'
                      }}
                      data-testid="marketplace-clear-search"
                    >
                      Clear Search
                    </button>
                    <button 
                      type="button"
                      onClick={() => navigate('/resources')}
                      style={{
                        ...styles.buttonSecondary,
                        ...styles.touchTarget,
                        background: 'transparent',
                        color: 'var(--color-primary)',
                        border: '1px solid var(--color-primary)'
                      }}
                      data-testid="marketplace-view-resources"
                    >
                      View My Resources
                    </button>
                  </Space>
                </Space>
              ) : (
                <Space direction="vertical" align="center" size="middle" style={{ textAlign: 'center' }}>
                  <Text>No templates available at this time</Text>
                  <Text type="secondary" style={{ fontSize: 14 }}>
                    Marketplace templates are currently being loaded or configured
                  </Text>
                  <Space>
                    <button 
                      type="button"
                      onClick={() => fetchTemplates()}
                      style={{
                        ...styles.buttonPrimary,
                        ...styles.touchTarget,
                        background: 'var(--color-primary)',
                        color: 'white',
                        border: 'none'
                      }}
                      data-testid="marketplace-refresh"
                    >
                      Refresh Templates
                    </button>
                    <button 
                      type="button"
                      onClick={() => navigate('/resources')}
                      style={{
                        ...styles.buttonSecondary,
                        ...styles.touchTarget,
                        background: 'transparent',
                        color: 'var(--color-primary)',
                        border: '1px solid var(--color-primary)'
                      }}
                      data-testid="marketplace-create-resource"
                    >
                      Create Custom Resource
                    </button>
                  </Space>
                </Space>
              )
            }
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        </Card>
      ) : (
        <div>
          {categoryGroups.map((group, index) => (
            <div key={group.key} style={{ marginBottom: 48 }} data-testid={`marketplace-category-${group.key}`}>
              {/* Category Header */}
              <div style={{ marginBottom: 16 }}>
                <div>
                  <Title level={4} style={{ margin: 0 }}>{group.title}</Title>
                  <Text type="secondary">{group.description}</Text>
                </div>
              </div>
              
              {/* Templates in this category */}
              <Row gutter={[16, 16]}>
                {group.templates.map(template => (
                  <Col 
                    key={template.name} 
                    xs={24} 
                    sm={viewMode === 'list' ? 24 : 12} 
                    lg={viewMode === 'list' ? 24 : 8}
                    xl={viewMode === 'list' ? 24 : 6}
                  >
                    <MarketplaceCard
                      template={template}
                      viewMode={viewMode}
                      onDeploy={() => handleDeployTemplate(template)}
                      onPreview={() => {
                        setPreviewTemplate(template)
                        setShowPreview(true)
                      }}
                      data-testid={`marketplace-card-${template.name}`}
                    />
                  </Col>
                ))}
              </Row>
              
              {/* Divider between categories */}
              {index < categoryGroups.length - 1 && (
                <Divider style={{ marginTop: 32 }} />
              )}
            </div>
          ))}
        </div>
      )}

      {/* Preview Modal */}
      {previewTemplate && (
        <TemplatePreviewModal
          template={previewTemplate}
          visible={showPreview}
          onClose={() => {
            setShowPreview(false)
            setPreviewTemplate(null)
          }}
          onUseTemplate={(template) => {
            handleDeployTemplate(template as Template)
            setShowPreview(false)
          }}
          context="marketplace"
        />
      )}

      {/* Create Repository Modal */}
      {showCreateModal && deployingTemplate && (
        <UnifiedResourceModal
          open={showCreateModal}
          onCancel={() => {
            setShowCreateModal(false)
            setDeployingTemplate(null)
          }}
          resourceType="repository"
          mode="create"
          existingData={{
            preselectedTemplate: deployingTemplate.name
          }}
          onSubmit={handleCreateRepository}
          isSubmitting={createRepositoryMutation.isPending}
        />
      )}
    </div>
  )
}

export default MarketplacePage