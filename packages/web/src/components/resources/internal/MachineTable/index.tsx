import React, { useCallback, useMemo, useRef, useState } from 'react';
import { Empty, Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { useMachines } from '@/api/queries/machines';
import { useRepositories } from '@/api/queries/repositories';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { MachineVaultStatusPanel } from '@/components/resources/internal/MachineVaultStatusPanel';
import { RediaccButton, RediaccEmpty, RediaccTable, RediaccTooltip } from '@/components/ui';
import { featureFlags } from '@/config/featureFlags';
import { useDialogState, useTraceModal } from '@/hooks/useDialogState';
import { useDynamicPageSize } from '@/hooks/useDynamicPageSize';
import { AssignToClusterModal } from '@/pages/ceph/components/AssignToClusterModal';
import { RemoveFromClusterModal } from '@/pages/ceph/components/RemoveFromClusterModal';
import { ViewAssignmentStatusModal } from '@/pages/ceph/components/ViewAssignmentStatusModal';
import { RemoteFileBrowserModal } from '@/pages/resources/components/RemoteFileBrowserModal';
import { getMachineRepositories as coreGetMachineRepositories } from '@/platform';
import { useLocalizedFunctions } from '@/services/functionsService';
import { usePingFunction } from '@/services/pingService';
import { RootState } from '@/store/store';
import type { Machine } from '@/types';
import {
  BranchesOutlined,
  CloudServerOutlined,
  DashboardOutlined,
  DesktopOutlined,
  GlobalOutlined,
  InboxOutlined,
  InfoCircleOutlined,
  RightOutlined,
  TeamOutlined,
} from '@/utils/optimizedIcons';
import type { DeployedRepo } from '@rediacc/shared/services/machine';
import { buildMachineTableColumns, type MachineFunctionAction } from './columns';
import {
  BulkActionsBar,
  BulkActionsSummary,
  GroupCardContainer,
  GroupCardCount,
  GroupCardHeader,
  GroupCardIndicator,
  GroupCardRow,
  GroupCardTitle,
  GroupedCardStack,
  GroupHeaderTag,
  GroupRowActionButton,
  GroupRowContent,
  GroupRowIcon,
  GroupRowInfo,
  GroupRowName,
  MachineTableWrapper,
  StyledRediaccEmpty,
  StyledTag,
  TableContainer,
  ViewToggleButton,
  ViewToggleContainer,
  ViewToggleDivider,
} from './styles';

// Local type for group variants - maps to preset prop
type GroupVariant = 'repository' | 'bridge' | 'team' | 'region' | 'status' | 'grand';

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
          <RediaccTooltip title={t('common:actions.clearSelection')}>
            <RediaccButton
              onClick={() => setSelectedRowKeys([])}
              data-testid="machine-bulk-clear-selection"
              aria-label={t('common:actions.clearSelection')}
            >
              Clear
            </RediaccButton>
          </RediaccTooltip>
        </Space>
        <Space size="middle">
          <RediaccTooltip title={t('machines:bulkActions.assignToCluster')}>
            <RediaccButton
              variant="primary"
              icon={<CloudServerOutlined />}
              onClick={() => setBulkAssignClusterModal(true)}
              data-testid="machine-bulk-assign-cluster"
              aria-label={t('machines:bulkActions.assignToCluster')}
            />
          </RediaccTooltip>
          <RediaccTooltip title={t('machines:bulkActions.removeFromCluster')}>
            <RediaccButton
              icon={<CloudServerOutlined />}
              onClick={() => setRemoveFromClusterModal(true)}
              data-testid="machine-bulk-remove-cluster"
              aria-label={t('machines:bulkActions.removeFromCluster')}
            />
          </RediaccTooltip>
          <RediaccTooltip title={t('machines:bulkActions.viewAssignmentStatus')}>
            <RediaccButton
              icon={<InfoCircleOutlined />}
              onClick={() => setViewAssignmentStatusModal(true)}
              data-testid="machine-bulk-view-status"
              aria-label={t('machines:bulkActions.viewAssignmentStatus')}
            />
          </RediaccTooltip>
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
          <RediaccTooltip title={t('machines:machine')}>
            <ViewToggleButton
              variant={groupBy === 'machine' ? 'primary' : 'default'}
              icon={<DesktopOutlined />}
              onClick={() => setGroupBy('machine')}
              data-testid="machine-view-toggle-machine"
              aria-label={t('machines:machine')}
            />
          </RediaccTooltip>

          <ViewToggleDivider />

          <RediaccTooltip title={t('machines:groupByBridge')}>
            <ViewToggleButton
              variant={groupBy === 'bridge' ? 'primary' : 'default'}
              icon={<CloudServerOutlined />}
              onClick={() => setGroupBy('bridge')}
              data-testid="machine-view-toggle-bridge"
              aria-label={t('machines:groupByBridge')}
            />
          </RediaccTooltip>

          <RediaccTooltip title={t('machines:groupByTeam')}>
            <ViewToggleButton
              variant={groupBy === 'team' ? 'primary' : 'default'}
              icon={<TeamOutlined />}
              onClick={() => setGroupBy('team')}
              data-testid="machine-view-toggle-team"
              aria-label={t('machines:groupByTeam')}
            />
          </RediaccTooltip>

          {isExpertMode && (
            <RediaccTooltip title={t('machines:groupByRegion')}>
              <ViewToggleButton
                variant={groupBy === 'region' ? 'primary' : 'default'}
                icon={<GlobalOutlined />}
                onClick={() => setGroupBy('region')}
                data-testid="machine-view-toggle-region"
                aria-label={t('machines:groupByRegion')}
              />
            </RediaccTooltip>
          )}

          <RediaccTooltip title={t('machines:groupByRepo')}>
            <ViewToggleButton
              variant={groupBy === 'repository' ? 'primary' : 'default'}
              icon={<InboxOutlined />}
              onClick={() => setGroupBy('repository')}
              data-testid="machine-view-toggle-repo"
              aria-label={t('machines:groupByRepo')}
            />
          </RediaccTooltip>

          <RediaccTooltip title={t('machines:groupByStatus')}>
            <ViewToggleButton
              variant={groupBy === 'status' ? 'primary' : 'default'}
              icon={<DashboardOutlined />}
              onClick={() => setGroupBy('status')}
              data-testid="machine-view-toggle-status"
              aria-label={t('machines:groupByStatus')}
            />
          </RediaccTooltip>

          <RediaccTooltip title={t('machines:groupByGrand')}>
            <ViewToggleButton
              variant={groupBy === 'grand' ? 'primary' : 'default'}
              icon={<BranchesOutlined />}
              onClick={() => setGroupBy('grand')}
              data-testid="machine-view-toggle-grand"
              aria-label={t('machines:groupByGrand')}
            />
          </RediaccTooltip>
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
        <StyledRediaccEmpty>
          <RediaccEmpty
            variant="minimal"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t('resources:repositories.noRepositories')}
          />
        </StyledRediaccEmpty>
      );
    }

    const variantMap: Record<GroupByMode, GroupVariant> = {
      machine: 'repository',
      bridge: 'bridge',
      team: 'team',
      region: 'region',
      repository: 'repository',
      status: 'status',
      grand: 'grand',
    };

    const indicatorColors: Record<GroupVariant, string> = {
      team: 'var(--color-success)',
      bridge: 'var(--color-primary)',
      region: 'var(--color-info)',
      repository: 'var(--color-secondary)',
      status: 'var(--color-warning)',
      grand: 'var(--color-secondary)',
    };

    const iconMap: Partial<Record<GroupByMode, React.ReactNode>> = {
      bridge: <CloudServerOutlined />,
      team: <TeamOutlined />,
      region: <GlobalOutlined />,
      repository: <InboxOutlined />,
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
                    navigate(`/machines/${machine.machineName}/repositories`, {
                      state: { machine },
                    })
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

                  <RediaccTooltip title={t('machines:viewRepos')}>
                    <GroupRowActionButton
                      variant="primary"
                      icon={<RightOutlined />}
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/machines/${machine.machineName}/repositories`, {
                          state: { machine },
                        });
                      }}
                    >
                      {t('machines:viewRepos')}
                    </GroupRowActionButton>
                  </RediaccTooltip>
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
          <RediaccTable
            columns={columns}
            dataSource={filteredMachines}
            rowKey="machineName"
            loading={isLoading}
            interactive
            selectable
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

                navigate(`/machines/${record.machineName}/repositories`, {
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
