import React, { useState, useMemo, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Table,
  Input,
  Button,
  Select,
  Dropdown,
  Card,
  Badge,
  Tag,
  Space,
  Alert,
  Modal,
  Row,
  Col,
  Segmented,
  Form,
  Empty,
  Radio,
  Tooltip,
  Progress,
} from 'antd';
import type { ColumnsType } from 'antd/es/table/interface';
import {
  SearchOutlined,
  MoreOutlined,
  EditOutlined,
  DeleteOutlined,
  KeyOutlined,
  PlusOutlined,
  AppstoreOutlined,
  TableOutlined,
  FilterOutlined,
  FunctionOutlined,
  HistoryOutlined,
  WifiOutlined,
  InboxOutlined,
  DatabaseOutlined,
  TeamOutlined,
  GlobalOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CloudServerOutlined,
  BranchesOutlined,
  HddOutlined,
  DesktopOutlined,
} from '@ant-design/icons';
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

const { Option } = Select;
const { Search } = Input;

interface MachineTableProps {
  teamFilter?: string | string[];
  showFilters?: boolean;
  showActions?: boolean;
  className?: string;
  onCreateMachine?: () => void;
  onEditMachine?: (machine: Machine) => void;
  onVaultMachine?: (machine: Machine) => void;
  onFunctionsMachine?: (machine: Machine) => void;
  onDeleteMachine?: (machine: Machine) => void;
  onCreateRepository?: (machine: Machine) => void;
  enabled?: boolean;
  expandedRowKeys?: string[];
  onExpandedRowsChange?: (keys: string[]) => void;
  refreshKeys?: Record<string, number>;
}

