import React, { useState, useMemo, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Table,
  Button,
  Dropdown,
  Card,
  Badge,
  Tag,
  Space,
  Alert,
  Modal,
  Form,
  Empty,
  Radio,
  Tooltip,
  Progress,
} from 'antd';
import type { ColumnsType } from 'antd/es/table/interface';
import {
  MoreOutlined,
  EditOutlined,
  DeleteOutlined,
  KeyOutlined,
  PlusOutlined,
  FunctionOutlined,
  HistoryOutlined,
  WifiOutlined,
  InboxOutlined,
  DatabaseOutlined,
  TeamOutlined,
  GlobalOutlined,
  CloudServerOutlined,
  BranchesOutlined,
  HddOutlined,
  DesktopOutlined,
  DashboardOutlined,
  CloudDownloadOutlined,
  RightOutlined,
  InfoCircleOutlined,
} from '@/utils/optimizedIcons';
import { useMachines } from '@/api/queries/machines';
import { useDropdownData } from '@/api/queries/useDropdownData';
import type { Machine } from '@/types';
import { useSelector } from 'react-redux';
import { RootState } from '@/store/store';
import { useDynamicPageSize } from '@/hooks/useDynamicPageSize';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { usePingFunction } from '@/services/pingService';
import { showMessage } from '@/utils/messages';
import { MachineRepositoryList } from './MachineRepositoryList';
import { useLocalizedFunctions } from '@/services/functionsService';
import { getLocalizedRelativeTime, formatTimestamp } from '@/utils/timeUtils';
import { useRepositories } from '@/api/queries/repositories';
import { useTeams } from '@/api/queries/teams';
import { useTheme } from '@/context/ThemeContext';
import { RemoteFileBrowserModal } from './RemoteFileBrowserModal';
import { MachineVaultStatusPanel } from './MachineVaultStatusPanel';
import { AssignToClusterModal } from './AssignToClusterModal';
import { RemoveFromClusterModal } from './RemoveFromClusterModal';
import { ViewAssignmentStatusModal } from './ViewAssignmentStatusModal';
import MachineAssignmentStatusBadge from './MachineAssignmentStatusBadge';
import MachineAssignmentStatusCell from './MachineAssignmentStatusCell';
import { useGetMachineAssignmentStatus } from '@/api/queries/distributedStorage';


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
  expandedRowKeys?: string[];
  onExpandedRowsChange?: (keys: string[]) => void;
  refreshKeys?: Record<string, number>;
  onRowClick?: (machine: Machine) => void;
  selectedMachine?: Machine | null;
  onMachineRepositoryClick?: (machine: Machine, repository: any) => void;
  onMachineContainerClick?: (machine: Machine, container: any) => void;
  onRefreshMachines?: () => Promise<any>;
}

