import React from 'react'
import { Col, Tooltip } from 'antd'
import type { TFunction } from 'i18next'
import {
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
  ExportOutlined,
  SearchOutlined,
} from '@/utils/optimizedIcons'
import {
  ToolbarRow,
  ActionButtonGroup,
  ToolbarButton,
  SearchInput,
} from '../styles'

interface MachineControlsProps {
  selectedCount: number
  assignedCount: number
  searchText: string
  isRemoving: boolean
  onAddMachines: () => void
  onRemoveMachines: () => void
  onRefresh: () => void
  onExport: () => void
  onSearchChange: (value: string) => void
  t: TFunction<'distributedStorage' | 'machines' | 'common'>
}

export const MachineControls: React.FC<MachineControlsProps> = ({
  selectedCount,
  assignedCount,
  searchText,
  isRemoving,
  onAddMachines,
  onRemoveMachines,
  onRefresh,
  onExport,
  onSearchChange,
  t,
}) => (
  <ToolbarRow gutter={16} align="middle">
    <Col flex="auto">
      <ActionButtonGroup>
        <Tooltip title={t('machines:assignToClone')}>
          <ToolbarButton
            type="primary"
            icon={<PlusOutlined />}
            onClick={onAddMachines}
            data-testid="clone-manager-button-add"
            aria-label={t('machines:assignToClone')}
          />
        </Tooltip>
        {selectedCount > 0 && (
          <Tooltip
            title={`${t('machines:removeFromClone')} (${selectedCount})`}
          >
            <ToolbarButton
              danger
              icon={<DeleteOutlined />}
              onClick={onRemoveMachines}
              loading={isRemoving}
              data-testid="clone-manager-button-remove"
              aria-label={`${t('machines:removeFromClone')} (${selectedCount})`}
            />
          </Tooltip>
        )}
        <Tooltip title={t('common:actions.refresh')}>
          <ToolbarButton
            icon={<ReloadOutlined />}
            onClick={onRefresh}
            data-testid="clone-manager-button-refresh"
            aria-label={t('common:actions.refresh')}
          />
        </Tooltip>
        <Tooltip title={t('common:actions.export')}>
          <ToolbarButton
            icon={<ExportOutlined />}
            onClick={onExport}
            disabled={assignedCount === 0}
            data-testid="clone-manager-button-export"
            aria-label={t('common:actions.export')}
          />
        </Tooltip>
      </ActionButtonGroup>
    </Col>
    <Col>
      <SearchInput
        placeholder={t('machines:searchPlaceholder')}
        allowClear
        enterButton={<SearchOutlined />}
        size="middle"
        value={searchText}
        onSearch={onSearchChange}
        onChange={(event) => onSearchChange(event.target.value)}
        data-testid="clone-manager-search-input"
      />
    </Col>
  </ToolbarRow>
)
