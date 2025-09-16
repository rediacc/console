import React, { useState, useEffect, useMemo } from 'react'
import { Card, Row, Col, Input, Space, Typography, Spin, Empty, Segmented, Divider, message } from 'antd'
import { 
  SearchOutlined, 
  AppstoreOutlined, 
  UnorderedListOutlined,
  DatabaseOutlined,
  RocketOutlined,
  MonitorOutlined,
  HddOutlined,
  MessageOutlined,
  SafetyOutlined,
  SearchOutlined as SearchIconOutlined,
  CodeOutlined,
  ControlOutlined,
  ApiOutlined,
  CloudOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import MarketplaceCard from '@/components/marketplace/MarketplaceCard'
import MarketplacePreview from '@/components/marketplace/MarketplacePreview'
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal'
import { useDropdownData } from '@/api/queries/useDropdownData'
import { useCreateRepository } from '@/api/queries/repositories'

const { Title, Text } = Typography
const { Search } = Input

interface Template {
  name: string
  readme: string
  category?: string
  tags?: string[]
  difficulty?: 'beginner' | 'intermediate' | 'advanced'
  iconUrl?: string
}

interface CategoryGroup {
  key: string
  title: string
  icon: React.ReactNode
  description: string
  templates: Template[]
}

const MarketplacePage: React.FC = () => {
  const { t } = useTranslation(['marketplace', 'resources', 'common'])
  const navigate = useNavigate()
  const styles = useComponentStyles()
  const { data: dropdownData } = useDropdownData()
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
      const response = await fetch(`${window.location.origin}/config/templates.json`)
      if (!response.ok) throw new Error('Failed to fetch templates')
      
      const data = await response.json()
      // Enhance templates with marketplace metadata
      const enhancedTemplates = (data.templates || []).map((template: Template) => ({
        ...template,
        category: getTemplateCategory(template.name),
        tags: getTemplateTags(template.name, template.readme),
        difficulty: getTemplateDifficulty(template.name),
        iconUrl: `${window.location.origin}/config/template_${template.name}_icon.svg`
      }))
      setTemplates(enhancedTemplates)
    } catch (err) {
      // Error fetching templates
    } finally {
      setLoading(false)
    }
  }

  // Helper functions for template metadata
  const getTemplateCategory = (name: string): string => {
    if (name.startsWith('db_')) return 'databases'
    if (name.startsWith('kick_')) return 'quickstart'
    if (name.startsWith('monitor_')) return 'monitoring'
    if (name.startsWith('cache_')) return 'caching'
    if (name.startsWith('queue_')) return 'messaging'
    if (name.startsWith('auth_')) return 'authentication'
    if (name.startsWith('search_')) return 'search'
    if (name.startsWith('dev_')) return 'development'
    if (name.startsWith('manage_')) return 'management'
    if (name.startsWith('api_')) return 'api'
    if (name.startsWith('route_')) return 'networking'
    return 'other'
  }

  const getTemplateTags = (name: string, readme: string): string[] => {
    const tags = []
    const lowerName = name.toLowerCase()
    const lowerReadme = readme.toLowerCase()
    
    // Technology tags
    if (lowerName.includes('mysql')) tags.push('MySQL')
    if (lowerName.includes('postgres')) tags.push('PostgreSQL')
    if (lowerName.includes('mongo')) tags.push('MongoDB')
    if (lowerName.includes('redis')) tags.push('Redis')
    if (lowerName.includes('nginx')) tags.push('Nginx')
    if (lowerName.includes('wordpress')) tags.push('WordPress')
    if (lowerName.includes('docker')) tags.push('Docker')
    
    // Use case tags
    if (lowerReadme.includes('production')) tags.push('Production Ready')
    if (lowerReadme.includes('development')) tags.push('Development')
    if (lowerReadme.includes('high availability')) tags.push('HA')
    if (lowerReadme.includes('cluster')) tags.push('Clustered')
    
    return tags
  }

  const getTemplateDifficulty = (name: string): 'beginner' | 'intermediate' | 'advanced' => {
    if (['kick_nginx', 'db_mysql', 'cache_redis'].includes(name)) return 'beginner'
    if (['monitor_prometheus_grafana', 'queue_kafka', 'auth_keycloak'].includes(name)) return 'advanced'
    return 'intermediate'
  }


  // Group templates by category
  const categoryGroups = useMemo((): CategoryGroup[] => {
    const groups: Record<string, CategoryGroup> = {
      databases: {
        key: 'databases',
        title: t('marketplace:category.databases'),
        icon: <DatabaseOutlined />,
        description: t('marketplace:category.databases.description', 'Database systems for data storage and management'),
        templates: []
      },
      quickstart: {
        key: 'quickstart',
        title: t('marketplace:category.quickstart'),
        icon: <RocketOutlined />,
        description: t('marketplace:category.quickstart.description', 'Quick start templates to get you up and running'),
        templates: []
      },
      monitoring: {
        key: 'monitoring',
        title: t('marketplace:category.monitoring'),
        icon: <MonitorOutlined />,
        description: t('marketplace:category.monitoring.description', 'Monitoring and observability solutions'),
        templates: []
      },
      caching: {
        key: 'caching',
        title: t('marketplace:category.caching'),
        icon: <HddOutlined />,
        description: t('marketplace:category.caching.description', 'In-memory caching solutions'),
        templates: []
      },
      messaging: {
        key: 'messaging',
        title: t('marketplace:category.messaging'),
        icon: <MessageOutlined />,
        description: t('marketplace:category.messaging.description', 'Message queuing and streaming platforms'),
        templates: []
      },
      authentication: {
        key: 'authentication',
        title: t('marketplace:category.authentication'),
        icon: <SafetyOutlined />,
        description: t('marketplace:category.authentication.description', 'Authentication and authorization services'),
        templates: []
      },
      search: {
        key: 'search',
        title: t('marketplace:category.search'),
        icon: <SearchIconOutlined />,
        description: t('marketplace:category.search.description', 'Search engines and indexing solutions'),
        templates: []
      },
      development: {
        key: 'development',
        title: t('marketplace:category.development'),
        icon: <CodeOutlined />,
        description: t('marketplace:category.development.description', 'Development tools and platforms'),
        templates: []
      },
      management: {
        key: 'management',
        title: t('marketplace:category.management'),
        icon: <ControlOutlined />,
        description: t('marketplace:category.management.description', 'Infrastructure management tools'),
        templates: []
      },
      api: {
        key: 'api',
        title: t('marketplace:category.api'),
        icon: <ApiOutlined />,
        description: t('marketplace:category.api.description', 'API gateways and management'),
        templates: []
      },
      networking: {
        key: 'networking',
        title: t('marketplace:category.networking'),
        icon: <CloudOutlined />,
        description: t('marketplace:category.networking.description', 'Networking and routing solutions'),
        templates: []
      }
    }

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

    // Group filtered templates
    filteredTemplates.forEach(template => {
      const category = template.category || 'other'
      if (groups[category]) {
        groups[category].templates.push(template)
      }
    })

    // Return only groups with templates
    return Object.values(groups).filter(group => group.templates.length > 0)
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
                <Space align="center" size="middle">
                  <span style={{ fontSize: 24, color: '#1890ff' }}>{group.icon}</span>
                  <div>
                    <Title level={4} style={{ margin: 0 }}>{group.title}</Title>
                    <Text type="secondary">{group.description}</Text>
                  </div>
                </Space>
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
        <MarketplacePreview
          template={previewTemplate}
          visible={showPreview}
          onClose={() => {
            setShowPreview(false)
            setPreviewTemplate(null)
          }}
          onDeploy={() => {
            handleDeployTemplate(previewTemplate)
            setShowPreview(false)
          }}
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