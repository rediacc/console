import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
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
  message,
  Row,
  Col,
  Segmented,
  Form,
  Typography,
  Slider,
  Empty,
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
} from '@ant-design/icons';
import { useMachines, useDeleteMachine, useCreateMachine, useUpdateMachineName, useUpdateMachineBridge, useUpdateMachineVault } from '@/api/queries/machines';
import { useTeams } from '@/api/queries/teams';
import { useDropdownData } from '@/api/queries/useDropdownData';
import { useCreateRepository } from '@/api/queries/repositories';
import ResourceForm from '@/components/forms/ResourceForm';
import ResourceFormWithVault from '@/components/forms/ResourceFormWithVault';
import VaultEditorModal from '@/components/common/VaultEditorModal';
import type { Machine } from '@/types';
import { useSelector } from 'react-redux';
import { RootState } from '@/store/store';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { createMachineSchema, CreateMachineForm, editMachineSchema, EditMachineForm } from '@/utils/validation';
import { type QueueFunction, useCreateQueueItem } from '@/api/queries/queue';
import { useLocalizedFunctions } from '@/services/functionsService';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import { 
  FunctionOutlined,
  HistoryOutlined 
} from '@ant-design/icons';
import { useDynamicPageSize } from '@/hooks/useDynamicPageSize';
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import QueueItemTraceModal from '@/components/common/QueueItemTraceModal';

const { Option } = Select;
const { Search } = Input;
const { Title, Text, Paragraph } = Typography;

interface MachineTableProps {
  teamFilter?: string | string[];
  showFilters?: boolean;
  showActions?: boolean;
  className?: string;
  showCreateModal?: boolean;
  onCreateModalChange?: (show: boolean) => void;
  enabled?: boolean;
}

