import React, { useMemo, useState } from 'react';
import { Flex, Input, Select, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { SearchOutlined, TeamOutlined } from '@/utils/optimizedIcons';
import type { GetOrganizationTeams_ResultSet1 } from '@rediacc/shared/types';

interface TeamSelectorProps {
  teams: GetOrganizationTeams_ResultSet1[];
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
        <Flex align="center" className="flex w-full gap-2 pr-6">
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
      mode="multiple"
      className="w-full"
      // eslint-disable-next-line no-restricted-syntax
      style={style}
      placeholder={placeholder ?? t('common:teamSelector.selectTeams')}
      value={selectedTeams}
      onChange={(values) => onChange(values)}
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
            className="inline-flex items-center"
            closable={closable}
            onClose={onClose}
            data-testid={`team-selector-tag-${value}`}
          >
            {value}
          </Tag>
        );
      }}
      popupRender={(menu: React.ReactElement) => (
        <Flex gap={8} vertical>
          <Flex className="w-full">
            <Input
              className="flex w-full"
              placeholder={t('teams.placeholders.searchTeams')}
              prefix={<SearchOutlined />}
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value)}
              onPressEnter={(e) => e.stopPropagation()}
              autoComplete="off"
              data-testid="team-selector-search"
            />
          </Flex>
          <Flex gap={2} className="[&_.ant-select-item-option-state]:ml-2">
            {menu}
          </Flex>
        </Flex>
      )}
      maxTagCount="responsive"
      maxTagPlaceholder={(omittedValues: unknown[]) => (
        <Tag className="inline-flex items-center" data-testid="team-selector-more-tag">
          {t('common:teamSelector.moreTeams', { count: omittedValues.length })}
        </Tag>
      )}
    />
  );
};

export default TeamSelector;
