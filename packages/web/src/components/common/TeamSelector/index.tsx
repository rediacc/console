import React, { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { Team } from '@/api/queries/teams';
import { TeamOutlined, SearchOutlined } from '@/utils/optimizedIcons';
import {
  TeamSelect,
  TeamTag,
  DropdownSearchContainer,
  DropdownMenuWrapper,
  SearchInput,
  OptionLabel,
  OptionIcon,
} from './styles';

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
        <OptionLabel>
          <OptionIcon>
            <TeamOutlined />
          </OptionIcon>
          <span>{team.teamName}</span>
        </OptionLabel>
      ),
      value: team.teamName,
      'data-testid': `team-selector-option-${team.teamName}`,
    }));
  }, [teams, searchValue]);

  return (
    <TeamSelect
      mode="multiple"
      size="sm"
      style={style}
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
          <TeamTag closable={closable} onClose={onClose} data-testid={`team-selector-tag-${value}`}>
            {value}
          </TeamTag>
        );
      }}
      dropdownRender={(menu: React.ReactElement) => (
        <>
          <DropdownSearchContainer>
            <SearchInput
              placeholder={t('teams.placeholders.searchTeams')}
              prefix={<SearchOutlined />}
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value)}
              onPressEnter={(e) => e.stopPropagation()}
              autoComplete="off"
              data-testid="team-selector-search"
            />
          </DropdownSearchContainer>
          <DropdownMenuWrapper>{menu}</DropdownMenuWrapper>
        </>
      )}
      maxTagCount="responsive"
      maxTagPlaceholder={(omittedValues: unknown[]) => (
        <TeamTag data-testid="team-selector-more-tag">+{omittedValues.length} more</TeamTag>
      )}
    />
  );
};

export default TeamSelector;