export const MachineTable: React.FC<MachineTableProps> = ({
  teamFilter,
  showFilters = true,
  showActions = true,
  className = '',
  showCreateModal: externalShowCreateModal,
  onCreateModalChange,
  enabled = true,
}) => {
  const { t } = useTranslation(['machines', 'common', 'functions']);
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const isExpertMode = uiMode === 'expert';
  
  // Ref for table container
  const tableContainerRef = useRef<HTMLDivElement>(null);

  // State management
  const [search, setSearch] = useState('');
  const [selectedBridge, setSelectedBridge] = useState<string | undefined>(undefined);
  const [selectedTeam, setSelectedTeam] = useState<string | undefined>(Array.isArray(teamFilter) ? undefined : teamFilter);
  const [selectedRegion, setSelectedRegion] = useState<string | undefined>(undefined);
  const [viewMode, setViewMode] = useState<'table' | 'grid'>('table');
  const [groupBy, setGroupBy] = useState<'bridge' | 'team' | 'region'>('bridge');
  const [internalShowCreateModal, setInternalShowCreateModal] = useState(false);
  const [editingMachine, setEditingMachine] = useState<Machine | null>(null);
  const [vaultMachine, setVaultMachine] = useState<Machine | null>(null);
  const [functionModalMachine, setFunctionModalMachine] = useState<Machine | null>(null);
  const [auditTraceModal, setAuditTraceModal] = useState<{
    open: boolean
    entityType: string | null
    entityIdentifier: string | null
    entityName?: string
  }>({ open: false, entityType: null, entityIdentifier: null });
  const [queueTraceModal, setQueueTraceModal] = useState<{
    visible: boolean
    taskId: string | null
  }>({ visible: false, taskId: null });
  
  // Refs for form components
  const createFormRef = useRef<any>(null);
  
  // Use external control if provided, otherwise use internal state
  const showCreateModal = externalShowCreateModal !== undefined ? externalShowCreateModal : internalShowCreateModal;
  const setShowCreateModal = (show: boolean) => {
    if (onCreateModalChange) {
      onCreateModalChange(show);
    } else {
      setInternalShowCreateModal(show);
    }
  };


  // Queries and mutations
  const { data: machines = [], isLoading } = useMachines(teamFilter, enabled);
  const { data: dropdownData } = useDropdownData();
  const { data: teamsData = [] } = useTeams();
  const deleteMachine = useDeleteMachine();
  const createMachineMutation = useCreateMachine();
  const updateMachineNameMutation = useUpdateMachineName();
  const updateMachineBridgeMutation = useUpdateMachineBridge();
  const updateMachineVaultMutation = useUpdateMachineVault();
  const createQueueItemMutation = useCreateQueueItem();
  const createRepositoryMutation = useCreateRepository();
  const { buildQueueVault } = useQueueVaultBuilder();
  
  // Dynamic page size
  const dynamicPageSize = useDynamicPageSize(tableContainerRef, {
    containerOffset: 150, // Account for filters, tabs, and other UI elements
    minRows: 5,
    maxRows: 50
  });

  // Create a simple mode schema that only requires machineName
  const simpleMachineSchema = React.useMemo(() => 
    z.object({
      machineName: z.string().min(1, 'Machine name is required').max(100, 'Machine name must be less than 100 characters'),
      teamName: z.string().optional(),
      regionName: z.string().optional(),
      bridgeName: z.string().optional(),
      machineVault: z.string().optional().default('{}'),
    }),
    []
  );

  // Machine form setup - recreate when uiMode changes
  const machineForm = useForm<CreateMachineForm>({
    resolver: zodResolver(uiMode === 'simple' ? simpleMachineSchema : createMachineSchema) as any,
    defaultValues: {
      teamName: uiMode === 'simple' ? 'Private Team' : '',
      machineName: '',
      regionName: uiMode === 'simple' ? 'Default Region' : '',
      bridgeName: uiMode === 'simple' ? 'Global Bridges' : '',
      machineVault: '{}',
    },
  });

  // Edit machine form setup
  const editMachineForm = useForm<EditMachineForm>({
    resolver: zodResolver(editMachineSchema) as any,
    defaultValues: {
      machineName: '',
      regionName: '',
      bridgeName: '',
    },
  });

  // Watch form values for dependent fields
  const selectedRegionForMachine = machineForm.watch('regionName');
  const selectedRegionForEdit = editMachineForm.watch('regionName');

  // Get filtered bridges based on selected region
  const filteredBridgesForMachine = React.useMemo(() => {
    if (!selectedRegionForMachine || !dropdownData?.bridgesByRegion) return [];
    
    const regionData = dropdownData.bridgesByRegion.find(
      (r: any) => r.regionName === selectedRegionForMachine
    );
    return regionData?.bridges?.map((b: any) => ({ 
      value: b.value, 
      label: b.label 
    })) || [];
  }, [selectedRegionForMachine, dropdownData]);

  const filteredBridgesForEdit = React.useMemo(() => {
    if (!selectedRegionForEdit || !dropdownData?.bridgesByRegion) return [];
    
    const regionData = dropdownData.bridgesByRegion.find(
      (r: any) => r.regionName === selectedRegionForEdit
    );
    return regionData?.bridges?.map((b: any) => ({ 
      value: b.value, 
      label: b.label 
    })) || [];
  }, [selectedRegionForEdit, dropdownData]);

  // Clear bridge selection when region changes
  React.useEffect(() => {
    const currentBridge = machineForm.getValues('bridgeName');
    if (currentBridge && !filteredBridgesForMachine.find((b: any) => b.value === currentBridge)) {
      machineForm.setValue('bridgeName', '');
    }
  }, [selectedRegionForMachine, filteredBridgesForMachine, machineForm]);

  React.useEffect(() => {
    const currentBridge = editMachineForm.getValues('bridgeName');
    if (currentBridge && !filteredBridgesForEdit.find((b: any) => b.value === currentBridge)) {
      editMachineForm.setValue('bridgeName', '');
    }
  }, [selectedRegionForEdit, filteredBridgesForEdit, editMachineForm]);


  // Get unique values for filters
  const teams = dropdownData?.teams || [];
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
    return machines.filter((machine) => {
      const matchesSearch = search === '' || 
        machine.machineName.toLowerCase().includes(search.toLowerCase());
      const matchesBridge = !selectedBridge || machine.bridgeName === selectedBridge;
      const matchesTeam = !selectedTeam || machine.teamName === selectedTeam;
      const matchesRegion = !selectedRegion || machine.regionName === selectedRegion;
      
      return matchesSearch && matchesBridge && matchesTeam && matchesRegion;
    });
  }, [machines, search, selectedBridge, selectedTeam, selectedRegion]);

  // Group machines for grid view
  const groupedMachines = useMemo(() => {
    if (viewMode !== 'grid') return {};
    
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
      acc[key].push(machine);
      return acc;
    }, {} as Record<string, Machine[]>);
  }, [filteredMachines, viewMode, groupBy]);

  const handleDelete = useCallback(async (machine: Machine) => {
    Modal.confirm({
      title: t('machines:confirmDelete'),
      content: t('machines:deleteWarning', { name: machine.machineName }),
      okText: t('common:actions.delete'),
      okType: 'danger',
      cancelText: t('common:actions.cancel'),
      onOk: async () => {
        try {
          await deleteMachine.mutateAsync({
            machineName: machine.machineName,
            teamName: machine.teamName,
          });
          message.success(t('machines:deleteSuccess'));
        } catch (error) {
          message.error(t('machines:deleteError'));
        }
      },
    });
  }, [deleteMachine, t]);


  // Handle create machine
  const handleCreateMachine = async (data: CreateMachineForm) => {
    try {
      // In simple mode, ensure default values are used
      const formData = {
        teamName: uiMode === 'simple' ? 'Private Team' : data.teamName,
        regionName: uiMode === 'simple' ? 'Default Region' : data.regionName,
        bridgeName: uiMode === 'simple' ? 'Global Bridges' : data.bridgeName,
        machineName: data.machineName,
        machineVault: data.machineVault || '{}'
      };
      
      await createMachineMutation.mutateAsync({
        teamName: formData.teamName,
        bridgeName: formData.bridgeName,
        machineName: formData.machineName,
        machineVault: formData.machineVault
      });
      setShowCreateModal(false);
      machineForm.reset();
      message.success(t('machines:createSuccess'));
    } catch (error) {
      // Error handled by mutation
    }
  };

  // Handle edit machine
  const handleEditMachine = async (data: EditMachineForm) => {
    if (!editingMachine) return;
    
    try {
      // Check if name changed
      if (data.machineName !== editingMachine.machineName) {
        await updateMachineNameMutation.mutateAsync({
          teamName: editingMachine.teamName,
          currentMachineName: editingMachine.machineName,
          newMachineName: data.machineName,
        });
      }
      
      // Check if bridge changed
      if (data.bridgeName !== editingMachine.bridgeName) {
        await updateMachineBridgeMutation.mutateAsync({
          teamName: editingMachine.teamName,
          machineName: data.machineName,
          newBridgeName: data.bridgeName,
        });
      }
      
      message.success(t('machines:updateSuccess'));
      setEditingMachine(null);
      editMachineForm.reset();
    } catch (error) {
      // Error handled by mutation
    }
  };

  // Handle update vault
  const handleUpdateVault = async (vault: string, version: number) => {
    if (!vaultMachine) return;
    
    try {
      await updateMachineVaultMutation.mutateAsync({
        teamName: vaultMachine.teamName,
        machineName: vaultMachine.machineName,
        machineVault: vault,
        vaultVersion: version,
      });
      message.success(t('machines:vaultUpdateSuccess'));
      setVaultMachine(null);
    } catch (error) {
      // Error handled by mutation
    }
  };


  // Handle function selection from modal
  const handleFunctionSelected = async (functionData: {
    function: QueueFunction;
    params: Record<string, any>;
    priority: number;
    description: string;
  }) => {
    if (!functionModalMachine) return;

    try {
      // Check if this is repo_new function - if so, create repository first
      if (functionData.function.name === 'repo_new') {
        const repoName = functionData.params.repo;
        if (!repoName) {
          message.error('Repository name is required for repo_new function');
          return;
        }

        // Create repository in the system first
        try {
          await createRepositoryMutation.mutateAsync({
            teamName: functionModalMachine.teamName,
            repositoryName: repoName,
            repositoryVault: '{}'
          });
        } catch (error: any) {
          // If repository creation fails, don't proceed with queue item
          return;
        }
      }

      // Find the team vault data
      const teamData = teamsData.find(t => t.teamName === functionModalMachine.teamName)
      // TODO: Repository vault would need a separate query - not available in dropdown data
      const repoData = null

      // Build the queue vault with context data
      const queueVault = await buildQueueVault({
        teamName: functionModalMachine.teamName,
        machineName: functionModalMachine.machineName,
        bridgeName: functionModalMachine.bridgeName,
        repositoryName: functionData.params.repo, // Include if repo param exists
        functionName: functionData.function.name,
        params: functionData.params,
        priority: functionData.priority,
        description: functionData.description,
        addedVia: 'machine-table',
        // Pass vault data
        machineVault: functionModalMachine.vaultContent || '{}',
        teamVault: teamData?.vaultContent || '{}',
        repositoryVault: repoData?.vaultContent || '{}'
      });

      const response = await createQueueItemMutation.mutateAsync({
        teamName: functionModalMachine.teamName,
        machineName: functionModalMachine.machineName,
        bridgeName: functionModalMachine.bridgeName,
        queueVault,
        priority: functionData.priority
      });
      
      // Reset the modal
      setFunctionModalMachine(null);
      
      // Automatically open the trace modal if queue item was created successfully
      if (response?.taskId) {
        message.success(t('machines:queueItemCreated'));
        setQueueTraceModal({ visible: true, taskId: response.taskId });
      }
    } catch (error) {
      // Error is handled by the mutation
    }
  };

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
              type="link"
              icon={<KeyOutlined />}
              onClick={() => setVaultMachine(record)}
            >
              {t('machines:vault')}
            </Button>
            <Button
              type="link"
              icon={<EditOutlined />}
              onClick={() => {
                setEditingMachine(record);
                // Find the region for this machine's bridge
                const region = dropdownData?.bridgesByRegion?.find(r => 
                  r.bridges?.some(b => b.value === record.bridgeName)
                );
                editMachineForm.reset({
                  machineName: record.machineName,
                  regionName: region?.regionName || '',
                  bridgeName: record.bridgeName,
                });
              }}
            >
              {t('common:actions.edit')}
            </Button>
            <Button
              type="link"
              icon={<FunctionOutlined />}
              onClick={() => setFunctionModalMachine(record)}
            >
              {t('machines:functions')}
            </Button>
            <Button
              type="link"
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
              type="link"
              danger
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
  }, [isExpertMode, uiMode, showActions, t, handleDelete, dropdownData, editMachineForm]);

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
        <Space align="center" size="large">
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
            <Space align="center">
              <span style={{ marginRight: 8, fontWeight: 500 }}>{t('machines:groupBy')}:</span>
              <Select
                style={{ width: 150 }}
                value={groupBy}
                onChange={setGroupBy}
              >
                <Option value="bridge">{t('machines:groupByBridge')}</Option>
                <Option value="team">{t('machines:groupByTeam')}</Option>
                <Option value="region">{t('machines:groupByRegion')}</Option>
              </Select>
            </Space>
          )}
        </Space>
      </div>
    );
  };

  // Render embedded mode alert (removed since we're enabling full functionality)

  // Render grid view
  const renderGridView = () => {
    return (
      <Row gutter={[16, 16]}>
        {Object.entries(groupedMachines).map(([groupKey, machines]) => (
          <Col span={24} key={groupKey}>
            <Card
              title={
                <Space>
                  <Tag color={groupBy === 'bridge' ? 'green' : groupBy === 'team' ? '#8FBC8F' : 'purple'} style={{ fontSize: '14px' }}>
                    {groupKey}
                  </Tag>
                  <span style={{ fontSize: '14px', color: '#666' }}>
                    {machines.length} {t('machines:machineCount', { count: machines.length })}
                  </span>
                </Space>
              }
            >
              <Row gutter={[16, 16]}>
                {machines.map((machine) => (
                  <Col xs={24} sm={12} md={8} lg={6} key={machine.machineName}>
                    <Card
                      size="small"
                      hoverable
                      actions={showActions ? [
                        <KeyOutlined key="vault" onClick={() => setVaultMachine(machine)} />,
                        <EditOutlined key="edit" onClick={() => {
                          setEditingMachine(machine);
                          // Find the region for this machine's bridge
                          const region = dropdownData?.bridgesByRegion?.find(r => 
                            r.bridges?.some(b => b.value === machine.bridgeName)
                          );
                          editMachineForm.reset({
                            machineName: machine.machineName,
                            regionName: region?.regionName || '',
                            bridgeName: machine.bridgeName,
                          });
                        }} />,
                        <DeleteOutlined key="delete" onClick={() => handleDelete(machine)} />,
                      ] : undefined}
                    >
                      <Card.Meta
                        title={machine.machineName}
                        description={
                          <Space direction="vertical" size="small" style={{ width: '100%' }}>
                            {groupBy !== 'team' && (
                              <div>
                                <Tag color="#8FBC8F" style={{ marginRight: 4 }}>{machine.teamName}</Tag>
                              </div>
                            )}
                            {groupBy !== 'region' && machine.regionName && (
                              <div>
                                <Tag color="purple" style={{ marginRight: 4 }}>{machine.regionName}</Tag>
                              </div>
                            )}
                            {groupBy !== 'bridge' && (
                              <div>
                                <Tag color="green" style={{ marginRight: 4 }}>{machine.bridgeName}</Tag>
                              </div>
                            )}
                            <div style={{ fontSize: '12px', color: '#666' }}>
                              {t('machines:queueItems')}: {machine.queueCount}
                            </div>
                            {isExpertMode && (
                              <div style={{ fontSize: '12px', color: '#666' }}>
                                {t('machines:vaultVersion')}: {machine.vaultVersion}
                              </div>
                            )}
                          </Space>
                        }
                      />
                    </Card>
                  </Col>
                ))}
              </Row>
            </Card>
          </Col>
        ))}
      </Row>
    );
  };

  // Machine form fields
  const { t: tRes } = useTranslation('resources');
  
  // Determine if team is already selected/known
  const isTeamPreselected = uiMode === 'simple' || 
    selectedTeam || 
    (teamFilter && !Array.isArray(teamFilter)) || 
    (teamFilter && Array.isArray(teamFilter) && teamFilter.length === 1);
  
  const machineFormFields = uiMode === 'simple' 
    ? [
        {
          name: 'machineName',
          label: tRes('machines.machineName'),
          placeholder: tRes('machines.placeholders.enterMachineName'),
          required: true,
        },
      ]
    : isTeamPreselected
    ? [
        {
          name: 'regionName',
          label: tRes('general.region'),
          placeholder: tRes('regions.placeholders.selectRegion'),
          required: true,
          type: 'select' as const,
          options: dropdownData?.regions?.map((r: any) => ({ value: r.value, label: r.label })) || [],
        },
        {
          name: 'bridgeName',
          label: tRes('bridges.bridge'),
          placeholder: selectedRegionForMachine ? tRes('bridges.placeholders.selectBridge') : tRes('bridges.placeholders.selectRegionFirst'),
          required: true,
          type: 'select' as const,
          options: filteredBridgesForMachine,
          disabled: !selectedRegionForMachine,
        },
        {
          name: 'machineName',
          label: tRes('machines.machineName'),
          placeholder: tRes('machines.placeholders.enterMachineName'),
          required: true,
        },
      ]
    : [
        {
          name: 'teamName',
          label: tRes('general.team'),
          placeholder: tRes('teams.placeholders.selectTeam'),
          required: true,
          type: 'select' as const,
          options: dropdownData?.teams?.map(t => ({ value: t.value, label: t.label })) || [],
        },
        {
          name: 'regionName',
          label: tRes('general.region'),
          placeholder: tRes('regions.placeholders.selectRegion'),
          required: true,
          type: 'select' as const,
          options: dropdownData?.regions?.map((r: any) => ({ value: r.value, label: r.label })) || [],
        },
        {
          name: 'bridgeName',
          label: tRes('bridges.bridge'),
          placeholder: selectedRegionForMachine ? tRes('bridges.placeholders.selectBridge') : tRes('bridges.placeholders.selectRegionFirst'),
          required: true,
          type: 'select' as const,
          options: filteredBridgesForMachine,
          disabled: !selectedRegionForMachine,
        },
        {
          name: 'machineName',
          label: tRes('machines.machineName'),
          placeholder: tRes('machines.placeholders.enterMachineName'),
          required: true,
        },
      ];

  // Edit machine form fields
  const editMachineFormFields = [
    {
      name: 'machineName',
      label: tRes('machines.machineName'),
      placeholder: tRes('machines.placeholders.enterMachineName'),
      required: true,
    },
    {
      name: 'regionName',
      label: tRes('general.region'),
      placeholder: tRes('regions.placeholders.selectRegion'),
      required: true,
      type: 'select' as const,
      options: dropdownData?.regions?.map((r: any) => ({ value: r.value, label: r.label })) || [],
    },
    {
      name: 'bridgeName',
      label: tRes('bridges.bridge'),
      placeholder: selectedRegionForEdit ? tRes('bridges.placeholders.selectBridge') : tRes('bridges.placeholders.selectRegionFirst'),
      required: true,
      type: 'select' as const,
      options: filteredBridgesForEdit,
      disabled: !selectedRegionForEdit,
    },
  ];

  // Set preset team when modal opens
  React.useEffect(() => {
    if (showCreateModal) {
      let teamToSet = '';
      if (selectedTeam) {
        teamToSet = selectedTeam;
      } else if (teamFilter) {
        // If teamFilter is an array, only set if there's exactly one team
        if (Array.isArray(teamFilter)) {
          if (teamFilter.length === 1) {
            teamToSet = teamFilter[0];
          }
        } else {
          teamToSet = teamFilter;
        }
      }
      if (teamToSet) {
        machineForm.setValue('teamName', teamToSet);
      }
      
      // Automatically select first region if available
      if (dropdownData?.regions && dropdownData.regions.length > 0) {
        const firstRegion = dropdownData.regions[0].value;
        machineForm.setValue('regionName', firstRegion);
        
        // Find and select first bridge for this region
        const regionBridges = dropdownData.bridgesByRegion?.find(
          (region: any) => region.regionName === firstRegion
        );
        
        if (regionBridges?.bridges && regionBridges.bridges.length > 0) {
          const firstBridge = regionBridges.bridges[0].value;
          machineForm.setValue('bridgeName', firstBridge);
        }
      }
    }
  }, [showCreateModal, selectedTeam, teamFilter, machineForm, dropdownData]);

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
            sticky
          />
        </div>
      ) : (
        renderGridView()
      )}

      {/* Modals */}
      <Modal
        title={(() => {
          // Determine which team(s) we're creating for
          if (uiMode === 'simple') {
            return t('machines:createMachine') + ' ' + tRes('teams.resourcesInTeam', { team: 'Private Team' });
          } else if (selectedTeam) {
            return t('machines:createMachine') + ' ' + tRes('teams.resourcesInTeam', { team: selectedTeam });
          } else if (teamFilter && !Array.isArray(teamFilter)) {
            return t('machines:createMachine') + ' ' + tRes('teams.resourcesInTeam', { team: teamFilter });
          } else if (teamFilter && Array.isArray(teamFilter) && teamFilter.length === 1) {
            return t('machines:createMachine') + ' ' + tRes('teams.resourcesInTeam', { team: teamFilter[0] });
          }
          return t('machines:createMachine');
        })()}
        open={showCreateModal}
        onCancel={() => {
          setShowCreateModal(false);
          machineForm.reset();
        }}
        footer={[
          <Button 
            key="cancel" 
            onClick={() => {
              setShowCreateModal(false);
              machineForm.reset();
            }}
          >
            {t('common:actions.cancel')}
          </Button>,
          <Button
            key="submit"
            type="primary"
            loading={createMachineMutation.isPending}
            onClick={() => createFormRef.current?.submit()}
            style={{ background: '#556b2f', borderColor: '#556b2f' }}
          >
            {t('common:actions.create')}
          </Button>
        ]}
        width={800}
        style={{ top: 20 }}
      >
        <ResourceFormWithVault
          ref={createFormRef}
          form={machineForm}
          fields={machineFormFields}
          onSubmit={handleCreateMachine}
          entityType="MACHINE"
          vaultFieldName="machineVault"
          showDefaultsAlert={uiMode === 'simple' || isTeamPreselected}
          defaultsContent={
            <Space direction="vertical" size={0}>
              {(uiMode === 'simple' || isTeamPreselected) && (
                <Text>{t('machines:team')}: {
                  uiMode === 'simple' ? 'Private Team' : 
                  selectedTeam || 
                  (!Array.isArray(teamFilter) ? teamFilter : teamFilter[0])
                }</Text>
              )}
              {uiMode === 'simple' && (
                <>
                  <Text>{t('machines:region')}: Default Region</Text>
                  <Text>{t('machines:bridge')}: Global Bridges</Text>
                </>
              )}
            </Space>
          }
        />
      </Modal>

      {/* Edit Machine Modal */}
      {editingMachine && (
        <Modal
          title={t('machines:form.title.edit')}
          open={!!editingMachine}
          onCancel={() => {
            setEditingMachine(null);
            editMachineForm.reset();
          }}
          footer={null}
        >
          <ResourceForm
            form={editMachineForm}
            fields={editMachineFormFields}
            onSubmit={handleEditMachine}
            submitText={t('common:actions.save')}
            cancelText={t('common:actions.cancel')}
            onCancel={() => {
              setEditingMachine(null);
              editMachineForm.reset();
            }}
            loading={updateMachineNameMutation.isPending || updateMachineBridgeMutation.isPending}
          />
        </Modal>
      )}

      {/* Vault Configuration Modal */}
      <VaultEditorModal
        key={vaultMachine?.machineName || 'vault-modal'}
        open={!!vaultMachine}
        onCancel={() => {
          setVaultMachine(null);
        }}
        onSave={handleUpdateVault}
        entityType="MACHINE"
        title={t('machines:form.title.vault')}
        initialVault={vaultMachine?.vaultContent || "{}"}
        initialVersion={vaultMachine?.vaultVersion || 1}
        loading={updateMachineVaultMutation.isPending}
      />

      {/* Machine Functions Modal */}
      {/* Machine Functions Modal */}
      <FunctionSelectionModal
        open={!!functionModalMachine}
        onCancel={() => setFunctionModalMachine(null)}
        onSubmit={handleFunctionSelected}
        title={t('machines:addSystemFunction')}
        subtitle={
          functionModalMachine && (
            <Space size="small">
              <Text type="secondary">{t('machines:team')}:</Text>
              <Text strong>{functionModalMachine.teamName}</Text>
              <Text type="secondary" style={{ marginLeft: 16 }}>{t('machines:machine')}:</Text>
              <Text strong>{functionModalMachine.machineName}</Text>
            </Space>
          )
        }
        allowedCategories={['machine']}
        loading={createQueueItemMutation.isPending}
      />

      {/* Audit Trace Modal */}
      <AuditTraceModal
        open={auditTraceModal.open}
        onCancel={() => setAuditTraceModal({ open: false, entityType: null, entityIdentifier: null })}
        entityType={auditTraceModal.entityType}
        entityIdentifier={auditTraceModal.entityIdentifier}
        entityName={auditTraceModal.entityName}
      />

      {/* Queue Item Trace Modal */}
      <QueueItemTraceModal
        taskId={queueTraceModal.taskId}
        visible={queueTraceModal.visible}
        onClose={() => setQueueTraceModal({ visible: false, taskId: null })}
      />
    </div>
  );
};