import React, { useMemo, useState } from 'react';
import { Flex, Input, Select, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { SearchOutlined, TeamOutlined } from '@/utils/optimizedIcons';
import type { GetCompanyTeams_ResultSet1 as Team } from '@rediacc/shared/types';

interface TeamSelectorProps {
  teams: Team[];
  selectedTeams: string[];
  onChange: (selectedTeams: string[]) => void;
  loading?: boolean;
  placeholder?: string;
  style?: React.CSSProperties;
}

const TeamSelector: React.FC<TeamSelectorProps> = ({
  teams,
  selectedTeams,
  onChange,
  loading = false,
  placeholder = 'Select teams...',
  style,
}: TeamSelectorProps) => {
  const { t } = useTranslation('resources');
  const [searchValue, setSearchValue] = useState('');

  const filteredOptions = useMemo(() => {
    const filtered = teams.filter((team) =>
      team.teamName.toLowerCase().includes(searchValue.toLowerCase())
    );

    return filtered.map((team) => ({
      label: (
        <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
          <Flex align="center" style={{ display: 'inline-flex' }}>
            <TeamOutlined />
          </Flex>
          <Typography.Text>{team.teamName}</Typography.Text>
        </Flex>
      ),
      value: team.teamName,
      'data-testid': `team-selector-option-${team.teamName}`,
    }));
  }, [teams, searchValue]);

  return (
    <Select
      mode="multiple"
      style={{ width: '100%', ...style }}
      placeholder={placeholder}
      value={selectedTeams}
      onChange={(values) => onChange(values as string[])}
      loading={loading}
      options={filteredOptions}
      filterOption={false}
      showSearch
      searchValue={searchValue}
      onSearch={setSearchValue}
      data-testid="team-selector"
      tagRender={(props: { value: string; closable: boolean; onClose: () => void }) => {
        const { value, closable, onClose } = props;
        return (
          <Tag
            color="processing"
            style={{ display: 'inline-flex', alignItems: 'center' }}
            closable={closable}
            onClose={onClose}
            data-testid={`team-selector-tag-${value}`}
          >
            {value}
          </Tag>
        );
      }}
      dropdownRender={(menu: React.ReactElement) => (
        <>
          <Flex>
            <Input
              placeholder={t('teams.placeholders.searchTeams')}
              prefix={<SearchOutlined />}
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value)}
              onPressEnter={(e) => e.stopPropagation()}
              autoComplete="off"
              data-testid="team-selector-search"
            />
          </Flex>
          <Flex>{menu}</Flex>
        </>
      )}
      maxTagCount="responsive"
      maxTagPlaceholder={(omittedValues: unknown[]) => (
        <Tag
          color="processing"
          style={{ display: 'inline-flex', alignItems: 'center' }}
          data-testid="team-selector-more-tag"
        >
          +{omittedValues.length} more
        </Tag>
      )}
    />
  );
};

export default TeamSelector;
