import React, { useCallback, useMemo, useRef, useState } from 'react';
import { Button, Empty, Flex, Space, Tag, Tooltip, Typography, type MenuProps } from 'antd';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { useMachines } from '@/api/queries/machines';
import { useRepositories } from '@/api/queries/repositories';
import { RemoteFileBrowserModal } from '@/components/common';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { MobileCard } from '@/components/common/MobileCard';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import ResourceListView from '@/components/common/ResourceListView';
import { MachineVaultStatusPanel } from '@/components/resources/internal/MachineVaultStatusPanel';
import { featureFlags } from '@/config/featureFlags';
import { AssignToClusterModal } from '@/features/ceph/components/modals/AssignToClusterModal';
import { RemoveFromClusterModal } from '@/features/ceph/components/modals/RemoveFromClusterModal';
import { ViewAssignmentStatusModal } from '@/features/ceph/components/modals/ViewAssignmentStatusModal';
import { useDialogState, useTraceModal } from '@/hooks/useDialogState';
import { useDynamicPageSize } from '@/hooks/useDynamicPageSize';
import { getMachineRepositories as coreGetMachineRepositories } from '@/platform';
import { useLocalizedFunctions } from '@/services/functionsService';
import { usePingFunction } from '@/services/pingService';
import { RootState } from '@/store/store';
import type { Machine } from '@/types';
import {
  BranchesOutlined,
  CloudServerOutlined,
  DashboardOutlined,
  DeleteOutlined,
  DesktopOutlined,
  EditOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  FunctionOutlined,
  GlobalOutlined,
  HistoryOutlined,
  InboxOutlined,
  InfoCircleOutlined,
  TeamOutlined,
} from '@/utils/optimizedIcons';
import type { DeployedRepo } from '@rediacc/shared/services/machine';
import { buildMachineTableColumns, type MachineFunctionAction } from './columns';
import { GroupedMachineCard } from './components/GroupedMachineCard';

type GroupByMode = 'machine' | 'bridge' | 'team' | 'region' | 'repository' | 'status' | 'grand';

interface MachineTableProps {
  teamFilter?: string | string[];
  showActions?: boolean;
  className?: string;
  onCreateMachine?: () => void;
  onEditMachine?: (machine: Machine) => void;
  onVaultMachine?: (machine: Machine) => void;
  onFunctionsMachine?: (machine: Machine, functionName?: string) => void;
  onDeleteMachine?: (machine: Machine) => void;
  enabled?: boolean;
  onQueueItemCreated?: (taskId: string, machineName: string) => void;
  onRowClick?: (machine: Machine) => void;
  selectedMachine?: Machine | null;
}

