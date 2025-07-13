import React, { useState, useMemo } from 'react'
import { Select, Space, Tag, Input } from 'antd'
import { TeamOutlined, SearchOutlined } from '@/utils/optimizedIcons'
import type { Team } from '@/api/queries/teams'

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
      value: team.teamName
    }))
  }, [teams, searchValue])

  return (
    <Select
      mode="multiple"
      style={{ width: '100%', ...style }}
      placeholder={placeholder}
      value={selectedTeams}
      onChange={onChange}
      loading={loading}
      options={filteredOptions}
      filterOption={false}
      showSearch
      searchValue={searchValue}
      onSearch={setSearchValue}
      tagRender={(props) => {
        const { label, value, closable, onClose } = props
        return (
          <Tag
            color="#8FBC8F"
            closable={closable}
            onClose={onClose}
            style={{ marginRight: 3 }}
          >
            {value}
          </Tag>
        )
      }}
      dropdownRender={(menu) => (
        <>
          <div style={{ padding: '8px 12px' }}>
            <Input
              placeholder="Search teams by name..."
              prefix={<SearchOutlined />}
              value={searchValue}
              onChange={e => setSearchValue(e.target.value)}
              onPressEnter={e => e.stopPropagation()}
              autoComplete="off"
            />
          </div>
          <div style={{ borderTop: '1px solid #f0f0f0' }}>
            {menu}
          </div>
        </>
      )}
      maxTagCount='responsive'
      maxTagPlaceholder={(omittedValues) => (
        <Tag color="#8FBC8F">+{omittedValues.length} more</Tag>
      )}
    />
  )
}

export default TeamSelector