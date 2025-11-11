import React, { useState, useMemo, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Table,
  Button,
  Dropdown,
  Card,
  Badge,
  Tag,
  Space,
  Empty,
  Tooltip,
} from 'antd';
import type { ColumnsType } from 'antd/es/table/interface';
import {
  EditOutlined,
  DeleteOutlined,
  FunctionOutlined,
  HistoryOutlined,
  WifiOutlined,
  InboxOutlined,
  TeamOutlined,
  GlobalOutlined,
  CloudServerOutlined,
  BranchesOutlined,
  DesktopOutlined,
  DashboardOutlined,
  RightOutlined,
  InfoCircleOutlined,
  CheckCircleOutlined,
  DisconnectOutlined,
  EyeOutlined,
} from '@/utils/optimizedIcons';
import { useMachines } from '@/api/queries/machines';
import type { Machine } from '@/types';
import { useSelector } from 'react-redux';
import { RootState } from '@/store/store';
import { useDynamicPageSize } from '@/hooks/useDynamicPageSize';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { usePingFunction } from '@/services/pingService';
import { showMessage } from '@/utils/messages';
import { LocalActionsMenu } from './LocalActionsMenu';
import { useLocalizedFunctions } from '@/services/functionsService';
import { useRepositories } from '@/api/queries/repositories';
import { RemoteFileBrowserModal } from './RemoteFileBrowserModal';
import { MachineVaultStatusPanel } from './MachineVaultStatusPanel';
import { AssignToClusterModal } from './AssignToClusterModal';
import { RemoveFromClusterModal } from './RemoveFromClusterModal';
import { ViewAssignmentStatusModal } from './ViewAssignmentStatusModal';
import MachineAssignmentStatusCell from './MachineAssignmentStatusCell';
import { useComponentStyles } from '@/hooks/useComponentStyles';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import { featureFlags } from '@/config/featureFlags';


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
  const styles = useComponentStyles();
  
  // Ref for table container
  const tableContainerRef = useRef<HTMLDivElement>(null);

  // State management
  const [groupBy, setGroupBy] = useState<'machine' | 'bridge' | 'team' | 'region' | 'repository' | 'status' | 'grand'>('machine');

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
  );

  // Machine columns
  // eslint-disable-next-line react-hooks/preserve-manual-memoization -- React compiler cannot preserve memoization with dynamic dependencies
  const columns: ColumnsType<Machine> = React.useMemo(() => {
    const baseColumns: ColumnsType<Machine> = [];

    // Add Status column first
    baseColumns.push(
      {
        title: t('machines:status'),
        dataIndex: 'vaultStatusTime',
        key: 'status',
        width: 100,
        align: 'center',
        render: (_: any, record: Machine) => {
          if (!record.vaultStatusTime) {
            return (
              <Tooltip title={t('machines:statusUnknown')}>
                <span style={{ fontSize: 18, color: '#d9d9d9' }}>
                  <DisconnectOutlined />
                </span>
              </Tooltip>
            )
          }

          // Parse vaultStatusTime (UTC) - add 'Z' to ensure UTC parsing
          const statusTime = new Date(record.vaultStatusTime + 'Z')
          const now = new Date()
          const diffSeconds = (now.getTime() - statusTime.getTime()) / 1000
          const diffMinutes = diffSeconds / 60

          const isOnline = diffMinutes <= 3

          return (
            <Tooltip title={isOnline ? t('machines:connected') : t('machines:connectionFailed')}>
              <span style={{ fontSize: 18, color: isOnline ? '#52c41a' : '#d9d9d9' }}>
                {isOnline ? <CheckCircleOutlined /> : <DisconnectOutlined />}
              </span>
            </Tooltip>
          )
        },
      },
      {
        title: t('machines:machineName'),
        dataIndex: 'machineName',
        key: 'machineName',
        ellipsis: true,
        render: (name: string) => {
          return (
            <Space>
              <DesktopOutlined style={{ color: '#556b2f' }} />
              <strong>{name}</strong>
            </Space>
          );
        },
      },
    );

    // Only show team column if not in split view mode
    if (!onRowClick) {
      baseColumns.push({
        title: t('machines:team'),
        dataIndex: 'teamName',
        key: 'teamName',
        width: 150,
        ellipsis: true,
        render: (teamName: string) => <Tag color="#8FBC8F">{teamName}</Tag>,
      });
    }

    // Add team/bridge/region columns in expert mode - but not in split view
    if (!onRowClick) {
      if (isExpertMode) {
        // Show region and bridge columns (team is already filtered in embedded mode)
        baseColumns.push(
          {
            title: t('machines:region'),
            dataIndex: 'regionName',
            key: 'regionName',
            width: 150,
            ellipsis: true,
            render: (regionName: string) => regionName ? <Tag color="purple">{regionName}</Tag> : '-',
          },
          {
            title: t('machines:bridge'),
            dataIndex: 'bridgeName',
            key: 'bridgeName',
            width: 150,
            ellipsis: true,
            render: (bridgeName: string) => <Tag color="green">{bridgeName}</Tag>,
          }
        );
      } else if (uiMode !== 'simple') {
        // Show only bridge in non-expert UI
        baseColumns.push({
          title: t('bridges.bridge'),
          dataIndex: 'bridgeName',
          key: 'bridgeName',
          width: 150,
          ellipsis: true,
          render: (bridge: string) => <Tag color="#8FBC8F">{bridge}</Tag>,
        });
      }
    }

    // Distributed Storage Assignment Status column - show in expert mode with feature flag
    if (!onRowClick && isExpertMode && featureFlags.isEnabled('assignToCluster')) {
      baseColumns.push({
        title: t('machines:assignmentStatus.title'),
        key: 'assignmentStatus',
        width: 180,
        ellipsis: true,
        render: (_: unknown, record: Machine) => <MachineAssignmentStatusCell machine={record} />,
      });
    }

    // Queue items column - not in split view
    if (!onRowClick) {
      baseColumns.push({
        title: t('machines:queueItems'),
        dataIndex: 'queueCount',
        key: 'queueCount',
        width: 100,
        align: 'center' as const,
        render: (count: number) => (
          <Badge count={count} showZero style={{ backgroundColor: count > 0 ? '#52c41a' : '#d9d9d9' }} />
        ),
      });
    }


    // Actions column last if showActions is true
    if (showActions) {
      baseColumns.push({
        title: t('common:table.actions'),
        key: 'actions',
        width: DESIGN_TOKENS.DIMENSIONS.CARD_WIDTH,
        render: (_: unknown, record: Machine) => (
          <Space>
            {/* Eye button - opens detail panel */}
            <Tooltip title={t('common:viewDetails')}>
              <Button
                type="default"
                size="small"
                icon={<EyeOutlined />}
                onClick={(e) => {
                  e.stopPropagation()
                  handleRowClick(record)
                }}
                data-testid={`machine-view-details-${record.machineName}`}
                aria-label={t('common:viewDetails')}
              />
            </Tooltip>

            <Tooltip title={t('common:actions.edit')}>
              <Button
                type="primary"
                size="small"
                icon={<EditOutlined />}
                onClick={() => onEditMachine && onEditMachine(record)}
                data-testid={`machine-edit-${record.machineName}`}
                aria-label={t('common:actions.edit')}
              />
            </Tooltip>
            <Dropdown
              data-testid={`machine-dropdown-${record.machineName}`}
              menu={{
                items: [
                  {
                    key: 'functions',
                    label: t('machines:runAction'),
                    icon: <FunctionOutlined />,
                    'data-testid': `machine-functions-${record.machineName}`,
                    children: [
                      ...machineFunctions.map((func) => ({
                        key: `function-${func?.name || 'unknown'}`,
                        label: (
                          <span title={func?.description || ''}>
                            {func?.name || 'Unknown'}
                          </span>
                        ),
                        onClick: () => {
                          if (onFunctionsMachine && func?.name) {
                            onFunctionsMachine(record, func.name);
                          }
                        },
                        'data-testid': `machine-function-${func?.name || 'unknown'}-${record.machineName}`
                      })),
                      {
                        type: 'divider'
                      },
                      {
                        key: 'advanced',
                        label: t('machines:advanced'),
                        icon: <FunctionOutlined />,
                        onClick: () => {
                          if (onFunctionsMachine) {
                            onFunctionsMachine(record);
                          }
                        },
                        'data-testid': `machine-advanced-${record.machineName}`
                      }
                    ]
                  },
                  {
                    key: 'test',
                    label: t('machines:connectivityTest'),
                    icon: <WifiOutlined />,
                    onClick: async () => {
                      showMessage('info', t('machines:testingConnection'));
                      const result = await executePingForMachineAndWait(record, {
                        priority: 4,
                        description: 'Connectivity test',
                        addedVia: 'machine-table',
                        timeout: 15000 // 15 seconds timeout for quick test
                      });
                      if (result.success) {
                        showMessage('success', t('machines:connectionSuccessful'));
                      } else {
                        showMessage('error', result.error || t('machines:connectionFailed'));
                      }
                    },
                    'data-testid': `machine-test-${record.machineName}`
                  },
                  ...(isExpertMode && featureFlags.isEnabled('assignToCluster') ? [{
                    key: 'assignCluster',
                    label: record.distributedStorageClusterName
                      ? t('machines:changeClusterAssignment')
                      : t('machines:assignToCluster'),
                    icon: <CloudServerOutlined />,
                    onClick: () => {
                      setAssignClusterModal({
                        open: true,
                        machine: record
                      });
                    },
                    'data-testid': `machine-assign-cluster-${record.machineName}`
                  }] : [])
                ]
              }}
              trigger={['click']}
            >
              <Tooltip title={t('machines:remote')}>
                <Button
                  type="primary"
                  size="small"
                  icon={<FunctionOutlined />}
                  data-testid={`machine-remote-${record.machineName}`}
                  aria-label={t('machines:remote')}
                />
              </Tooltip>
            </Dropdown>
            <Tooltip title={t('machines:trace')}>
              <Button
                type="primary"
                size="small"
                icon={<HistoryOutlined />}
                onClick={() => {
                  setAuditTraceModal({
                    open: true,
                    entityType: 'Machine',
                    entityIdentifier: record.machineName,
                    entityName: record.machineName
                  });
                }}
                data-testid={`machine-trace-${record.machineName}`}
                aria-label={t('machines:trace')}
              />
            </Tooltip>
            <Tooltip title={t('common:actions.delete')}>
              <Button
                type="primary"
                danger
                size="small"
                icon={<DeleteOutlined />}
                onClick={() => handleDelete(record)}
                data-testid={`machine-delete-${record.machineName}`}
                aria-label={t('common:actions.delete')}
              />
            </Tooltip>
            <LocalActionsMenu
              machine={record.machineName}
              teamName={record.teamName}
            />
          </Space>
        ),
      });
    }

    return baseColumns;
  }, [isExpertMode, uiMode, showActions, t, handleDelete, onEditMachine, onFunctionsMachine, onCreateRepository, executePingForMachineAndWait, machineFunctions, setAssignClusterModal, setAuditTraceModal, setRemoteFileBrowserModal, handleRowClick]);

  // Row selection configuration - only show checkboxes if assignToCluster feature is enabled
  const rowSelection = (isExpertMode && featureFlags.isEnabled('assignToCluster')) ? {
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
    if (!isExpertMode || !featureFlags.isEnabled('assignToCluster') || selectedRowKeys.length === 0) return null;

    return (
      <div style={{ 
        marginBottom: 16, 
        padding: '12px 16px', 
        backgroundColor: '#f0f2f5',
        borderRadius: 8,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <Space>
          <span style={{ fontWeight: 500 }}>
            {t('machines:bulkActions.selected', { count: selectedRowKeys.length })}
          </span>
          <Tooltip title={t('common:actions.clearSelection')}>
            <Button
              size="small"
              onClick={() => setSelectedRowKeys([])}
              data-testid="machine-bulk-clear-selection"
              aria-label={t('common:actions.clearSelection')}
            />
          </Tooltip>
        </Space>
        <Space>
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
      </div>
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
      <div style={{ marginBottom: 16 }}>
        <Space wrap size="small">
          <Tooltip title={t('machines:machine')}>
            <Button
              type={groupBy === 'machine' ? 'primary' : 'default'}
              icon={<DesktopOutlined />}
              onClick={() => setGroupBy('machine')}
              style={styles.controlSurfaceSmall}
              data-testid="machine-view-toggle-machine"
              aria-label={t('machines:machine')}
            />
          </Tooltip>

          <div style={{ width: 1, height: 24, backgroundColor: 'var(--color-border)', margin: '0 8px' }} />

          <Tooltip title={t('machines:groupByBridge')}>
            <Button
              type={groupBy === 'bridge' ? 'primary' : 'default'}
              icon={<CloudServerOutlined />}
              onClick={() => setGroupBy('bridge')}
              style={styles.controlSurfaceSmall}
              data-testid="machine-view-toggle-bridge"
              aria-label={t('machines:groupByBridge')}
            />
          </Tooltip>

          <Tooltip title={t('machines:groupByTeam')}>
            <Button
              type={groupBy === 'team' ? 'primary' : 'default'}
              icon={<TeamOutlined />}
              onClick={() => setGroupBy('team')}
              style={styles.controlSurfaceSmall}
              data-testid="machine-view-toggle-team"
              aria-label={t('machines:groupByTeam')}
            />
          </Tooltip>

          {isExpertMode && (
            <Tooltip title={t('machines:groupByRegion')}>
              <Button
                type={groupBy === 'region' ? 'primary' : 'default'}
                icon={<GlobalOutlined />}
                onClick={() => setGroupBy('region')}
                style={styles.controlSurfaceSmall}
                data-testid="machine-view-toggle-region"
                aria-label={t('machines:groupByRegion')}
              />
            </Tooltip>
          )}

          <Tooltip title={t('machines:groupByRepository')}>
            <Button
              type={groupBy === 'repository' ? 'primary' : 'default'}
              icon={<InboxOutlined />}
              onClick={() => setGroupBy('repository')}
              style={styles.controlSurfaceSmall}
              data-testid="machine-view-toggle-repository"
              aria-label={t('machines:groupByRepository')}
            />
          </Tooltip>

          <Tooltip title={t('machines:groupByStatus')}>
            <Button
              type={groupBy === 'status' ? 'primary' : 'default'}
              icon={<DashboardOutlined />}
              onClick={() => setGroupBy('status')}
              style={styles.controlSurfaceSmall}
              data-testid="machine-view-toggle-status"
              aria-label={t('machines:groupByStatus')}
            />
          </Tooltip>

          <Tooltip title={t('machines:groupByGrand')}>
            <Button
              type={groupBy === 'grand' ? 'primary' : 'default'}
              icon={<BranchesOutlined />}
              onClick={() => setGroupBy('grand')}
              style={styles.controlSurfaceSmall}
              data-testid="machine-view-toggle-grand"
              aria-label={t('machines:groupByGrand')}
            />
          </Tooltip>
        </Space>
      </div>
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
    const getGroupColor = () => {
      switch (groupBy) {
        case 'machine': return '#556b2f';
        case 'bridge': return 'green';
        case 'team': return '#8FBC8F';
        case 'region': return 'purple';
        case 'repository': return '#556b2f';
        case 'status': return 'geekblue';
        case 'grand': return 'blue';
        default: return 'default';
      }
    };

    if (Object.keys(groupedMachinesForTable).length === 0) {
      return (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t('resources:repositories.noRepositories')}
          style={{ marginTop: 48 }}
        />
      );
    }

    const getGroupBackgroundColor = (groupIndex: number) => {
      // Only apply background to even groups (0, 2, 4, etc.)
      return groupIndex % 2 === 0 ? 'rgba(0, 0, 0, 0.02)' : 'transparent';
    };

    const getGroupBorderColor = (groupIndex: number) => {
      // Only apply special border to even groups
      return groupIndex % 2 === 0 ? 'rgba(0, 0, 0, 0.08)' : '#f0f0f0';
    };

    const getGroupHeaderColor = (groupIndex: number) => {
      // Only apply header color to even groups
      return groupIndex % 2 === 0 ? '#595959' : 'transparent';
    };

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
        {Object.entries(groupedMachinesForTable).map(([groupKey, machines], groupIndex) => (
          <Card
            key={groupKey}
            title={
              <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: 12,
                padding: '8px 0'
              }}>
                {groupIndex % 2 === 0 && (
                  <div style={{
                    width: 4,
                    height: DESIGN_TOKENS.DIMENSIONS.ICON_XL,
                    backgroundColor: getGroupHeaderColor(groupIndex),
                    borderRadius: 2
                  }} />
                )}
                <Space>
                  <span style={{ 
                    fontSize: '18px', 
                    fontWeight: 'bold',
                    color: '#333',
                    marginRight: 8
                  }}>
                    #{groupIndex + 1}
                  </span>
                  <Tag 
                    color={getGroupColor()} 
                    style={{ 
                      fontSize: '16px',
                      padding: '4px 16px',
                      fontWeight: 500
                    }}
                    icon={
                      groupBy === 'bridge' ? <CloudServerOutlined /> :
                      groupBy === 'team' ? <TeamOutlined /> :
                      groupBy === 'region' ? <GlobalOutlined /> :
                      groupBy === 'repository' ? <InboxOutlined /> :
                      groupBy === 'status' ? <DashboardOutlined /> :
                      groupBy === 'grand' ? <BranchesOutlined /> :
                      null
                    }
                  >
                    {groupKey}
                  </Tag>
                  <span style={{ fontSize: '14px', color: '#666' }}>
                    {machines.length} {machines.length === 1 ? t('machines:machine') : t('machines:machines')}
                  </span>
                </Space>
              </div>
            }
            styles={{
              body: {
                padding: 0,
                backgroundColor: getGroupBackgroundColor(groupIndex)
              }
            }}
            style={{
              borderColor: getGroupBorderColor(groupIndex),
              borderWidth: 2,
              boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06)'
            }}
            headStyle={{
              backgroundColor: getGroupBackgroundColor(groupIndex),
              borderBottom: `2px solid ${getGroupBorderColor(groupIndex)}`
            }}
          >
            {machines.map((machine, index) => (
              <div
                key={machine.machineName}
                style={{
                  borderBottom: index < machines.length - 1 ? `1px solid ${getGroupBorderColor(groupIndex)}` : 'none',
                  backgroundColor: index % 2 === 0 ? 'transparent' : 'rgba(0, 0, 0, 0.01)',
                  padding: '16px 24px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  transition: 'background-color 0.2s',
                  cursor: 'pointer'
                }}
                onClick={() => navigate(`/machines/${machine.machineName}/repositories`, { state: { machine } })}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'rgba(85, 107, 47, 0.05)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = index % 2 === 0 ? 'transparent' : 'rgba(0, 0, 0, 0.01)';
                }}
              >
                <Space size="large">
                  <DesktopOutlined style={{ fontSize: 20, color: '#556b2f' }} />
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>
                      {machine.machineName}
                    </div>
                    <Space size="small">
                      <Tag color="#8FBC8F">{machine.teamName}</Tag>
                      <Tag color="green">{machine.bridgeName}</Tag>
                      {machine.regionName && <Tag color="purple">{machine.regionName}</Tag>}
                    </Space>
                  </div>
                </Space>
                <Tooltip title={t('machines:viewRepositories')}>
                  <Button
                    type="primary"
                    icon={<RightOutlined />}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/machines/${machine.machineName}/repositories`, { state: { machine } });
                    }}
                    style={{ ...styles.controlSurfaceSmall }}
                  >
                    {t('machines:viewRepositories')}
                  </Button>
                </Tooltip>
              </div>
            ))}
          </Card>
        ))}
      </div>
    );
  };



  return (
    <div className={className}>
      {renderViewToggle()}
      {renderBulkActionsToolbar()}
      
      {groupBy === 'machine' ? (
        <div ref={tableContainerRef} style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <Table
            columns={columns}
            dataSource={filteredMachines}
            rowKey="machineName"
            loading={isLoading}
            scroll={{ x: 'max-content' }}
            rowSelection={rowSelection}
            rowClassName={(record) => {
              const isSelected = externalSelectedMachine?.machineName === record.machineName;
              return isSelected ? 'ant-table-row-selected' : '';
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
                // Don't trigger row click if clicking on buttons or dropdowns
                if (target.closest('button') || target.closest('.ant-dropdown')) {
                  return;
                }

                // Row clicks always navigate to repositories page
                // Only the eye button should trigger detail panel (via handleRowClick)
                navigate(`/machines/${record.machineName}/repositories`, {
                  state: { machine: record }
                })
              },
              style: {
                cursor: 'pointer',
                transition: 'background-color 0.3s ease'
              },
              onMouseEnter: (e) => {
                e.currentTarget.style.backgroundColor = 'rgba(0, 0, 0, 0.02)';
              },
              onMouseLeave: (e) => {
                e.currentTarget.style.backgroundColor = '';
              }
            })}
            sticky
          />
        </div>
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
    </div>
  );
};
