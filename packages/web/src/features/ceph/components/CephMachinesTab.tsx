import { Button, Card, Col, Flex, Input, Row, Select, Space, Typography } from 'antd';
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import { useGetTeamMachines } from '@/api/api-hooks.generated';
import { AssignToClusterModal } from '@/features/ceph/components/modals/AssignToClusterModal';
import { RemoveFromClusterModal } from '@/features/ceph/components/modals/RemoveFromClusterModal';
import { ViewAssignmentStatusModal } from '@/features/ceph/components/modals/ViewAssignmentStatusModal';
import { useDialogState } from '@/hooks/useDialogState';
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

interface CephMachinesTabProps {
  teamFilter?: string | string[];
}

type AssignmentFilter = 'all' | 'available' | 'cluster' | 'image' | 'clone';

export const CephMachinesTab: React.FC<CephMachinesTabProps> = ({ teamFilter }) => {
  const { t } = useTranslation(['ceph', 'machines', 'common']);
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
  const { data: allMachines = [], isLoading, refetch } = useGetTeamMachines(teamFilter?.[0]);

  // Filter machines based on search and assignment status
  const filteredMachines = React.useMemo(() => {
    // Ensure allMachines is always an array (already guaranteed by default value)
    if (!Array.isArray(allMachines)) {
      return [];
    }

    let filtered = allMachines;

    // Apply search filter
    if (searchText) {
      filtered = filtered.filter(
        (machine: Machine) =>
          (machine.machineName ?? '').toLowerCase().includes(searchText.toLowerCase()) ||
          (machine.teamName ?? '').toLowerCase().includes(searchText.toLowerCase()) ||
          (machine.bridgeName ?? '').toLowerCase().includes(searchText.toLowerCase())
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
    void refetch();
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
        machine.cephClusterName ?? '',
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
      <Flex align="center" justify="space-between">
        <Space>
          <Typography.Text>
            {t('machines:bulkActions.selected', { count: selectedMachines.length })}
          </Typography.Text>
          <Button onClick={() => setSelectedMachines([])} data-testid="ds-machines-clear-selection">
            {t('common:actions.clearSelection')}
          </Button>
        </Space>
        <Space>
          <Button
            type="primary"
            icon={<CloudServerOutlined />}
            onClick={() => setBulkAssignClusterModal(true)}
            data-testid="ds-machines-bulk-assign-cluster"
          >
            {t('machines:bulkActions.assignToCluster')}
          </Button>
          <Button
            icon={<CloudServerOutlined />}
            onClick={() => setRemoveFromClusterModal(true)}
            data-testid="ds-machines-bulk-remove-cluster"
          >
            {t('machines:bulkActions.removeFromCluster')}
          </Button>
          <Button
            icon={<InfoCircleOutlined />}
            onClick={() => setViewAssignmentStatusModal(true)}
            data-testid="ds-machines-bulk-view-status"
          >
            {t('machines:bulkActions.viewAssignmentStatus')}
          </Button>
        </Space>
      </Flex>
    );
  };

  return (
    <>
      {/* Summary Statistics */}
      <MachineAvailabilitySummary teamFilter={teamFilter} onRefresh={handleRefresh} />

      {/* Filters and Actions */}
      <Card>
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} sm={12} lg={8}>
            <Input.Search
              placeholder={t('machines.filters.searchPlaceholder')}
              value={searchText}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearchText(e.target.value)}
              allowClear
              data-testid="ds-machines-search"
            />
          </Col>

          <Col xs={24} sm={12} lg={8}>
            <Select
              placeholder={t('machines.filters.assignmentStatus')}
              value={assignmentFilter}
              onChange={(value) => setAssignmentFilter(value as AssignmentFilter)}
              suffixIcon={<FilterOutlined />}
              data-testid="ds-machines-filter-assignment"
              className="w-full"
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
            <Flex>
              <Space>
                <Button
                  icon={<ExportOutlined />}
                  onClick={handleExport}
                  data-testid="ds-machines-export-button"
                >
                  {t('machines.actions.exportReport')}
                </Button>
              </Space>
            </Flex>
          </Col>
        </Row>
      </Card>

      {/* Bulk Actions Toolbar */}
      {renderBulkActionsToolbar()}

      {/* Machine Table */}
      <Card>
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
          bulkAssignClusterModal
            ? allMachines.filter((m) => selectedMachines.includes(m.machineName ?? ''))
            : undefined
        }
        onSuccess={() => {
          assignClusterModal.close();
          setBulkAssignClusterModal(false);
          setSelectedMachines([]);
          void refetch();
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
          void refetch();
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
