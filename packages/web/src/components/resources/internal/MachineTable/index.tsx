import React, { useState, useMemo, useCallback, useRef } from 'react';
import { Table, Button, Space, Tooltip, Empty } from 'antd';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { useMachines } from '@/api/queries/machines';
import { useRepos } from '@/api/queries/repos';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { MachineVaultStatusPanel } from '@/components/resources/internal/MachineVaultStatusPanel';
import { RediaccEmpty } from '@/components/ui';
import { featureFlags } from '@/config/featureFlags';
import { useDialogState, useTraceModal } from '@/hooks/useDialogState';
import { useDynamicPageSize } from '@/hooks/useDynamicPageSize';
import { AssignToClusterModal } from '@/pages/ceph/components/AssignToClusterModal';
import { RemoveFromClusterModal } from '@/pages/ceph/components/RemoveFromClusterModal';
import { ViewAssignmentStatusModal } from '@/pages/ceph/components/ViewAssignmentStatusModal';
import { RemoteFileBrowserModal } from '@/pages/resources/components/RemoteFileBrowserModal';
import { getMachineRepos as coreGetMachineRepos } from '@/platform';
import { useLocalizedFunctions } from '@/services/functionsService';
import { usePingFunction } from '@/services/pingService';
import { RootState } from '@/store/store';
import type { Machine } from '@/types';
import {
  InboxOutlined,
  TeamOutlined,
  GlobalOutlined,
  CloudServerOutlined,
  BranchesOutlined,
  DesktopOutlined,
  DashboardOutlined,
  RightOutlined,
  InfoCircleOutlined,
} from '@/utils/optimizedIcons';
import type { DeployedRepo } from '@rediacc/shared/services/machine';
import { buildMachineTableColumns } from './columns';
import {
  MachineTableWrapper,
  TableContainer,
  BulkActionsBar,
  BulkActionsSummary,
  ViewToggleContainer,
  ViewToggleButton,
  ViewToggleDivider,
  GroupedCardStack,
  GroupCardContainer,
  GroupCardHeader,
  GroupCardIndicator,
  GroupCardTitle,
  GroupCardCount,
  GroupCardRow,
  GroupRowContent,
  GroupRowIcon,
  GroupRowInfo,
  GroupRowName,
  GroupRowActionButton,
  GroupHeaderTag,
  StyledTag,
} from './styles';
import type { MachineFunctionAction } from './columns';
// Local type for group variants - maps to preset prop
type GroupVariant = 'repo' | 'bridge' | 'team' | 'region' | 'status' | 'grand';

