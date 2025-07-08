import React from 'react'
import { Card, Space, Typography, Select, Tag, Button, Divider, Radio } from 'antd'
import { CloseOutlined, FilterOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'

const { Title, Text } = Typography

interface MarketplaceFiltersProps {
  categories: string[]
  tags: string[]
  selectedCategory: string | null
  selectedTags: string[]
  selectedDifficulty: string | null
  onCategoryChange: (category: string | null) => void
  onTagsChange: (tags: string[]) => void
  onDifficultyChange: (difficulty: string | null) => void
  onClearAll: () => void
}

const MarketplaceFilters: React.FC<MarketplaceFiltersProps> = ({
  categories,
  tags,
  selectedCategory,
  selectedTags,
  selectedDifficulty,
  onCategoryChange,
  onTagsChange,
  onDifficultyChange,
  onClearAll
}) => {
  const { t } = useTranslation('marketplace')

  const hasActiveFilters = selectedCategory || selectedTags.length > 0 || selectedDifficulty

  const categoryOptions = [
    { label: t('category.databases'), value: 'databases' },
    { label: t('category.quickstart'), value: 'quickstart' },
    { label: t('category.monitoring'), value: 'monitoring' },
    { label: t('category.caching'), value: 'caching' },
    { label: t('category.messaging'), value: 'messaging' },
    { label: t('category.authentication'), value: 'authentication' },
    { label: t('category.search'), value: 'search' },
    { label: t('category.development'), value: 'development' },
    { label: t('category.management'), value: 'management' },
    { label: t('category.api'), value: 'api' },
    { label: t('category.other'), value: 'other' }
  ].filter(opt => categories.includes(opt.value))

  const difficultyOptions = [
    { label: t('difficultyBeginner'), value: 'beginner' },
    { label: t('difficultyIntermediate'), value: 'intermediate' },
    { label: t('difficultyAdvanced'), value: 'advanced' }
  ]

  return (
    <Card>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <FilterOutlined />
            <Title level={5} style={{ margin: 0 }}>{t('filters')}</Title>
          </Space>
          {hasActiveFilters && (
            <Button 
              type="link" 
              size="small" 
              onClick={onClearAll}
              icon={<CloseOutlined />}
            >
              {t('clearAll')}
            </Button>
          )}
        </div>

        <Divider style={{ margin: '12px 0' }} />

        {/* Category Filter */}
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          <Text strong>{t('filterByCategory')}</Text>
          <Radio.Group 
            value={selectedCategory} 
            onChange={(e) => onCategoryChange(e.target.value)}
            style={{ width: '100%' }}
          >
            <Space direction="vertical" style={{ width: '100%' }}>
              <Radio value={null}>{t('allCategories')}</Radio>
              {categoryOptions.map(option => (
                <Radio key={option.value} value={option.value}>
                  {option.label}
                </Radio>
              ))}
            </Space>
          </Radio.Group>
        </Space>

        <Divider style={{ margin: '12px 0' }} />

        {/* Difficulty Filter */}
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          <Text strong>{t('filterByDifficulty')}</Text>
          <Radio.Group 
            value={selectedDifficulty} 
            onChange={(e) => onDifficultyChange(e.target.value)}
            style={{ width: '100%' }}
          >
            <Space direction="vertical" style={{ width: '100%' }}>
              <Radio value={null}>{t('allDifficulties')}</Radio>
              {difficultyOptions.map(option => (
                <Radio key={option.value} value={option.value}>
                  {option.label}
                </Radio>
              ))}
            </Space>
          </Radio.Group>
        </Space>

        <Divider style={{ margin: '12px 0' }} />

        {/* Tags Filter */}
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          <Text strong>{t('filterByTags')}</Text>
          <Select
            mode="multiple"
            style={{ width: '100%' }}
            placeholder={t('selectTags')}
            value={selectedTags}
            onChange={onTagsChange}
            options={tags.map(tag => ({ label: tag, value: tag }))}
            maxTagCount="responsive"
          />
          {selectedTags.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <Space wrap size={4}>
                {selectedTags.map(tag => (
                  <Tag 
                    key={tag}
                    closable
                    onClose={() => onTagsChange(selectedTags.filter(t => t !== tag))}
                  >
                    {tag}
                  </Tag>
                ))}
              </Space>
            </div>
          )}
        </Space>

        <Divider style={{ margin: '12px 0' }} />

        {/* Popular Filters */}
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          <Text strong>{t('popularFilters')}</Text>
          <Space wrap>
            <Tag.CheckableTag
              checked={selectedTags.includes('Production Ready')}
              onChange={checked => {
                if (checked) {
                  onTagsChange([...selectedTags, 'Production Ready'])
                } else {
                  onTagsChange(selectedTags.filter(t => t !== 'Production Ready'))
                }
              }}
            >
              {t('productionReady')}
            </Tag.CheckableTag>
            <Tag.CheckableTag
              checked={selectedTags.includes('Docker')}
              onChange={checked => {
                if (checked) {
                  onTagsChange([...selectedTags, 'Docker'])
                } else {
                  onTagsChange(selectedTags.filter(t => t !== 'Docker'))
                }
              }}
            >
              Docker
            </Tag.CheckableTag>
            <Tag.CheckableTag
              checked={selectedTags.includes('HA')}
              onChange={checked => {
                if (checked) {
                  onTagsChange([...selectedTags, 'HA'])
                } else {
                  onTagsChange(selectedTags.filter(t => t !== 'HA'))
                }
              }}
            >
              {t('highAvailability')}
            </Tag.CheckableTag>
          </Space>
        </Space>
      </Space>
    </Card>
  )
}

export default MarketplaceFilters