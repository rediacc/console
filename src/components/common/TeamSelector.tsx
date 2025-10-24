import React, { useState, useMemo } from 'react'
import { Select, Space, Tag, Input } from 'antd'
import { TeamOutlined, SearchOutlined } from '@/utils/optimizedIcons'
import type { Team } from '@/api/queries/teams'
import { DESIGN_TOKENS, spacing, borderRadius } from '@/utils/styleConstants'
import { useTranslation } from 'react-i18next'

interface TeamSelectorProps {
  teams: Team[]
  selectedTeams: string[]
  onChange: (selectedTeams: string[]) => void
  loading?: boolean
  placeholder?: string
  style?: React.CSSProperties
}

const TeamSelector: React.FC<TeamSelectorProps> = ({
  teams,
  selectedTeams,
  onChange,
  loading = false,
  placeholder = 'Select teams...',
  style
}) => {
  const { t } = useTranslation('resources')
  const [searchValue, setSearchValue] = useState('')

  const filteredOptions = useMemo(() => {
    const filtered = teams.filter(team =>
      team.teamName.toLowerCase().includes(searchValue.toLowerCase())
    )
    
    return filtered.map(team => ({
      label: (
        <Space>
          <TeamOutlined style={{ color: '#556b2f' }} />
          <span>{team.teamName}</span>
        </Space>
      ),
      value: team.teamName,
      'data-testid': `team-selector-option-${team.teamName}`
    }))
  }, [teams, searchValue])

  return (
    <Select
      mode="multiple"
      style={{ 
        width: '100%',
        // Don't apply input styles to Select - it has different DOM structure
        ...style 
      }}
      placeholder={placeholder}
      value={selectedTeams}
      onChange={onChange}
      loading={loading}
      options={filteredOptions}
      filterOption={false}
      showSearch
      searchValue={searchValue}
      onSearch={setSearchValue}
      data-testid="team-selector"
      tagRender={(props) => {
        const { value, closable, onClose } = props
        return (
          <Tag
            color="var(--color-primary)"
            closable={closable}
            onClose={onClose}
            style={{ 
              marginRight: spacing('XS'),
              borderRadius: borderRadius('SM'),
              // Remove minHeight - let content determine height
              display: 'inline-flex',
              alignItems: 'center'
            }}
            data-testid={`team-selector-tag-${value}`}
          >
            {value}
          </Tag>
        )
      }}
      popupRender={(menu) => (
        <>
          <div style={{ padding: spacing('SM') }}>
            <Input
              placeholder={t('teams.placeholders.searchTeams')}
              prefix={<SearchOutlined style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.BASE }} />}
              value={searchValue}
              onChange={e => setSearchValue(e.target.value)}
              onPressEnter={e => e.stopPropagation()}
              autoComplete="off"
              style={{
                // Input inside dropdown - let it use default styles
              }}
              data-testid="team-selector-search"
            />
          </div>
          <div style={{ borderTop: '1px solid var(--color-border-secondary)' }}>
            {menu}
          </div>
        </>
      )}
      maxTagCount='responsive'
      maxTagPlaceholder={(omittedValues) => (
        <Tag 
          color="var(--color-primary)" 
          style={{ 
            borderRadius: borderRadius('SM'),
            // Remove minHeight - let content determine height
            display: 'inline-flex',
            alignItems: 'center'
          }}
          data-testid="team-selector-more-tag"
        >
          +{omittedValues.length} more
        </Tag>
      )}
    />
  )
}

export default TeamSelector