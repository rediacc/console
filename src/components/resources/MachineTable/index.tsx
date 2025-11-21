import React, { useState, useMemo, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Table,
  Button,
  Dropdown,
  Space,
  Tooltip,
} from 'antd';
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
import { useMachines } from '@/api/queries/machines';
import type { Machine } from '@/types';
import { useSelector } from 'react-redux';
import { RootState } from '@/store/store';
import { useDynamicPageSize } from '@/hooks/useDynamicPageSize';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { usePingFunction } from '@/services/pingService';
import { LocalActionsMenu } from '../LocalActionsMenu';
import { useLocalizedFunctions } from '@/services/functionsService';
import { useRepositories } from '@/api/queries/repositories';
import { RemoteFileBrowserModal } from '../RemoteFileBrowserModal';
import { MachineVaultStatusPanel } from '../MachineVaultStatusPanel';
import { AssignToClusterModal } from '../AssignToClusterModal';
import { RemoveFromClusterModal } from '../RemoveFromClusterModal';
import { ViewAssignmentStatusModal } from '../ViewAssignmentStatusModal';
import { featureFlags } from '@/config/featureFlags';
import { buildMachineTableColumns } from './columns';
import type { MachineFunctionAction } from './columns';
import {
  MachineTableWrapper,
  TableContainer,
  BulkActionsBar,
  BulkActionsSummary,
  ViewToggleContainer,
  ViewToggleButton,
  ViewToggleDivider,
  EmptyState,
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
  onCreateRepository?: (machine: Machine, repositoryGuid?: string) => void;
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
  onCreateRepository,
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
  const [auditTraceModal, setAuditTraceModal] = useState<{
    open: boolean
    entityType: string | null
    entityIdentifier: string | null
    entityName?: string
  }>({ open: false, entityType: null, entityIdentifier: null });
  
  const [remoteFileBrowserModal, setRemoteFileBrowserModal] = useState<{
    open: boolean;
    machine: Machine | null;
  }>({ open: false, machine: null });
  
  const [assignClusterModal, setAssignClusterModal] = useState<{
    open: boolean;
    machine: Machine | null;
  }>({ open: false, machine: null });
  
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
    maxRows: 50
  });

  // Use machines directly without filtering
  const filteredMachines = machines;

  // Parse machine vault status to get repository information
  const getMachineRepositories = (machine: Machine) => {
    try {
      if (!machine.vaultStatus || machine.vaultStatus.trim().startsWith('jq:') || 
          machine.vaultStatus.trim().startsWith('error:') ||
          !machine.vaultStatus.trim().startsWith('{')) {
        return [];
      }
      
      const vaultStatusData = JSON.parse(machine.vaultStatus);
      if (vaultStatusData.status === 'completed' && vaultStatusData.result) {
        let cleanedResult = vaultStatusData.result;
        const jsonEndMatch = cleanedResult.match(/(\}[\s\n]*$)/);
        if (jsonEndMatch) {
          const lastBraceIndex = cleanedResult.lastIndexOf('}');
          if (lastBraceIndex < cleanedResult.length - 10) {
            cleanedResult = cleanedResult.substring(0, lastBraceIndex + 1);
          }
        }
        const newlineIndex = cleanedResult.indexOf('\njq:');
        if (newlineIndex > 0) {
          cleanedResult = cleanedResult.substring(0, newlineIndex);
        }
        cleanedResult = cleanedResult.trim();
        
        const result = JSON.parse(cleanedResult);
        if (result?.repositories && Array.isArray(result.repositories)) {
          return result.repositories.map((repo: any) => {
            const isGuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(repo.name);
            if (isGuid) {
              const matchingRepo = repositories.find(r => r.repositoryGuid === repo.name);
              if (matchingRepo) {
                return {
                  ...repo,
                  name: matchingRepo.repositoryName,
                  repositoryGuid: matchingRepo.repositoryGuid,
                  grandGuid: matchingRepo.grandGuid
                };
              }
            }
            return repo;
          });
        }
      }
    } catch (err) {
      // Error parsing, return empty array
    }
    return [];
  };

  const handleDelete = useCallback((machine: Machine) => {
    if (onDeleteMachine) {
      onDeleteMachine(machine);
    }
  }, [onDeleteMachine]);

  const handleRowClick = useCallback((machine: Machine) => {
    if (onRowClick) {
      onRowClick(machine);
    } else {
      setSelectedMachine(machine);
      setVaultPanelVisible(true);
    }
  }, [onRowClick]);

  const handlePanelClose = useCallback(() => {
    setVaultPanelVisible(false);
    // Clear selected machine immediately - no delays
    setSelectedMachine(null);
  }, []);






  // Get machine functions
  const { getFunctionsByCategory } = useLocalizedFunctions();
  const machineFunctions = useMemo(() =>
    getFunctionsByCategory('machine').filter(func =>
      func && func.showInMenu !== false &&
      func.name !== 'mount' &&
      func.name !== 'pull'
    ),
    [getFunctionsByCategory]
  ) as MachineFunctionAction[];

  const canAssignToCluster = isExpertMode && featureFlags.isEnabled('assignToCluster');

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
        setAssignClusterModal,
        setAuditTraceModal,
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
      setAssignClusterModal,
      setAuditTraceModal,
      machineFunctions,
    ],
  );

  // Row selection configuration - only show checkboxes if assignToCluster feature is enabled
  const rowSelection = canAssignToCluster ? {
    selectedRowKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => {
      setSelectedRowKeys(newSelectedRowKeys as string[]);
    },
    getCheckboxProps: (record: Machine) => ({
      disabled: false, // Can be customized based on machine status
      'data-testid': `machine-checkbox-${record.machineName}`,
    }),
  } : undefined;

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
            />
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
              type={groupBy === 'machine' ? 'primary' : 'default'}
              icon={<DesktopOutlined />}
              onClick={() => setGroupBy('machine')}
              data-testid="machine-view-toggle-machine"
              aria-label={t('machines:machine')}
            />
          </Tooltip>

          <ViewToggleDivider />

          <Tooltip title={t('machines:groupByBridge')}>
            <ViewToggleButton
              type={groupBy === 'bridge' ? 'primary' : 'default'}
              icon={<CloudServerOutlined />}
              onClick={() => setGroupBy('bridge')}
              data-testid="machine-view-toggle-bridge"
              aria-label={t('machines:groupByBridge')}
            />
          </Tooltip>

          <Tooltip title={t('machines:groupByTeam')}>
            <ViewToggleButton
              type={groupBy === 'team' ? 'primary' : 'default'}
              icon={<TeamOutlined />}
              onClick={() => setGroupBy('team')}
              data-testid="machine-view-toggle-team"
              aria-label={t('machines:groupByTeam')}
            />
          </Tooltip>

          {isExpertMode && (
            <Tooltip title={t('machines:groupByRegion')}>
              <ViewToggleButton
                type={groupBy === 'region' ? 'primary' : 'default'}
                icon={<GlobalOutlined />}
                onClick={() => setGroupBy('region')}
                data-testid="machine-view-toggle-region"
                aria-label={t('machines:groupByRegion')}
              />
            </Tooltip>
          )}

          <Tooltip title={t('machines:groupByRepository')}>
            <ViewToggleButton
              type={groupBy === 'repository' ? 'primary' : 'default'}
              icon={<InboxOutlined />}
              onClick={() => setGroupBy('repository')}
              data-testid="machine-view-toggle-repository"
              aria-label={t('machines:groupByRepository')}
            />
          </Tooltip>

          <Tooltip title={t('machines:groupByStatus')}>
            <ViewToggleButton
              type={groupBy === 'status' ? 'primary' : 'default'}
              icon={<DashboardOutlined />}
              onClick={() => setGroupBy('status')}
              data-testid="machine-view-toggle-status"
              aria-label={t('machines:groupByStatus')}
            />
          </Tooltip>

          <Tooltip title={t('machines:groupByGrand')}>
            <ViewToggleButton
              type={groupBy === 'grand' ? 'primary' : 'default'}
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
    
    filteredMachines.forEach(machine => {
      let key = '';
      if (groupBy === 'bridge') {
        key = machine.bridgeName;
      } else if (groupBy === 'team') {
        key = machine.teamName;
      } else if (groupBy === 'region') {
        key = machine.regionName || 'Unknown';
      } else if (groupBy === 'repository') {
        // For repository grouping, we'll handle this differently
        const machineRepos = getMachineRepositories(machine);
        if (machineRepos.length === 0) {
          // Skip machines without repositories
          return;
        }
        // Add machine to each repository it has
        machineRepos.forEach((repo: any) => {
          const repoKey = repo.name;
          if (!result[repoKey]) result[repoKey] = [];
          if (!result[repoKey].find(m => m.machineName === machine.machineName)) {
            result[repoKey].push(machine);
          }
        });
        return;
      } else if (groupBy === 'status') {
        const machineRepos = getMachineRepositories(machine);
        if (machineRepos.length === 0) {
          key = 'No Repositories';
        } else {
          // Priority-based status assignment
          const hasInaccessible = machineRepos.some((r: any) => !r.accessible);
          const hasRunning = machineRepos.some((r: any) => r.mounted && r.docker_running);
          const hasStopped = machineRepos.some((r: any) => r.mounted && !r.docker_running);
          const hasUnmounted = machineRepos.some((r: any) => !r.mounted);
          
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
        const machineRepos = getMachineRepositories(machine);
        if (machineRepos.length === 0) return;

        machineRepos.forEach((repo: any) => {
          let grandKey = 'No Grand Repository';
          if (repo.grandGuid) {
            const grandRepo = repositories.find(r => r.repositoryGuid === repo.grandGuid);
            if (grandRepo) {
              grandKey = grandRepo.repositoryName;
            }
          }
          if (!result[grandKey]) result[grandKey] = [];
          if (!result[grandKey].find(m => m.machineName === machine.machineName)) {
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
        <EmptyState description={t('resources:repositories.noRepositories')} />
      );
    }

    const variantMap: Record<GroupByMode, TagVariant> = {
      machine: 'repository',
      bridge: 'bridge',
      team: 'team',
      region: 'region',
      repository: 'repository',
      status: 'status',
      grand: 'grand',
    };

    const indicatorColors: Record<TagVariant, string> = {
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
                    navigate(`/machines/${machine.machineName}/repositories`, { state: { machine } })
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

                  <Tooltip title={t('machines:viewRepositories')}>
                    <GroupRowActionButton
                      type="primary"
                      icon={<RightOutlined />}
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/machines/${machine.machineName}/repositories`, { state: { machine } });
                      }}
                    >
                      {t('machines:viewRepositories')}
                    </GroupRowActionButton>
                  </Tooltip>
                </GroupCardRow>
              ))}
            </GroupCardContainer>
          )
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
              showTotal: (total, range) => t('common:table.showingRecords', { start: range[0], end: range[1], total }),
            }}
            onRow={(record) => ({
              'data-testid': `machine-row-${record.machineName}`,
              onClick: (e) => {
                const target = e.target as HTMLElement;
                if (target.closest('button') || target.closest('.ant-dropdown') || target.closest('.ant-dropdown-menu')) {
                  return;
                }

                navigate(`/machines/${record.machineName}/repositories`, {
                  state: { machine: record }
                })
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
        open={auditTraceModal.open}
        onCancel={() => setAuditTraceModal({ open: false, entityType: null, entityIdentifier: null })}
        entityType={auditTraceModal.entityType}
        entityIdentifier={auditTraceModal.entityIdentifier}
        entityName={auditTraceModal.entityName}
      />
      
      {remoteFileBrowserModal.machine && (
        <RemoteFileBrowserModal
          open={remoteFileBrowserModal.open}
          onCancel={() => setRemoteFileBrowserModal({ open: false, machine: null })}
          machineName={remoteFileBrowserModal.machine.machineName}
          teamName={remoteFileBrowserModal.machine.teamName}
          bridgeName={remoteFileBrowserModal.machine.bridgeName}
          onQueueItemCreated={onQueueItemCreated}
        />
      )}
      
      {/* Assign to Cluster Modal */}
      {assignClusterModal.machine && (
        <AssignToClusterModal
          open={assignClusterModal.open}
          machine={assignClusterModal.machine}
          onCancel={() => setAssignClusterModal({ open: false, machine: null })}
          onSuccess={() => {
            setAssignClusterModal({ open: false, machine: null });
            refetch();
          }}
        />
      )}
      
      {/* Bulk Assign to Cluster Modal */}
      <AssignToClusterModal
        open={bulkAssignClusterModal}
        machines={machines.filter(m => selectedRowKeys.includes(m.machineName))}
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
        machines={machines.filter(m => selectedRowKeys.includes(m.machineName))}
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
        machines={machines.filter(m => selectedRowKeys.includes(m.machineName))}
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
