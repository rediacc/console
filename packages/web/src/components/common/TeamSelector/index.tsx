import React, { useMemo, useState } from 'react';
import { Flex, Input, Select, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { SearchOutlined, TeamOutlined } from '@/utils/optimizedIcons';
import type { GetOrganizationTeams_ResultSet1 } from '@rediacc/shared/types';

interface TeamSelectorProps {
  teams: GetOrganizationTeams_ResultSet1[];
  selectedTeam: string | null;
  onChange: (team: string | null) => void;
  loading?: boolean;
  placeholder?: string;
  style?: React.CSSProperties;
}

const TeamSelector: React.FC<TeamSelectorProps> = ({
  teams,
  selectedTeam,
  onChange,
  loading = false,
  placeholder,
  style,
}: TeamSelectorProps) => {
  const { t } = useTranslation(['resources', 'common']);
  const [searchValue, setSearchValue] = useState('');

  const filteredOptions = useMemo(() => {
    const filtered = teams.filter((team) =>
      (team.teamName ?? '').toLowerCase().includes(searchValue.toLowerCase())
    );

    return filtered.map((team) => ({
      label: (
        <Flex align="center" wrap className="inline-flex">
          <Flex align="center" className="inline-flex">
            <TeamOutlined />
          </Flex>
          <Typography.Text>{team.teamName ?? ''}</Typography.Text>
        </Flex>
      ),
      value: team.teamName ?? '',
      'data-testid': `team-selector-option-${team.teamName ?? ''}`,
    }));
  }, [teams, searchValue]);

  return (
    <Select
      className="w-full"
      // eslint-disable-next-line no-restricted-syntax
      style={style}
      placeholder={placeholder ?? t('common:teamSelector.selectTeam')}
      value={selectedTeam}
      onChange={(value) => onChange(value)}
      loading={loading}
      options={filteredOptions}
      filterOption={false}
      showSearch
      searchValue={searchValue}
      onSearch={setSearchValue}
      data-testid="team-selector"
      popupRender={(menu: React.ReactElement) => (
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
    />
  );
};

export default TeamSelector;
