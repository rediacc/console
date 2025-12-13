import React, { useState } from 'react';
import { Card, Col, Row, Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import { useMachines } from '@/api/queries/machines';
import { RediaccButton, RediaccSearchInput } from '@/components/ui';
import { useComponentStyles } from '@/hooks/useComponentStyles';
import { useDialogState } from '@/hooks/useDialogState';
import { AssignToClusterModal } from '@/pages/ceph/components/AssignToClusterModal';
import { RemoveFromClusterModal } from '@/pages/ceph/components/RemoveFromClusterModal';
import { ViewAssignmentStatusModal } from '@/pages/ceph/components/ViewAssignmentStatusModal';
import { RootState } from '@/store/store';
import { Machine } from '@/types';
import { showMessage } from '@/utils/messages';
import {
  CloudServerOutlined,
  ExportOutlined,
  FilterOutlined,
  InfoCircleOutlined,
} from '@/utils/optimizedIcons';
import { FilterableMachineTable } from './FilterableMachineTable';
import { MachineAvailabilitySummary } from './MachineAvailabilitySummary';
import {
  BulkActionsToolbar,
  BulkActionsLabel,
  RightAlignedCol,
  FiltersCard,
  FullWidthSelect,
} from './styles';


interface CephMachinesTabProps {
  teamFilter?: string | string[];
}

type AssignmentFilter = 'all' | 'available' | 'cluster' | 'image' | 'clone';

export const CephMachinesTab: React.FC<CephMachinesTabProps> = ({ teamFilter }) => {
  const { t } = useTranslation(['ceph', 'machines', 'common']);
  const componentStyles = useComponentStyles();
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const isExpertMode = uiMode === 'expert';

  // State
  const [searchText, setSearchText] = useState('');
  const [assignmentFilter, setAssignmentFilter] = useState<AssignmentFilter>('all');
  const [selectedMachines, setSelectedMachines] = useState<string[]>([]);
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([]);
  const [refreshKeys, setRefreshKeys] = useState<Record<string, number>>({});

  // Modal states
  const assignClusterModal = useDialogState<Machine>();

  const [bulkAssignClusterModal, setBulkAssignClusterModal] = useState(false);
  const [removeFromClusterModal, setRemoveFromClusterModal] = useState(false);
  const [viewAssignmentStatusModal, setViewAssignmentStatusModal] = useState(false);

  // Queries
  const { data: allMachines = [], isLoading, refetch } = useMachines(teamFilter);

  // Filter machines based on search and assignment status
  const filteredMachines = React.useMemo(() => {
    // Ensure allMachines is always an array
    if (!allMachines || !Array.isArray(allMachines)) {
      return [];
    }

    let filtered = allMachines;

    // Apply search filter
    if (searchText) {
      filtered = filtered.filter(
        (machine: Machine) =>
          machine.machineName.toLowerCase().includes(searchText.toLowerCase()) ||
          machine.teamName.toLowerCase().includes(searchText.toLowerCase()) ||
          machine.bridgeName.toLowerCase().includes(searchText.toLowerCase())
      );
    }

    // Apply assignment filter
    // Note: assignmentStatus is now a simple string ('ASSIGNED' | 'UNASSIGNED')
    if (assignmentFilter !== 'all') {
      filtered = filtered.filter((machine: Machine) => {
        const isAssigned = machine.assignmentStatus === 'ASSIGNED' || !!machine.cephClusterName;
        switch (assignmentFilter) {
          case 'available':
            return !isAssigned;
          case 'cluster':
            return !!machine.cephClusterName;
          case 'image':
            // Image assignments are not currently tracked separately
            return false;
          case 'clone':
            // Clone assignments are not currently tracked separately
            return false;
          default:
            return true;
        }
      });
    }

    return filtered;
  }, [allMachines, searchText, assignmentFilter]);

  // Handlers
  const handleRefresh = () => {
    refetch();
    setRefreshKeys({});
  };

  const handleExport = () => {
    const csvContent = [
      ['Machine Name', 'Team', 'Bridge', 'Assignment Status', 'Assigned To'],
      ...filteredMachines.map((machine: Machine) => [
        machine.machineName,
        machine.teamName,
        machine.bridgeName,
        machine.cephClusterName ? 'Cluster' : 'Available',
        machine.cephClusterName || '',
      ]),
    ]
      .map((row) => row.join(','))
      .join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `ceph-machines-${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    showMessage('success', t('common:export.success'));
  };

  // Render bulk actions toolbar
  const renderBulkActionsToolbar = () => {
    if (!isExpertMode || selectedMachines.length === 0) return null;

    return (
      <BulkActionsToolbar>
        <Space>
          <BulkActionsLabel>
            {t('machines:bulkActions.selected', { count: selectedMachines.length })}
          </BulkActionsLabel>
          <RediaccButton
            onClick={() => setSelectedMachines([])}
            data-testid="ds-machines-clear-selection"
            style={componentStyles.controlSurface}
          >
            {t('common:actions.clearSelection')}
          </RediaccButton>
        </Space>
        <Space>
          <RediaccButton
            variant="primary"
            icon={<CloudServerOutlined />}
            onClick={() => setBulkAssignClusterModal(true)}
            data-testid="ds-machines-bulk-assign-cluster"
            style={componentStyles.controlSurface}
          >
            {t('machines:bulkActions.assignToCluster')}
          </RediaccButton>
          <RediaccButton
            icon={<CloudServerOutlined />}
            onClick={() => setRemoveFromClusterModal(true)}
            data-testid="ds-machines-bulk-remove-cluster"
            style={componentStyles.controlSurface}
          >
            {t('machines:bulkActions.removeFromCluster')}
          </RediaccButton>
          <RediaccButton
            icon={<InfoCircleOutlined />}
            onClick={() => setViewAssignmentStatusModal(true)}
            data-testid="ds-machines-bulk-view-status"
            style={componentStyles.controlSurface}
          >
            {t('machines:bulkActions.viewAssignmentStatus')}
          </RediaccButton>
        </Space>
      </BulkActionsToolbar>
    );
  };

  return (
    <>
      {/* Summary Statistics */}
      <MachineAvailabilitySummary teamFilter={teamFilter} onRefresh={handleRefresh} />

      {/* Filters and Actions */}
      <FiltersCard style={componentStyles.card}>
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} sm={12} lg={8}>
            <RediaccSearchInput
              placeholder={t('machines.filters.searchPlaceholder')}
              value={searchText}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearchText(e.target.value)}
              allowClear
              data-testid="ds-machines-search"
              style={componentStyles.input}
            />
          </Col>

          <Col xs={24} sm={12} lg={8}>
            <FullWidthSelect
              style={componentStyles.input}
              placeholder={t('machines.filters.assignmentStatus')}
              value={assignmentFilter}
              onChange={(value) => setAssignmentFilter(value as AssignmentFilter)}
              suffixIcon={<FilterOutlined />}
              data-testid="ds-machines-filter-assignment"
              options={[
                { value: 'all', label: t('machines.filters.allStatuses') },
                { value: 'available', label: t('assignment.available') },
                { value: 'cluster', label: t('assignment.assignedToCluster') },
                { value: 'image', label: t('assignment.assignedToImage') },
                { value: 'clone', label: t('assignment.assignedToClone') },
              ]}
            />
          </Col>

          <Col xs={24} lg={8}>
            <RightAlignedCol>
              <Space>
                <RediaccButton
                  icon={<ExportOutlined />}
                  onClick={handleExport}
                  data-testid="ds-machines-export-button"
                  style={componentStyles.controlSurface}
                >
                  {t('machines.actions.exportReport')}
                </RediaccButton>
              </Space>
            </RightAlignedCol>
          </Col>
        </Row>
      </FiltersCard>

      {/* Bulk Actions Toolbar */}
      {renderBulkActionsToolbar()}

      {/* Machine Table */}
      <Card style={componentStyles.card}>
        <FilterableMachineTable
          machines={filteredMachines}
          loading={isLoading}
          selectedRowKeys={selectedMachines}
          onSelectionChange={setSelectedMachines}
          showSelection={isExpertMode}
          expandedRowKeys={expandedRowKeys}
          onExpandedRowsChange={setExpandedRowKeys}
          refreshKeys={refreshKeys}
        />
      </Card>

      {/* Modals */}
      <AssignToClusterModal
        open={assignClusterModal.isOpen || bulkAssignClusterModal}
        onCancel={() => {
          assignClusterModal.close();
          setBulkAssignClusterModal(false);
        }}
        machine={assignClusterModal.state.data}
        machines={
          bulkAssignClusterModal && allMachines && Array.isArray(allMachines)
            ? allMachines.filter((m) => selectedMachines.includes(m.machineName))
            : undefined
        }
        onSuccess={() => {
          assignClusterModal.close();
          setBulkAssignClusterModal(false);
          setSelectedMachines([]);
          refetch();
        }}
      />

      <RemoveFromClusterModal
        open={removeFromClusterModal}
        onCancel={() => setRemoveFromClusterModal(false)}
        selectedMachines={selectedMachines}
        allMachines={allMachines}
        onSuccess={() => {
          setRemoveFromClusterModal(false);
          setSelectedMachines([]);
          refetch();
        }}
      />

      <ViewAssignmentStatusModal
        open={viewAssignmentStatusModal}
        onCancel={() => setViewAssignmentStatusModal(false)}
        selectedMachines={selectedMachines}
        allMachines={allMachines}
      />
    </>
  );
};