export const MachineTable: React.FC<MachineTableProps> = ({
  teamFilter,
  showActions = true,
  className = '',
  onEditMachine,
  onFunctionsMachine,
  onDeleteMachine,
  enabled = true,
  onQueueItemCreated,
  onRowClick,
  selectedMachine: _externalSelectedMachine,
}) => {
  const { t } = useTranslation(['machines', 'common', 'functions', 'resources']);
  const navigate = useNavigate();
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const isExpertMode = uiMode === 'expert';
  const { executePingForMachineAndWait } = usePingFunction();
  // Ref for table container
  const tableContainerRef = useRef<HTMLDivElement>(null);

  // State management
  const [groupBy, setGroupBy] = useState<GroupByMode>('machine');

  // Bulk selection state
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const auditTrace = useTraceModal();
  const remoteFileBrowserModal = useDialogState<Machine>();
  const assignClusterModal = useDialogState<Machine>();

  const [bulkAssignClusterModal, setBulkAssignClusterModal] = useState(false);
  const [removeFromClusterModal, setRemoveFromClusterModal] = useState(false);
  const [viewAssignmentStatusModal, setViewAssignmentStatusModal] = useState(false);

  const [selectedMachine, setSelectedMachine] = useState<Machine | null>(null);
  const [vaultPanelVisible, setVaultPanelVisible] = useState(false);

  // Reset to 'machine' view when entering Simple mode
  React.useEffect(() => {
    if (uiMode === 'simple' && groupBy !== 'machine') {
      setGroupBy('machine');
    }
  }, [uiMode, groupBy]);

  // Queries only - mutations are handled by parent
  const { data: machines = [], isLoading, refetch } = useMachines(teamFilter, enabled);
  const { data: repositories = [] } = useRepositories(teamFilter);

  // Dynamic page size
  const dynamicPageSize = useDynamicPageSize(tableContainerRef, {
    containerOffset: 170, // Account for filters, tabs, and other UI elements
    minRows: 5,
    maxRows: 50,
  });

  // Use machines directly without filtering
  const filteredMachines = machines;

  // Parse machine vault status to get repository information
  // Uses core vault-status parser with repository name resolution
  const getMachineRepositories = useCallback(
    (machine: Machine): DeployedRepo[] => {
      return coreGetMachineRepositories(
        machine,
        repositories.map((r) => ({
          repositoryGuid: r.repositoryGuid,
          repositoryName: r.repositoryName,
          grandGuid: r.grandGuid,
        }))
      );
    },
    [repositories]
  );

  const handleDelete = useCallback(
    (machine: Machine) => {
      if (onDeleteMachine) {
        onDeleteMachine(machine);
      }
    },
    [onDeleteMachine]
  );

  const handleRowClick = useCallback(
    (machine: Machine) => {
      if (onRowClick) {
        onRowClick(machine);
      } else {
        setSelectedMachine(machine);
        setVaultPanelVisible(true);
      }
    },
    [onRowClick]
  );

  const handlePanelClose = useCallback(() => {
    setVaultPanelVisible(false);
    // Clear selected machine immediately - no delays
    setSelectedMachine(null);
  }, []);

  // Get machine functions
  const { getFunctionsByCategory } = useLocalizedFunctions();
  const machineFunctions = useMemo(
    () =>
      getFunctionsByCategory('machine').filter(
        (func) => func && func.showInMenu !== false && func.name !== 'mount' && func.name !== 'pull'
      ),
    [getFunctionsByCategory]
  ) as MachineFunctionAction[];

  const canAssignToCluster = isExpertMode && featureFlags.isEnabled('assignToCluster');

  // Wrapper functions for column builder compatibility
  const openAssignClusterModal = useCallback(
    (state: { open: boolean; machine: Machine | null }) => {
      if (state.open && state.machine) {
        assignClusterModal.open(state.machine);
      } else {
        assignClusterModal.close();
      }
    },
    [assignClusterModal]
  );

  const openAuditTraceModal = useCallback(
    (state: {
      open: boolean;
      entityType: string | null;
      entityIdentifier: string | null;
      entityName?: string;
    }) => {
      if (state.open && state.entityType && state.entityIdentifier) {
        auditTrace.open({
          entityType: state.entityType,
          entityIdentifier: state.entityIdentifier,
          entityName: state.entityName,
        });
      } else {
        auditTrace.close();
      }
    },
    [auditTrace]
  );

  const columns = React.useMemo(
    () =>
      buildMachineTableColumns({
        t,
        isExpertMode,
        uiMode,
        showActions,
        hasSplitView: Boolean(onRowClick),
        canAssignToCluster,
        onEditMachine,
        onFunctionsMachine,
        handleDelete,
        handleRowClick,
        onViewRepositories: (machine) =>
          navigate(`/machines/${machine.machineName}/repositories`, { state: { machine } }),
        executePingForMachineAndWait,
        setAssignClusterModal: openAssignClusterModal,
        setAuditTraceModal: openAuditTraceModal,
        machineFunctions,
      }),
    [
      t,
      isExpertMode,
      uiMode,
      showActions,
      onRowClick,
      canAssignToCluster,
      onEditMachine,
      onFunctionsMachine,
      handleDelete,
      handleRowClick,
      navigate,
      executePingForMachineAndWait,
      openAssignClusterModal,
      openAuditTraceModal,
      machineFunctions,
    ]
  );

  // Row selection configuration - only show checkboxes if assignToCluster feature is enabled
  const rowSelection = canAssignToCluster
    ? {
        selectedRowKeys,
        onChange: (newSelectedRowKeys: React.Key[]) => {
          setSelectedRowKeys(newSelectedRowKeys as string[]);
        },
        getCheckboxProps: (record: Machine) => ({
          disabled: false, // Can be customized based on machine status
          'data-testid': `machine-checkbox-${record.machineName}`,
        }),
      }
    : undefined;

  // Render bulk actions toolbar - only if feature is enabled
  const renderBulkActionsToolbar = () => {
    if (!canAssignToCluster || selectedRowKeys.length === 0) return null;

    return (
      <Flex align="center" justify="space-between" wrap>
        <Space size="middle">
          <Typography.Text>
            {t('machines:bulkActions.selected', { count: selectedRowKeys.length })}
          </Typography.Text>
          <Tooltip title={t('common:actions.clearSelection')}>
            <Button
              onClick={() => setSelectedRowKeys([])}
              data-testid="machine-bulk-clear-selection"
              aria-label={t('common:actions.clearSelection')}
            >
              Clear
            </Button>
          </Tooltip>
        </Space>
        <Space size="middle">
          <Tooltip title={t('machines:bulkActions.assignToCluster')}>
            <Button
              type="primary"
              icon={<CloudServerOutlined />}
              onClick={() => setBulkAssignClusterModal(true)}
              data-testid="machine-bulk-assign-cluster"
              aria-label={t('machines:bulkActions.assignToCluster')}
            />
          </Tooltip>
          <Tooltip title={t('machines:bulkActions.removeFromCluster')}>
            <Button
              icon={<CloudServerOutlined />}
              onClick={() => setRemoveFromClusterModal(true)}
              data-testid="machine-bulk-remove-cluster"
              aria-label={t('machines:bulkActions.removeFromCluster')}
            />
          </Tooltip>
          <Tooltip title={t('machines:bulkActions.viewAssignmentStatus')}>
            <Button
              icon={<InfoCircleOutlined />}
              onClick={() => setViewAssignmentStatusModal(true)}
              data-testid="machine-bulk-view-status"
              aria-label={t('machines:bulkActions.viewAssignmentStatus')}
            />
          </Tooltip>
        </Space>
      </Flex>
    );
  };

  // Render view mode toggle
  const renderViewToggle = () => {
    // In simple mode, hide all grouping buttons
    if (uiMode === 'simple') {
      return null;
    }

    // In expert/normal mode, show all grouping buttons
    return (
      <Flex>
        <Space wrap size="small">
          <Tooltip title={t('machines:machine')}>
            <Button
              // eslint-disable-next-line no-restricted-syntax
              style={{ minWidth: 42 }}
              type={groupBy === 'machine' ? 'primary' : 'default'}
              icon={<DesktopOutlined />}
              onClick={() => setGroupBy('machine')}
              data-testid="machine-view-toggle-machine"
              aria-label={t('machines:machine')}
            />
          </Tooltip>

          <Typography.Text
            // eslint-disable-next-line no-restricted-syntax
            style={{ width: 1, height: 24 }}
          />

          <Tooltip title={t('machines:groupByBridge')}>
            <Button
              // eslint-disable-next-line no-restricted-syntax
              style={{ minWidth: 42 }}
              type={groupBy === 'bridge' ? 'primary' : 'default'}
              icon={<CloudServerOutlined />}
              onClick={() => setGroupBy('bridge')}
              data-testid="machine-view-toggle-bridge"
              aria-label={t('machines:groupByBridge')}
            />
          </Tooltip>

          <Tooltip title={t('machines:groupByTeam')}>
            <Button
              // eslint-disable-next-line no-restricted-syntax
              style={{ minWidth: 42 }}
              type={groupBy === 'team' ? 'primary' : 'default'}
              icon={<TeamOutlined />}
              onClick={() => setGroupBy('team')}
              data-testid="machine-view-toggle-team"
              aria-label={t('machines:groupByTeam')}
            />
          </Tooltip>

          {isExpertMode && (
            <Tooltip title={t('machines:groupByRegion')}>
              <Button
                // eslint-disable-next-line no-restricted-syntax
                style={{ minWidth: 42 }}
                type={groupBy === 'region' ? 'primary' : 'default'}
                icon={<GlobalOutlined />}
                onClick={() => setGroupBy('region')}
                data-testid="machine-view-toggle-region"
                aria-label={t('machines:groupByRegion')}
              />
            </Tooltip>
          )}

          <Tooltip title={t('machines:groupByRepository')}>
            <Button
              // eslint-disable-next-line no-restricted-syntax
              style={{ minWidth: 42 }}
              type={groupBy === 'repository' ? 'primary' : 'default'}
              icon={<InboxOutlined />}
              onClick={() => setGroupBy('repository')}
              data-testid="machine-view-toggle-repo"
              aria-label={t('machines:groupByRepository')}
            />
          </Tooltip>

          <Tooltip title={t('machines:groupByStatus')}>
            <Button
              // eslint-disable-next-line no-restricted-syntax
              style={{ minWidth: 42 }}
              type={groupBy === 'status' ? 'primary' : 'default'}
              icon={<DashboardOutlined />}
              onClick={() => setGroupBy('status')}
              data-testid="machine-view-toggle-status"
              aria-label={t('machines:groupByStatus')}
            />
          </Tooltip>

          <Tooltip title={t('machines:groupByGrand')}>
            <Button
              // eslint-disable-next-line no-restricted-syntax
              style={{ minWidth: 42 }}
              type={groupBy === 'grand' ? 'primary' : 'default'}
              icon={<BranchesOutlined />}
              onClick={() => setGroupBy('grand')}
              data-testid="machine-view-toggle-grand"
              aria-label={t('machines:groupByGrand')}
            />
          </Tooltip>
        </Space>
      </Flex>
    );
  };

  // Render embedded mode alert (removed since we're enabling full functionality)

  // Grouped machines for table view
  const groupedMachinesForTable = useMemo(() => {
    const result: Record<string, Machine[]> = {};

    if (groupBy === 'machine') {
      // Don't group when showing normal machine view
      return result;
    }

    filteredMachines.forEach((machine) => {
      let key = '';
      if (groupBy === 'bridge') {
        key = machine.bridgeName;
      } else if (groupBy === 'team') {
        key = machine.teamName;
      } else if (groupBy === 'region') {
        key = machine.regionName || 'Unknown';
      } else if (groupBy === 'repository') {
        // For repository grouping, we'll handle this differently
        const machineRepositories = getMachineRepositories(machine);
        if (machineRepositories.length === 0) {
          // Skip machines without repositories
          return;
        }
        // Add machine to each repository it has
        machineRepositories.forEach((repository) => {
          const repositoryKey = repository.name;
          if (!result[repositoryKey]) result[repositoryKey] = [];
          if (!result[repositoryKey].find((m) => m.machineName === machine.machineName)) {
            result[repositoryKey].push(machine);
          }
        });
        return;
      } else if (groupBy === 'status') {
        const machineRepositories = getMachineRepositories(machine);
        if (machineRepositories.length === 0) {
          key = 'No Repositories';
        } else {
          // Priority-based status assignment
          const hasInaccessible = machineRepositories.some((r) => !r.accessible);
          const hasRunning = machineRepositories.some((r) => r.mounted && r.docker_running);
          const hasStopped = machineRepositories.some((r) => r.mounted && !r.docker_running);
          const hasUnmounted = machineRepositories.some((r) => !r.mounted);

          if (hasInaccessible) {
            key = 'Inaccessible';
          } else if (hasRunning) {
            key = 'Active (Running)';
          } else if (hasStopped) {
            key = 'Ready (Stopped)';
          } else if (hasUnmounted) {
            key = 'Not Mounted';
          } else {
            key = 'Unknown Status';
          }
        }
      } else if (groupBy === 'grand') {
        // Group by grand repository
        const machineRepositories = getMachineRepositories(machine);
        if (machineRepositories.length === 0) return;

        machineRepositories.forEach((repository) => {
          let grandKey = 'No Grand Repository';
          if (repository.grandGuid) {
            const grandRepository = repositories.find(
              (r) => r.repositoryGuid === repository.grandGuid
            );
            if (grandRepository) {
              grandKey = grandRepository.repositoryName;
            }
          }
          if (!result[grandKey]) result[grandKey] = [];
          if (!result[grandKey].find((m) => m.machineName === machine.machineName)) {
            result[grandKey].push(machine);
          }
        });
        return;
      }

      // Add machine to result for non-special grouping types
      if (key) {
        if (!result[key]) result[key] = [];
        result[key].push(machine);
      }
    });

    return result;
  }, [filteredMachines, groupBy, repositories, getMachineRepositories]);

  // Render grouped table view
  const renderGroupedTableView = () => {
    if (Object.keys(groupedMachinesForTable).length === 0) {
      return (
        <Flex>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t('resources:repositories.noRepositories')}
          />
        </Flex>
      );
    }

    return (
      <Flex vertical gap={16}>
        {Object.entries(groupedMachinesForTable).map(([groupKey, groupMachines]) => (
          <GroupedMachineCard
            key={groupKey}
            groupKey={groupKey}
            groupBy={groupBy}
            machines={groupMachines}
            columns={columns}
            mobileRender={mobileRender}
            loading={isLoading}
            pageSize={10}
            rowSelection={rowSelection}
            onRow={(record) =>
              ({
                'data-testid': `machine-row-${record.machineName}`,
              }) as React.HTMLAttributes<HTMLElement>
            }
          />
        ))}
      </Flex>
    );
  };

  const mobileRender = useCallback(
    (record: Machine) => {
      const menuItems: MenuProps['items'] = [
        {
          key: 'viewRepositories',
          label: t('resources:repositories.repositories'),
          icon: <FolderOpenOutlined />,
          onClick: () =>
            navigate(`/machines/${record.machineName}/repositories`, {
              state: { machine: record },
            }),
        },
        {
          key: 'viewDetails',
          label: t('resources:audit.details'),
          icon: <EyeOutlined />,
          onClick: () => handleRowClick(record),
        },
        { type: 'divider' as const },
        ...(onEditMachine
          ? [
              {
                key: 'edit',
                label: t('common:actions.edit'),
                icon: <EditOutlined />,
                onClick: () => onEditMachine(record),
              },
            ]
          : []),
        ...(onFunctionsMachine
          ? [
              {
                key: 'functions',
                label: t('machines:functions'),
                icon: <FunctionOutlined />,
                onClick: () => onFunctionsMachine(record),
              },
            ]
          : []),
        {
          key: 'trace',
          label: t('resources:audit.trace'),
          icon: <HistoryOutlined />,
          onClick: () =>
            auditTrace.open({
              entityType: 'Machine',
              entityIdentifier: record.machineName,
              entityName: record.machineName,
            }),
        },
        ...(handleDelete
          ? [
              { type: 'divider' as const },
              {
                key: 'delete',
                label: t('common:actions.delete'),
                icon: <DeleteOutlined />,
                danger: true,
                onClick: () => handleDelete(record),
              },
            ]
          : []),
      ];

      return (
        <MobileCard actions={<ResourceActionsDropdown menuItems={menuItems} />}>
          <Space>
            <DesktopOutlined />
            <Typography.Text strong className="truncate">
              {record.machineName}
            </Typography.Text>
          </Space>
          <Flex gap={8} wrap>
            <Tag>{record.teamName}</Tag>
            {record.bridgeName && <Tag>{record.bridgeName}</Tag>}
            {record.regionName && <Tag>{record.regionName}</Tag>}
          </Flex>
        </MobileCard>
      );
    },
    [t, navigate, onEditMachine, onFunctionsMachine, handleDelete, auditTrace, handleRowClick]
  );

  return (
    <Flex vertical className={`h-full ${className}`}>
      {renderViewToggle()}
      {renderBulkActionsToolbar()}

      {groupBy === 'machine' ? (
        <Flex vertical ref={tableContainerRef} className="flex-1 overflow-hidden">
          <ResourceListView<Machine>
            loading={isLoading}
            data={filteredMachines}
            columns={columns}
            rowKey="machineName"
            rowSelection={rowSelection}
            mobileRender={mobileRender}
            pagination={{
              pageSize: dynamicPageSize,
              showSizeChanger: false,
              showTotal: (total, range) =>
                t('common:table.showingRecords', { start: range[0], end: range[1], total }),
            }}
            onRow={(record) =>
              ({
                'data-testid': `machine-row-${record.machineName}`,
              }) as React.HTMLAttributes<HTMLElement>
            }
          />
        </Flex>
      ) : (
        renderGroupedTableView()
      )}

      {/* Modals */}
      <AuditTraceModal
        open={auditTrace.isOpen}
        onCancel={auditTrace.close}
        entityType={auditTrace.entityType}
        entityIdentifier={auditTrace.entityIdentifier}
        entityName={auditTrace.entityName}
      />

      {remoteFileBrowserModal.state.data && (
        <RemoteFileBrowserModal
          open={remoteFileBrowserModal.isOpen}
          onCancel={remoteFileBrowserModal.close}
          machineName={remoteFileBrowserModal.state.data.machineName}
          teamName={remoteFileBrowserModal.state.data.teamName}
          bridgeName={remoteFileBrowserModal.state.data.bridgeName}
          onQueueItemCreated={onQueueItemCreated}
        />
      )}

      {/* Assign to Cluster Modal */}
      {assignClusterModal.state.data && (
        <AssignToClusterModal
          open={assignClusterModal.isOpen}
          machine={assignClusterModal.state.data}
          onCancel={assignClusterModal.close}
          onSuccess={() => {
            assignClusterModal.close();
            refetch();
          }}
        />
      )}

      {/* Bulk Assign to Cluster Modal */}
      <AssignToClusterModal
        open={bulkAssignClusterModal}
        machines={machines.filter((m) => selectedRowKeys.includes(m.machineName))}
        onCancel={() => setBulkAssignClusterModal(false)}
        onSuccess={() => {
          setBulkAssignClusterModal(false);
          setSelectedRowKeys([]);
          refetch();
        }}
      />

      {/* Remove from Cluster Modal */}
      <RemoveFromClusterModal
        open={removeFromClusterModal}
        machines={machines.filter((m) => selectedRowKeys.includes(m.machineName))}
        onCancel={() => setRemoveFromClusterModal(false)}
        onSuccess={() => {
          setRemoveFromClusterModal(false);
          setSelectedRowKeys([]);
          refetch();
        }}
      />

      {/* View Assignment Status Modal */}
      <ViewAssignmentStatusModal
        open={viewAssignmentStatusModal}
        machines={machines.filter((m) => selectedRowKeys.includes(m.machineName))}
        onCancel={() => setViewAssignmentStatusModal(false)}
      />

      {/* Machine Vault Status Panel - only show in standalone mode */}
      {!onRowClick && (
        <MachineVaultStatusPanel
          machine={selectedMachine}
          visible={vaultPanelVisible}
          onClose={handlePanelClose}
        />
      )}
    </Flex>
  );
};