type GroupByMode = 'machine' | 'bridge' | 'team' | 'region' | 'repo' | 'status' | 'grand';

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
  selectedMachine: externalSelectedMachine,
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
  const { data: repos = [] } = useRepos(teamFilter);

  // Dynamic page size
  const dynamicPageSize = useDynamicPageSize(tableContainerRef, {
    containerOffset: 170, // Account for filters, tabs, and other UI elements
    minRows: 5,
    maxRows: 50,
  });

  // Use machines directly without filtering
  const filteredMachines = machines;

  // Parse machine vault status to get repo information
  // Uses core vault-status parser with repo name resolution
  const getMachineRepos = useCallback(
    (machine: Machine): DeployedRepo[] => {
      return coreGetMachineRepos(
        machine,
        repos.map((r) => ({
          repoGuid: r.repoGuid,
          repoName: r.repoName,
          grandGuid: r.grandGuid,
        }))
      );
    },
    [repos]
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
      <BulkActionsBar>
        <Space size="middle">
          <BulkActionsSummary>
            {t('machines:bulkActions.selected', { count: selectedRowKeys.length })}
          </BulkActionsSummary>
          <Tooltip title={t('common:actions.clearSelection')}>
            <Button
              size="small"
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
      </BulkActionsBar>
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
      <ViewToggleContainer>
        <Space wrap size="small">
          <Tooltip title={t('machines:machine')}>
            <ViewToggleButton
              variant={groupBy === 'machine' ? 'primary' : 'default'}
              icon={<DesktopOutlined />}
              onClick={() => setGroupBy('machine')}
              data-testid="machine-view-toggle-machine"
              aria-label={t('machines:machine')}
            />
          </Tooltip>

          <ViewToggleDivider />

          <Tooltip title={t('machines:groupByBridge')}>
            <ViewToggleButton
              variant={groupBy === 'bridge' ? 'primary' : 'default'}
              icon={<CloudServerOutlined />}
              onClick={() => setGroupBy('bridge')}
              data-testid="machine-view-toggle-bridge"
              aria-label={t('machines:groupByBridge')}
            />
          </Tooltip>

          <Tooltip title={t('machines:groupByTeam')}>
            <ViewToggleButton
              variant={groupBy === 'team' ? 'primary' : 'default'}
              icon={<TeamOutlined />}
              onClick={() => setGroupBy('team')}
              data-testid="machine-view-toggle-team"
              aria-label={t('machines:groupByTeam')}
            />
          </Tooltip>

          {isExpertMode && (
            <Tooltip title={t('machines:groupByRegion')}>
              <ViewToggleButton
                variant={groupBy === 'region' ? 'primary' : 'default'}
                icon={<GlobalOutlined />}
                onClick={() => setGroupBy('region')}
                data-testid="machine-view-toggle-region"
                aria-label={t('machines:groupByRegion')}
              />
            </Tooltip>
          )}

          <Tooltip title={t('machines:groupByRepo')}>
            <ViewToggleButton
              variant={groupBy === 'repo' ? 'primary' : 'default'}
              icon={<InboxOutlined />}
              onClick={() => setGroupBy('repo')}
              data-testid="machine-view-toggle-repo"
              aria-label={t('machines:groupByRepo')}
            />
          </Tooltip>

          <Tooltip title={t('machines:groupByStatus')}>
            <ViewToggleButton
              variant={groupBy === 'status' ? 'primary' : 'default'}
              icon={<DashboardOutlined />}
              onClick={() => setGroupBy('status')}
              data-testid="machine-view-toggle-status"
              aria-label={t('machines:groupByStatus')}
            />
          </Tooltip>

          <Tooltip title={t('machines:groupByGrand')}>
            <ViewToggleButton
              variant={groupBy === 'grand' ? 'primary' : 'default'}
              icon={<BranchesOutlined />}
              onClick={() => setGroupBy('grand')}
              data-testid="machine-view-toggle-grand"
              aria-label={t('machines:groupByGrand')}
            />
          </Tooltip>
        </Space>
      </ViewToggleContainer>
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
      } else if (groupBy === 'repo') {
        // For repo grouping, we'll handle this differently
        const machineRepos = getMachineRepos(machine);
        if (machineRepos.length === 0) {
          // Skip machines without repos
          return;
        }
        // Add machine to each repo it has
        machineRepos.forEach((repo) => {
          const repoKey = repo.name;
          if (!result[repoKey]) result[repoKey] = [];
          if (!result[repoKey].find((m) => m.machineName === machine.machineName)) {
            result[repoKey].push(machine);
          }
        });
        return;
      } else if (groupBy === 'status') {
        const machineRepos = getMachineRepos(machine);
        if (machineRepos.length === 0) {
          key = 'No Repos';
        } else {
          // Priority-based status assignment
          const hasInaccessible = machineRepos.some((r) => !r.accessible);
          const hasRunning = machineRepos.some((r) => r.mounted && r.docker_running);
          const hasStopped = machineRepos.some((r) => r.mounted && !r.docker_running);
          const hasUnmounted = machineRepos.some((r) => !r.mounted);

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
        // Group by grand repo
        const machineRepos = getMachineRepos(machine);
        if (machineRepos.length === 0) return;

        machineRepos.forEach((repo) => {
          let grandKey = 'No Grand Repo';
          if (repo.grandGuid) {
            const grandRepo = repos.find((r) => r.repoGuid === repo.grandGuid);
            if (grandRepo) {
              grandKey = grandRepo.repoName;
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
  }, [filteredMachines, groupBy, repos, getMachineRepos]);

  // Render grouped table view
  const renderGroupedTableView = () => {
    if (Object.keys(groupedMachinesForTable).length === 0) {
      return (
        <RediaccEmpty
          variant="minimal"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t('resources:repos.noRepos')}
          style={{ marginTop: 64 }}
        />
      );
    }

    const variantMap: Record<GroupByMode, GroupVariant> = {
      machine: 'repo',
      bridge: 'bridge',
      team: 'team',
      region: 'region',
      repo: 'repo',
      status: 'status',
      grand: 'grand',
    };

    const indicatorColors: Record<GroupVariant, string> = {
      team: 'var(--color-success)',
      bridge: 'var(--color-primary)',
      region: 'var(--color-info)',
      repo: 'var(--color-secondary)',
      status: 'var(--color-warning)',
      grand: 'var(--color-secondary)',
    };

    const iconMap: Partial<Record<GroupByMode, React.ReactNode>> = {
      bridge: <CloudServerOutlined />,
      team: <TeamOutlined />,
      region: <GlobalOutlined />,
      repo: <InboxOutlined />,
      status: <DashboardOutlined />,
      grand: <BranchesOutlined />,
    };

    return (
      <GroupedCardStack>
        {Object.entries(groupedMachinesForTable).map(([groupKey, machines], groupIndex) => {
          const variant = variantMap[groupBy];
          const indicatorColor = indicatorColors[variant];

          return (
            <GroupCardContainer key={groupKey} $isAlternate={groupIndex % 2 === 0}>
              <GroupCardHeader>
                <GroupCardIndicator $color={indicatorColor} />
                <Space size="small">
                  <GroupCardTitle>#{groupIndex + 1}</GroupCardTitle>
                  <GroupHeaderTag $variant={variant} icon={iconMap[groupBy]}>
                    {groupKey}
                  </GroupHeaderTag>
                  <GroupCardCount>
                    {machines.length}{' '}
                    {machines.length === 1 ? t('machines:machine') : t('machines:machines')}
                  </GroupCardCount>
                </Space>
              </GroupCardHeader>

              {machines.map((machine, index) => (
                <GroupCardRow
                  key={machine.machineName}
                  $isStriped={index % 2 !== 0}
                  onClick={() =>
                    navigate(`/machines/${machine.machineName}/repos`, { state: { machine } })
                  }
                  data-testid={`grouped-machine-row-${machine.machineName}`}
                >
                  <GroupRowContent>
                    <GroupRowIcon />
                    <GroupRowInfo>
                      <GroupRowName>{machine.machineName}</GroupRowName>
                      <Space size="small">
                        <StyledTag $variant="team">{machine.teamName}</StyledTag>
                        {machine.bridgeName && (
                          <StyledTag $variant="bridge">{machine.bridgeName}</StyledTag>
                        )}
                        {machine.regionName && (
                          <StyledTag $variant="region">{machine.regionName}</StyledTag>
                        )}
                      </Space>
                    </GroupRowInfo>
                  </GroupRowContent>

                  <Tooltip title={t('machines:viewRepos')}>
                    <GroupRowActionButton
                      variant="primary"
                      icon={<RightOutlined />}
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/machines/${machine.machineName}/repos`, { state: { machine } });
                      }}
                    >
                      {t('machines:viewRepos')}
                    </GroupRowActionButton>
                  </Tooltip>
                </GroupCardRow>
              ))}
            </GroupCardContainer>
          );
        })}
      </GroupedCardStack>
    );
  };

  return (
    <MachineTableWrapper className={className}>
      {renderViewToggle()}
      {renderBulkActionsToolbar()}

      {groupBy === 'machine' ? (
        <TableContainer ref={tableContainerRef}>
          <Table
            columns={columns}
            dataSource={filteredMachines}
            rowKey="machineName"
            loading={isLoading}
            scroll={{ x: 'max-content' }}
            rowSelection={rowSelection}
            rowClassName={(record) => {
              const isSelected = externalSelectedMachine?.machineName === record.machineName;
              const baseClass = 'machine-table-row';
              return isSelected ? `${baseClass} machine-table-row--selected` : baseClass;
            }}
            data-testid="machine-table"
            pagination={{
              pageSize: dynamicPageSize,
              showSizeChanger: false,
              showTotal: (total, range) =>
                t('common:table.showingRecords', { start: range[0], end: range[1], total }),
            }}
            onRow={(record) => ({
              'data-testid': `machine-row-${record.machineName}`,
              onClick: (e) => {
                const target = e.target as HTMLElement;
                if (
                  target.closest('button') ||
                  target.closest('.ant-dropdown') ||
                  target.closest('.ant-dropdown-menu')
                ) {
                  return;
                }

                navigate(`/machines/${record.machineName}/repos`, {
                  state: { machine: record },
                });
              },
            })}
            sticky
          />
        </TableContainer>
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
    </MachineTableWrapper>
  );
};