export const MachineTable: React.FC<MachineTableProps> = ({
  teamFilter,
  showActions = true,
  className = '',
  onCreateMachine,
  onEditMachine,
  onVaultMachine,
  onFunctionsMachine,
  onDeleteMachine,
  onCreateRepository,
  enabled = true,
  onQueueItemCreated,
  expandedRowKeys: externalExpandedRowKeys,
  onExpandedRowsChange: externalOnExpandedRowsChange,
  refreshKeys: externalRefreshKeys,
  onRowClick,
  selectedMachine: externalSelectedMachine,
  onMachineRepositoryClick,
  onMachineContainerClick,
  onRefreshMachines,
}) => {
  const { t } = useTranslation(['machines', 'common', 'functions', 'resources']);
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const isExpertMode = uiMode === 'expert';
  const { executePingForMachineAndWait } = usePingFunction();
  const { theme } = useTheme();
  
  // Ref for table container
  const tableContainerRef = useRef<HTMLDivElement>(null);

  // State management
  const [groupBy, setGroupBy] = useState<'machine' | 'bridge' | 'team' | 'region' | 'repository' | 'status' | 'grand'>('machine');
  const [internalExpandedRowKeys, setInternalExpandedRowKeys] = useState<string[]>([]);
  const [expansionTimestamps, setExpansionTimestamps] = useState<Record<string, number>>({});
  const [internalRefreshKeys, setInternalRefreshKeys] = useState<Record<string, number>>({});
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [showLoadingIndicator, setShowLoadingIndicator] = useState(false);
  const [loadingTimer, setLoadingTimer] = useState<NodeJS.Timeout | null>(null);
  const [expandingRowKey, setExpandingRowKey] = useState<string | null>(null);
  
  // Bulk selection state
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  
  // Use external or internal state
  const expandedRowKeys = externalExpandedRowKeys !== undefined ? externalExpandedRowKeys : internalExpandedRowKeys;
  const setExpandedRowKeys = externalOnExpandedRowsChange || setInternalExpandedRowKeys;
  const refreshKeys = externalRefreshKeys !== undefined ? externalRefreshKeys : internalRefreshKeys;
  const setRefreshKeys = externalRefreshKeys !== undefined 
    ? () => {} // If external, parent manages refresh keys
    : setInternalRefreshKeys;
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

  // Clean up timer on unmount
  React.useEffect(() => {
    return () => {
      if (loadingTimer) {
        clearTimeout(loadingTimer);
      }
    };
  }, [loadingTimer]);

  // Queries only - mutations are handled by parent
  const { data: machines = [], isLoading, refetch } = useMachines(teamFilter, enabled);
  const { data: dropdownData } = useDropdownData();
  const { data: teams } = useTeams();
  const { data: repositories = [] } = useRepositories(teamFilter);
  
  // Dynamic page size
  const dynamicPageSize = useDynamicPageSize(tableContainerRef, {
    containerOffset: 170, // Account for filters, tabs, and other UI elements
    minRows: 5,
    maxRows: 50
  });



  // Get unique values for filters
  const teamsData = dropdownData?.teams || [];

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
    // Keep selectedMachine for a bit to avoid UI flicker during close animation
    setTimeout(() => {
      setSelectedMachine(null);
    }, 300);
  }, []);






  // Get machine functions
  const { getFunctionsByCategory } = useLocalizedFunctions();
  const machineFunctions = useMemo(() => 
    getFunctionsByCategory('machine').filter(func => 
      func.showInMenu !== false && 
      func.name !== 'mount' && 
      func.name !== 'pull'
    ), 
    [getFunctionsByCategory]
  );

  // Machine columns
  const columns: ColumnsType<Machine> = React.useMemo(() => {
    const baseColumns: ColumnsType<Machine> = [];

    // Add the other columns first
    baseColumns.push(
      {
        title: t('machines:machineName'),
        dataIndex: 'machineName',
        key: 'machineName',
        ellipsis: true,
        sorter: (a: Machine, b: Machine) => a.machineName.localeCompare(b.machineName),
        render: (name: string, record: Machine) => {
          const isExpanded = expandedRowKeys.includes(record.machineName);
          return (
            <Space>
              <span style={{ 
                display: 'inline-block',
                width: 12,
                transition: 'transform 0.3s ease',
                transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)'
              }}>
                <RightOutlined style={{ fontSize: 12, color: '#999' }} />
              </span>
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
        sorter: (a: Machine, b: Machine) => a.teamName.localeCompare(b.teamName),
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
            sorter: (a: Machine, b: Machine) => (a.regionName || '').localeCompare(b.regionName || ''),
          },
          {
            title: t('machines:bridge'),
            dataIndex: 'bridgeName',
            key: 'bridgeName',
            width: 150,
            ellipsis: true,
            render: (bridgeName: string) => <Tag color="green">{bridgeName}</Tag>,
            sorter: (a: Machine, b: Machine) => a.bridgeName.localeCompare(b.bridgeName),
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

    // Distributed Storage Assignment Status column - show in expert mode
    if (!onRowClick && isExpertMode) {
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
        sorter: (a: Machine, b: Machine) => a.queueCount - b.queueCount,
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
        width: 320,
        render: (_: unknown, record: Machine) => (
          <Space>
            <Button
              type="primary"
              size="small"
              icon={<EditOutlined />}
              onClick={() => onEditMachine && onEditMachine(record)}
            >
              {t('common:actions.edit')}
            </Button>
            <Dropdown
              menu={{
                items: [
                  {
                    key: 'createRepo',
                    label: t('machines:createRepo'),
                    icon: <InboxOutlined />,
                    onClick: () => onCreateRepository && onCreateRepository(record)
                  },
                  {
                    key: 'pull',
                    label: t('functions:functions.pull.name'),
                    icon: <CloudDownloadOutlined />,
                    onClick: () => {
                      setRemoteFileBrowserModal({
                        open: true,
                        machine: record
                      });
                    }
                  },
                  {
                    key: 'functions',
                    label: t('machines:runAction'),
                    icon: <FunctionOutlined />,
                    children: [
                      ...machineFunctions.map((func) => ({
                        key: `function-${func.name}`,
                        label: (
                          <span title={func.description}>
                            {func.name}
                          </span>
                        ),
                        onClick: () => {
                          if (onFunctionsMachine) {
                            onFunctionsMachine(record, func.name);
                            // Mark this machine for refresh when action completes
                            if (externalRefreshKeys === undefined) {
                              setInternalRefreshKeys(prev => ({
                                ...prev,
                                [record.machineName]: Date.now()
                              }))
                            }
                          }
                        }
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
                            // Mark this machine for refresh when action completes
                            if (externalRefreshKeys === undefined) {
                              setInternalRefreshKeys(prev => ({
                                ...prev,
                                [record.machineName]: Date.now()
                              }))
                            }
                          }
                        }
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
                    }
                  },
                  ...(isExpertMode ? [{
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
                    }
                  }] : [])
                ]
              }}
              trigger={['click']}
            >
              <Button
                type="primary"
                size="small"
                icon={<FunctionOutlined />}
              >
                {t('machines:remote')}
              </Button>
            </Dropdown>
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
            >
              {t('machines:trace')}
            </Button>
            <Button
              type="primary"
              danger
              size="small"
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(record)}
            >
              {t('common:actions.delete')}
            </Button>
          </Space>
        ),
      });
    }

    return baseColumns;
  }, [isExpertMode, uiMode, showActions, t, handleDelete, dropdownData, onEditMachine, onVaultMachine, onFunctionsMachine, onCreateRepository, executePingForMachineAndWait, machineFunctions]);

  // Row selection configuration
  const rowSelection = isExpertMode ? {
    selectedRowKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => {
      setSelectedRowKeys(newSelectedRowKeys as string[]);
    },
    getCheckboxProps: (record: Machine) => ({
      disabled: false, // Can be customized based on machine status
    }),
  } : undefined;

  // Render bulk actions toolbar
  const renderBulkActionsToolbar = () => {
    if (!isExpertMode || selectedRowKeys.length === 0) return null;

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
          <Button
            size="small"
            onClick={() => setSelectedRowKeys([])}
          >
            {t('common:actions.clearSelection')}
          </Button>
        </Space>
        <Space>
          <Button
            type="primary"
            icon={<CloudServerOutlined />}
            onClick={() => setBulkAssignClusterModal(true)}
          >
            {t('machines:bulkActions.assignToCluster')}
          </Button>
          <Button
            icon={<CloudServerOutlined />}
            onClick={() => setRemoveFromClusterModal(true)}
          >
            {t('machines:bulkActions.removeFromCluster')}
          </Button>
          <Button
            icon={<InfoCircleOutlined />}
            onClick={() => setViewAssignmentStatusModal(true)}
          >
            {t('machines:bulkActions.viewAssignmentStatus')}
          </Button>
        </Space>
      </div>
    );
  };

  // Render view mode toggle
  const renderViewToggle = () => {
    return (
      <div style={{ marginBottom: 16 }}>
        <Space wrap size="small">
          <span style={{ marginRight: 8, fontWeight: 500 }}>{t('machines:groupBy')}:</span>
          <Radio.Group 
            value={groupBy} 
            onChange={(e) => setGroupBy(e.target.value)}
            buttonStyle="solid"
            style={{
              backgroundColor: theme === 'light' ? '#f5f5f5' : undefined,
              borderRadius: '6px',
              padding: '2px'
            }}
            className={theme === 'light' ? 'light-mode-radio-group' : ''}
          >
            <Radio.Button value="machine">
              <Space>
                <DesktopOutlined />
                {t('machines:machine')}
              </Space>
            </Radio.Button>
            <span style={{ marginLeft: 16 }} />
            <Radio.Button value="bridge">
              <Space>
                <CloudServerOutlined />
                {t('machines:groupByBridge')}
              </Space>
            </Radio.Button>
            <Radio.Button value="team">
              <Space>
                <TeamOutlined />
                {t('machines:groupByTeam')}
              </Space>
            </Radio.Button>
            {isExpertMode && (
              <Radio.Button value="region">
                <Space>
                  <GlobalOutlined />
                  {t('machines:groupByRegion')}
                </Space>
              </Radio.Button>
            )}
            <Radio.Button value="repository">
              <Space>
                <InboxOutlined />
                {t('machines:groupByRepository')}
              </Space>
            </Radio.Button>
            <Radio.Button value="status">
              <Space>
                <DashboardOutlined />
                {t('machines:groupByStatus')}
              </Space>
            </Radio.Button>
            <Radio.Button value="grand">
              <Space>
                <BranchesOutlined />
                {t('machines:groupByGrand')}
              </Space>
            </Radio.Button>
          </Radio.Group>
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
        machineRepos.forEach(repo => {
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
          const hasInaccessible = machineRepos.some(r => !r.accessible);
          const hasRunning = machineRepos.some(r => r.mounted && r.docker_running);
          const hasStopped = machineRepos.some(r => r.mounted && !r.docker_running);
          const hasUnmounted = machineRepos.some(r => !r.mounted);
          
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
        
        machineRepos.forEach(repo => {
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
      
      if (key && groupBy !== 'repository') {
        if (!result[key]) result[key] = [];
        result[key].push(machine);
      }
    });
    
    return result;
  }, [filteredMachines, groupBy, repositories]);

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
                    height: 32,
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
            bodyStyle={{ 
              padding: 0,
              backgroundColor: getGroupBackgroundColor(groupIndex)
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
                  backgroundColor: index % 2 === 0 ? 'transparent' : 'rgba(0, 0, 0, 0.01)'
                }}
              >
                <MachineRepositoryList 
                  machine={machine}
                  key={`${machine.machineName}-${expansionTimestamps[machine.machineName] || 0}-${refreshKeys[machine.machineName] || 0}`}
                  onActionComplete={() => {
                    // Refresh this specific machine's repository list
                    if (externalRefreshKeys === undefined) {
                      setInternalRefreshKeys(prev => ({
                        ...prev,
                        [machine.machineName]: Date.now()
                      }))
                    }
                  }}
                  onRepositoryClick={(repository) => onMachineRepositoryClick?.(machine, repository)}
                  onContainerClick={(container) => onMachineContainerClick?.(machine, container)}
                  onCreateRepository={onCreateRepository}
                  hideSystemInfo={true}
                  isLoading={showLoadingIndicator && expandingRowKey === machine.machineName}
                  onRefreshMachines={onRefreshMachines}
                />
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
            scroll={{ x: true, y: 'calc(100vh - 400px)' }}
            rowSelection={rowSelection}
            rowClassName={(record) => {
              const isSelected = externalSelectedMachine?.machineName === record.machineName;
              return isSelected ? 'ant-table-row-selected' : '';
            }}
            pagination={{
              pageSize: dynamicPageSize,
              showSizeChanger: false,
              showTotal: (total, range) => t('common:table.showingRecords', { start: range[0], end: range[1], total }),
            }}
            onRow={(record) => ({
              onClick: (e) => {
                const target = e.target as HTMLElement;
                // Don't expand if clicking on buttons or dropdowns
                if (target.closest('button') || target.closest('.ant-dropdown-trigger')) {
                  return;
                }
                
                // Toggle expansion
                const isExpanded = expandedRowKeys.includes(record.machineName);
                if (isExpanded) {
                  setExpandedRowKeys(expandedRowKeys.filter(key => key !== record.machineName));
                } else {
                  setExpandedRowKeys([...expandedRowKeys, record.machineName]);
                  // Track expansion timestamp
                  setExpansionTimestamps(prev => ({
                    ...prev,
                    [record.machineName]: Date.now()
                  }));
                  
                  // Trigger refresh when expanding
                  if (onRefreshMachines) {
                    setExpandingRowKey(record.machineName);
                    setIsRefreshing(true);
                    
                    // Start 1-second timer for loading indicator
                    const timer = setTimeout(() => {
                      setShowLoadingIndicator(true);
                    }, 1000);
                    setLoadingTimer(timer);
                    
                    // Trigger refresh
                    onRefreshMachines().finally(() => {
                      if (loadingTimer) {
                        clearTimeout(loadingTimer);
                      }
                      setIsRefreshing(false);
                      setShowLoadingIndicator(false);
                      setExpandingRowKey(null);
                      setLoadingTimer(null);
                    });
                  }
                }
                
                // Also call the row click handler if provided
                if (onRowClick) {
                  handleRowClick(record);
                }
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
            expandable={{
              expandedRowRender: (record) => (
                <MachineRepositoryList 
                  machine={record} 
                  key={`${record.machineName}-${expansionTimestamps[record.machineName] || 0}-${refreshKeys[record.machineName] || 0}`}
                  onActionComplete={() => {
                    // Refresh this specific machine's repository list
                    if (externalRefreshKeys === undefined) {
                      setInternalRefreshKeys(prev => ({
                        ...prev,
                        [record.machineName]: Date.now()
                      }))
                    }
                  }}
                  onRepositoryClick={(repository) => onMachineRepositoryClick?.(record, repository)}
                  onContainerClick={(container) => onMachineContainerClick?.(record, container)}
                  onCreateRepository={onCreateRepository}
                  isLoading={showLoadingIndicator && expandingRowKey === record.machineName}
                  onRefreshMachines={onRefreshMachines}
                />
              ),
              rowExpandable: () => true,
              expandedRowKeys,
              onExpandedRowsChange: (keys) => {
                const newKeys = keys as string[];
                setExpandedRowKeys(newKeys);
                
                // Track expansion timestamp for newly expanded rows
                const newTimestamps = { ...expansionTimestamps };
                newKeys.forEach(key => {
                  if (!expandedRowKeys.includes(key)) {
                    // This is a newly expanded row
                    newTimestamps[key] = Date.now();
                  }
                });
                setExpansionTimestamps(newTimestamps);
              },
              expandIcon: () => null, // Hide default expand icon
              expandRowByClick: false // We handle this manually
            }}
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