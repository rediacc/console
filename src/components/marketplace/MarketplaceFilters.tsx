import React from 'react'
import { Card, Space, Typography, Select, Tag, Button, Divider, Radio } from 'antd'
import { CloseOutlined, FilterOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing, borderRadius } from '@/utils/styleConstants'

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
  const styles = useComponentStyles()

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
    <Card 
      data-testid="marketplace-filter-container"
      style={{
        ...styles.card,
        borderRadius: borderRadius('LG'),
        boxShadow: DESIGN_TOKENS.SHADOWS.CARD
      }}
    >
      <Space direction="vertical" size={spacing('LG')} style={{ width: '100%' }}>
        {/* Header */}
        <div style={styles.flexBetween}>
          <Space size={spacing('SM')}>
            <FilterOutlined style={styles.icon.medium} />
            <Title level={5} style={{ ...styles.heading5, margin: 0 }}>{t('filters')}</Title>
          </Space>
          {hasActiveFilters && (
            <Button 
              type="link" 
              onClick={onClearAll}
              icon={<CloseOutlined />}
              data-testid="marketplace-filter-clear-all"
              style={{
                ...styles.buttonGhost,
                height: 'auto',
                padding: `${spacing('XS')}px ${spacing('SM')}px`,
                fontSize: DESIGN_TOKENS.FONT_SIZE.SM
              }}
            >
              {t('clearAll')}
            </Button>
          )}
        </div>

        <Divider style={{ margin: `${spacing('SM')}px 0` }} />

        {/* Category Filter */}
        <Space direction="vertical" size={spacing('SM')} style={{ width: '100%' }}>
          <Text strong style={styles.label}>{t('filterByCategory')}</Text>
          <Radio.Group 
            value={selectedCategory} 
            onChange={(e) => onCategoryChange(e.target.value)}
            style={{ width: '100%' }}
            data-testid="marketplace-filter-category"
          >
            <Space direction="vertical" size={spacing('XS')} style={{ width: '100%' }}>
              <Radio 
                value="" 
                data-testid="marketplace-filter-category-all"
                style={{ 
                  minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
                  display: 'flex',
                  alignItems: 'center'
                }}
              >
                {t('allCategories')}
              </Radio>
              {categoryOptions.map(option => (
                <Radio 
                  key={option.value} 
                  value={option.value} 
                  data-testid={`marketplace-filter-category-${option.value}`}
                  style={{ 
                    minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
                    display: 'flex',
                    alignItems: 'center'
                  }}
                >
                  {option.label}
                </Radio>
              ))}
            </Space>
          </Radio.Group>
        </Space>

        <Divider style={{ margin: `${spacing('SM')}px 0` }} />

        {/* Difficulty Filter */}
        <Space direction="vertical" size={spacing('SM')} style={{ width: '100%' }}>
          <Text strong style={styles.label}>{t('filterByDifficulty')}</Text>
          <Radio.Group 
            value={selectedDifficulty} 
            onChange={(e) => onDifficultyChange(e.target.value)}
            style={{ width: '100%' }}
            data-testid="marketplace-filter-difficulty"
          >
            <Space direction="vertical" size={spacing('XS')} style={{ width: '100%' }}>
              <Radio 
                value="" 
                data-testid="marketplace-filter-difficulty-all"
                style={{ 
                  minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
                  display: 'flex',
                  alignItems: 'center'
                }}
              >
                {t('allDifficulties')}
              </Radio>
              {difficultyOptions.map(option => (
                <Radio 
                  key={option.value} 
                  value={option.value} 
                  data-testid={`marketplace-filter-difficulty-${option.value}`}
                  style={{ 
                    minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
                    display: 'flex',
                    alignItems: 'center'
                  }}
                >
                  {option.label}
                </Radio>
              ))}
            </Space>
          </Radio.Group>
        </Space>

        <Divider style={{ margin: `${spacing('SM')}px 0` }} />

        {/* Tags Filter */}
        <Space direction="vertical" size={spacing('SM')} style={{ width: '100%' }}>
          <Text strong style={styles.label}>{t('filterByTags')}</Text>
          <Select
            mode="multiple"
            style={{ 
              width: '100%',
              ...styles.input
            }}
            placeholder={t('selectTags')}
            value={selectedTags}
            onChange={onTagsChange}
            options={tags.map(tag => ({ label: tag, value: tag }))}
            maxTagCount="responsive"
            data-testid="marketplace-filter-tags-select"
          />
          {selectedTags.length > 0 && (
            <div style={{ marginTop: spacing('SM') }}>
              <Space wrap size={spacing('XS')}>
                {selectedTags.map(tag => (
                  <Tag 
                    key={tag}
                    closable
                    onClose={() => onTagsChange(selectedTags.filter(t => t !== tag))}
                    data-testid={`marketplace-filter-tag-${tag.toLowerCase().replace(/\s+/g, '-')}`}
                    style={{
                      borderRadius: borderRadius('SM'),
                      fontSize: DESIGN_TOKENS.FONT_SIZE.SM
                    }}
                  >
                    {tag}
                  </Tag>
                ))}
              </Space>
            </div>
          )}
        </Space>

        <Divider style={{ margin: `${spacing('SM')}px 0` }} />

        {/* Popular Filters */}
        <Space direction="vertical" size={spacing('SM')} style={{ width: '100%' }}>
          <Text strong style={styles.label}>{t('popularFilters')}</Text>
          <Space wrap size={spacing('XS')}>
            <Tag.CheckableTag
              checked={selectedTags.includes('Production Ready')}
              onChange={checked => {
                if (checked) {
                  onTagsChange([...selectedTags, 'Production Ready'])
                } else {
                  onTagsChange(selectedTags.filter(t => t !== 'Production Ready'))
                }
              }}
              data-testid="marketplace-filter-popular-production-ready"
              style={{
                minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
                display: 'flex',
                alignItems: 'center',
                borderRadius: borderRadius('SM'),
                fontSize: DESIGN_TOKENS.FONT_SIZE.SM,
                padding: `${spacing('XS')}px ${spacing('SM')}px`
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
              data-testid="marketplace-filter-popular-docker"
              style={{
                minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
                display: 'flex',
                alignItems: 'center',
                borderRadius: borderRadius('SM'),
                fontSize: DESIGN_TOKENS.FONT_SIZE.SM,
                padding: `${spacing('XS')}px ${spacing('SM')}px`
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
              data-testid="marketplace-filter-popular-ha"
              style={{
                minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
                display: 'flex',
                alignItems: 'center',
                borderRadius: borderRadius('SM'),
                fontSize: DESIGN_TOKENS.FONT_SIZE.SM,
                padding: `${spacing('XS')}px ${spacing('SM')}px`
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