export const MachineTable: React.FC<MachineTableProps> = ({
  teamFilter,
  showFilters = true,
  showActions = true,
  className = '',
  onCreateMachine,
  onEditMachine,
  onVaultMachine,
  onFunctionsMachine,
  onDeleteMachine,
  onCreateRepository,
  enabled = true,
  expandedRowKeys: externalExpandedRowKeys,
  onExpandedRowsChange: externalOnExpandedRowsChange,
  refreshKeys: externalRefreshKeys,
}) => {
  const { t } = useTranslation(['machines', 'common', 'functions', 'resources']);
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const isExpertMode = uiMode === 'expert';
  const { executePingForMachineAndWait } = usePingFunction();
  const { theme } = useTheme();
  
  // Ref for table container
  const tableContainerRef = useRef<HTMLDivElement>(null);

  // State management
  const [search, setSearch] = useState('');
  const [selectedBridge, setSelectedBridge] = useState<string | undefined>(undefined);
  const [selectedTeam, setSelectedTeam] = useState<string | undefined>(Array.isArray(teamFilter) ? undefined : teamFilter);
  const [selectedRegion, setSelectedRegion] = useState<string | undefined>(undefined);
  const [viewMode, setViewMode] = useState<'table' | 'grid'>('table');
  const [groupBy, setGroupBy] = useState<'bridge' | 'team' | 'region' | 'repository' | 'mounted' | 'unmounted' | 'grand'>('bridge');
  const [internalExpandedRowKeys, setInternalExpandedRowKeys] = useState<string[]>([]);
  const [expansionTimestamps, setExpansionTimestamps] = useState<Record<string, number>>({});
  const [internalRefreshKeys, setInternalRefreshKeys] = useState<Record<string, number>>({});
  
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


  // Queries only - mutations are handled by parent
  const { data: machines = [], isLoading } = useMachines(teamFilter, enabled);
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
  const regions = dropdownData?.regions || [];
  const bridges = useMemo(() => {
    if (!dropdownData?.bridgesByRegion) return [];
    const allBridges: Array<{ value: string; label: string }> = [];
    dropdownData.bridgesByRegion.forEach(region => {
      if (region.bridges && Array.isArray(region.bridges)) {
        region.bridges.forEach(bridge => {
          if (!allBridges.find(b => b.value === bridge.value)) {
            allBridges.push(bridge);
          }
        });
      }
    });
    return allBridges;
  }, [dropdownData]);

  // Filter machines based on selections
  const filteredMachines = useMemo(() => {
    const filtered = machines.filter((machine) => {
      const matchesSearch = search === '' || 
        machine.machineName.toLowerCase().includes(search.toLowerCase());
      const matchesBridge = !selectedBridge || machine.bridgeName === selectedBridge;
      const matchesTeam = !selectedTeam || machine.teamName === selectedTeam;
      const matchesRegion = !selectedRegion || machine.regionName === selectedRegion;
      
      return matchesSearch && matchesBridge && matchesTeam && matchesRegion;
    });
    return filtered;
  }, [machines, search, selectedBridge, selectedTeam, selectedRegion]);

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

  // Group machines for grid view
  const groupedData = useMemo(() => {
    if (viewMode !== 'grid') return {};
    
    if (groupBy === 'repository' || groupBy === 'mounted' || groupBy === 'unmounted' || groupBy === 'grand') {
      // For repository-based grouping, we need to create entries per repository
      const result: Record<string, Array<{machine: Machine, repository?: any}>> = {};
      
      filteredMachines.forEach(machine => {
        const machineRepos = getMachineRepositories(machine);
        
        if (groupBy === 'repository') {
          // Group by individual repositories
          if (machineRepos.length === 0) {
            const key = 'No Repositories';
            if (!result[key]) result[key] = [];
            result[key].push({ machine });
          } else {
            machineRepos.forEach(repo => {
              const key = repo.name;
              if (!result[key]) result[key] = [];
              result[key].push({ machine, repository: repo });
            });
          }
        } else if (groupBy === 'mounted') {
          const mountedRepos = machineRepos.filter(r => r.mounted);
          if (mountedRepos.length === 0) {
            const key = 'No Mounted Repositories';
            if (!result[key]) result[key] = [];
            result[key].push({ machine });
          } else {
            mountedRepos.forEach(repo => {
              const key = 'Mounted Repositories';
              if (!result[key]) result[key] = [];
              result[key].push({ machine, repository: repo });
            });
          }
        } else if (groupBy === 'unmounted') {
          const unmountedRepos = machineRepos.filter(r => !r.mounted);
          if (unmountedRepos.length === 0) {
            const key = 'No Unmounted Repositories';
            if (!result[key]) result[key] = [];
            result[key].push({ machine });
          } else {
            unmountedRepos.forEach(repo => {
              const key = 'Unmounted Repositories';
              if (!result[key]) result[key] = [];
              result[key].push({ machine, repository: repo });
            });
          }
        } else if (groupBy === 'grand') {
          // Group by grand repository
          machineRepos.forEach(repo => {
            if (repo.grandGuid) {
              const grandRepo = repositories.find(r => r.repositoryGuid === repo.grandGuid);
              const key = grandRepo ? grandRepo.repositoryName : 'Unknown Grand';
              if (!result[key]) result[key] = [];
              result[key].push({ machine, repository: repo });
            } else {
              const key = 'No Grand Repository';
              if (!result[key]) result[key] = [];
              result[key].push({ machine, repository: repo });
            }
          });
        }
      });
      
      return result;
    } else {
      // For machine-based grouping (bridge, team, region)
      return filteredMachines.reduce((acc, machine) => {
        let key = '';
        if (groupBy === 'bridge') {
          key = machine.bridgeName;
        } else if (groupBy === 'team') {
          key = machine.teamName;
        } else if (groupBy === 'region') {
          key = machine.regionName || 'Unknown';
        }
        
        if (!acc[key]) acc[key] = [];
        acc[key].push({ machine });
        return acc;
      }, {} as Record<string, Array<{machine: Machine, repository?: any}>>);
    }
  }, [filteredMachines, viewMode, groupBy, repositories]);

  const handleDelete = useCallback((machine: Machine) => {
    if (onDeleteMachine) {
      onDeleteMachine(machine);
    }
  }, [onDeleteMachine]);





  // Get machine functions
  const { getFunctionsByCategory } = useLocalizedFunctions();
  const machineFunctions = useMemo(() => 
    getFunctionsByCategory('machine').filter(func => func.showInMenu !== false), 
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
        filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }) => (
          <div style={{ padding: 8 }}>
            <Input
              placeholder={t('machines:searchMachineName')}
              value={selectedKeys[0]}
              onChange={e => setSelectedKeys(e.target.value ? [e.target.value] : [])}
              onPressEnter={() => confirm()}
              style={{ marginBottom: 8, display: 'block' }}
            />
            <Space>
              <Button
                type="primary"
                onClick={() => confirm()}
                icon={<SearchOutlined />}
                size="small"
                style={{ width: 90 }}
              >
                {t('common:actions.search')}
              </Button>
              <Button
                onClick={() => clearFilters && clearFilters()}
                size="small"
                style={{ width: 90 }}
              >
                {t('common:actions.reset')}
              </Button>
            </Space>
          </div>
        ),
        filterIcon: (filtered: boolean) => (
          <SearchOutlined style={{ color: filtered ? '#1890ff' : undefined }} />
        ),
        onFilter: (value: string | number | boolean, record: Machine) => 
          record.machineName.toLowerCase().includes(value.toString().toLowerCase()),
      },
      {
        title: t('machines:team'),
        dataIndex: 'teamName',
        key: 'teamName',
        width: 150,
        ellipsis: true,
        render: (teamName: string) => <Tag color="#8FBC8F">{teamName}</Tag>,
        sorter: (a: Machine, b: Machine) => a.teamName.localeCompare(b.teamName),
      },
    );

    // Add team/bridge/region columns in expert mode
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

    // Queue items column
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

    // Last updated column
    baseColumns.push({
      title: t('machines:lastUpdated'),
      dataIndex: 'vaultStatusTime',
      key: 'vaultStatusTime',
      width: 180,
      render: (time: string) => {
        const relativeTime = getLocalizedRelativeTime(time, t);
        const formattedTime = formatTimestamp(time);
        
        return (
          <span title={formattedTime}>
            {relativeTime}
          </span>
        );
      },
      sorter: (a: Machine, b: Machine) => {
        const timeA = a.vaultStatusTime ? new Date(a.vaultStatusTime).getTime() : 0;
        const timeB = b.vaultStatusTime ? new Date(b.vaultStatusTime).getTime() : 0;
        return timeA - timeB;
      },
    });

    // Vault version in expert mode
    if (isExpertMode) {
      baseColumns.push({
        title: t('machines:vaultVersion'),
        dataIndex: 'vaultVersion',
        key: 'vaultVersion',
        width: 100,
        align: 'center' as const,
        sorter: (a: Machine, b: Machine) => a.vaultVersion - b.vaultVersion,
        render: (version: number) => <Tag>{t('common:general.versionFormat', { version })}</Tag>,
      });
    }

    // Actions column last if showActions is true
    if (showActions) {
      baseColumns.push({
        title: t('common:table.actions'),
        key: 'actions',
        width: 350,
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
                  }
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

  // Render filters section
  const renderFilters = () => {
    if (!showFilters) return null;

    return (
      <div style={{ marginBottom: 16 }}>
        <Space wrap size="middle">
          <Input
            key={t('machines:searchPlaceholder')}
            placeholder={t('machines:searchPlaceholder')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 250 }}
            prefix={<SearchOutlined />}
          />
          
          {isExpertMode && (
            <>
              <Select
                style={{ width: 200 }}
                placeholder={t('machines:filterByRegion')}
                allowClear
                value={selectedRegion}
                onChange={setSelectedRegion}
                suffixIcon={<FilterOutlined />}
              >
                {regions.map((region) => (
                  <Option key={region.value} value={region.value}>
                    {region.label}
                  </Option>
                ))}
              </Select>

              <Select
                style={{ width: 200 }}
                placeholder={t('machines:filterByBridge')}
                allowClear
                value={selectedBridge}
                onChange={setSelectedBridge}
                suffixIcon={<FilterOutlined />}
              >
                {bridges.map((bridge) => (
                  <Option key={bridge.value} value={bridge.value}>
                    {bridge.label}
                  </Option>
                ))}
              </Select>
            </>
          )}

        </Space>
      </div>
    );
  };

  // Render view mode toggle
  const renderViewToggle = () => {
    if (!isExpertMode) return null;

    return (
      <div style={{ marginBottom: 16 }}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space align="center">
            <span style={{ marginRight: 8, fontWeight: 500 }}>{t('machines:viewMode')}:</span>
            <Segmented
              options={[
                { label: t('machines:tableView'), value: 'table', icon: <TableOutlined /> },
                { label: t('machines:gridView'), value: 'grid', icon: <AppstoreOutlined /> },
              ]}
              value={viewMode}
              onChange={(value) => setViewMode(value as 'table' | 'grid')}
            />
          </Space>
          
          {viewMode === 'grid' && (
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
                <Radio.Button value="region">
                  <Space>
                    <GlobalOutlined />
                    {t('machines:groupByRegion')}
                  </Space>
                </Radio.Button>
                <Radio.Button value="repository">
                  <Space>
                    <InboxOutlined />
                    {t('machines:groupByRepository')}
                  </Space>
                </Radio.Button>
                <Radio.Button value="mounted">
                  <Space>
                    <CheckCircleOutlined />
                    {t('machines:groupByMounted')}
                  </Space>
                </Radio.Button>
                <Radio.Button value="unmounted">
                  <Space>
                    <CloseCircleOutlined />
                    {t('machines:groupByUnmounted')}
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
          )}
        </Space>
      </div>
    );
  };

  // Render embedded mode alert (removed since we're enabling full functionality)

  // Render grid view
  const renderGridView = () => {
    const getGroupColor = () => {
      switch (groupBy) {
        case 'bridge': return 'green';
        case 'team': return '#8FBC8F';
        case 'region': return 'purple';
        case 'repository': return '#556b2f';
        case 'mounted': return 'success';
        case 'unmounted': return 'warning';
        case 'grand': return 'blue';
        default: return 'default';
      }
    };

    const renderRepositoryCard = (item: {machine: Machine, repository?: any}) => {
      const { machine, repository } = item;
      
      return (
        <Col xs={24} sm={12} md={8} lg={6} xl={4} key={`${machine.machineName}-${repository?.name || 'no-repo'}`}>
          <Card
            size="small"
            hoverable
            style={{ height: '100%' }}
            actions={showActions ? [
              <Tooltip title={t('machines:editMachine')}>
                <EditOutlined onClick={() => onEditMachine && onEditMachine(machine)} />
              </Tooltip>,
              <Tooltip title={t('machines:runFunction')}>
                <FunctionOutlined onClick={() => onFunctionsMachine && onFunctionsMachine(machine)} />
              </Tooltip>,
              <Tooltip title={t('machines:delete')}>
                <DeleteOutlined onClick={() => handleDelete(machine)} />
              </Tooltip>,
            ] : undefined}
          >
            <Card.Meta
              title={
                <Space direction="vertical" size={0} style={{ width: '100%' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <DesktopOutlined style={{ color: '#556b2f' }} />
                    <strong style={{ fontSize: 14 }}>{machine.machineName}</strong>
                  </div>
                  {repository && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                      <InboxOutlined style={{ color: '#8B4513' }} />
                      <span style={{ fontSize: 13, fontWeight: 500 }}>{repository.name}</span>
                    </div>
                  )}
                </Space>
              }
              description={
                <Space direction="vertical" size={4} style={{ width: '100%', marginTop: 8 }}>
                  {/* Tags Section */}
                  <Space wrap size={4}>
                    <Tag color="#8FBC8F" style={{ margin: 0, fontSize: 11 }}>{machine.teamName}</Tag>
                    {machine.regionName && (
                      <Tag color="purple" style={{ margin: 0, fontSize: 11 }}>{machine.regionName}</Tag>
                    )}
                    <Tag color="green" style={{ margin: 0, fontSize: 11 }}>{machine.bridgeName}</Tag>
                  </Space>
                  
                  {/* Repository Info */}
                  {repository && (
                    <>
                      <Space wrap size={4}>
                        {repository.mounted && (
                          <Tag icon={<CheckCircleOutlined />} color="blue" style={{ margin: 0, fontSize: 11 }}>
                            {t('resources:repositories.mounted')}
                          </Tag>
                        )}
                        {repository.accessible && (
                          <Tag color="green" style={{ margin: 0, fontSize: 11 }}>
                            {t('resources:repositories.accessible')}
                          </Tag>
                        )}
                        {repository.docker_running && (
                          <Tag color="cyan" style={{ margin: 0, fontSize: 11 }}>
                            {repository.container_count} {t('resources:repositories.containers')}
                          </Tag>
                        )}
                        {repository.has_services && (
                          <Tag color="orange" style={{ margin: 0, fontSize: 11 }}>
                            {repository.service_count} {t('resources:repositories.services')}
                          </Tag>
                        )}
                      </Space>
                      
                      {/* Repository Size and Disk Usage */}
                      <div style={{ fontSize: 12, color: '#666' }}>
                        <Space>
                          <HddOutlined />
                          <span>{repository.size_human}</span>
                        </Space>
                      </div>
                      
                      {repository.disk_space && repository.mounted && (
                        <div style={{ marginTop: 4 }}>
                          <Progress 
                            percent={parseInt(repository.disk_space.use_percent)} 
                            size="small"
                            strokeWidth={4}
                            status={parseInt(repository.disk_space.use_percent) > 90 ? 'exception' : 'normal'}
                            format={(percent) => `${percent}%`}
                          />
                          <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                            {repository.disk_space.used} / {repository.disk_space.total}
                          </div>
                        </div>
                      )}
                      
                      {/* Last Modified */}
                      <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>
                        {t('resources:repositories.lastModified')}: {repository.modified_human}
                      </div>
                    </>
                  )}
                  
                  {/* Machine Stats */}
                  <div style={{ marginTop: 4, paddingTop: 4, borderTop: '1px solid #f0f0f0' }}>
                    <Space size="small">
                      <Badge count={machine.queueCount} showZero style={{ backgroundColor: machine.queueCount > 0 ? '#52c41a' : '#d9d9d9' }}>
                        <span style={{ fontSize: 11, color: '#666' }}>{t('machines:queue')}</span>
                      </Badge>
                      {machine.vaultStatusTime && (
                        <span style={{ fontSize: 11, color: '#999' }}>
                          {getLocalizedRelativeTime(machine.vaultStatusTime, t)}
                        </span>
                      )}
                    </Space>
                  </div>
                </Space>
              }
            />
          </Card>
        </Col>
      );
    };

    return (
      <Row gutter={[16, 16]}>
        {Object.entries(groupedData).map(([groupKey, items]) => (
          <Col span={24} key={groupKey}>
            <Card
              title={
                <Space>
                  <Tag color={getGroupColor()} style={{ fontSize: '14px' }}>
                    {groupKey}
                  </Tag>
                  <span style={{ fontSize: '14px', color: '#666' }}>
                    {items.length} {t('machines:itemCount', { count: items.length })}
                  </span>
                </Space>
              }
              bodyStyle={{ padding: '12px' }}
            >
              <Row gutter={[12, 12]}>
                {items.map((item) => renderRepositoryCard(item))}
              </Row>
            </Card>
          </Col>
        ))}
      </Row>
    );
  };


  return (
    <div className={className}>
      {renderFilters()}
      {renderViewToggle()}
      
      {viewMode === 'table' ? (
        <div ref={tableContainerRef} style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <Table
            columns={columns}
            dataSource={filteredMachines}
            rowKey="machineName"
            loading={isLoading}
            scroll={{ x: 'max-content', y: 'calc(100vh - 400px)' }}
            pagination={{
              pageSize: dynamicPageSize,
              showSizeChanger: false,
              showTotal: (total, range) => t('common:table.showingRecords', { start: range[0], end: range[1], total }),
            }}
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
              }
            }}
            sticky
          />
        </div>
      ) : (
        renderGridView()
      )}

      {/* Modals */}
      <AuditTraceModal
        open={auditTraceModal.open}
        onCancel={() => setAuditTraceModal({ open: false, entityType: null, entityIdentifier: null })}
        entityType={auditTraceModal.entityType}
        entityIdentifier={auditTraceModal.entityIdentifier}
        entityName={auditTraceModal.entityName}
      />
    </div>
  );
};