import React, { useState, useMemo, useCallback, useEffect } from 'react';
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
import { useDropdownData } from '@/api/queries/useDropdownData';
import ResourceForm from '@/components/forms/ResourceForm';
import VaultEditorModal from '@/components/common/VaultEditorModal';
import type { Machine } from '@/types';
import { useSelector } from 'react-redux';
import { RootState } from '@/store/store';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { createMachineSchema, CreateMachineForm, editMachineSchema, EditMachineForm } from '@/utils/validation';
import { QUEUE_FUNCTIONS, type QueueFunction } from '@/api/queries/queue';
import { useCreateQueueItem } from '@/api/queries/queue';
import { 
  FunctionOutlined 
} from '@ant-design/icons';

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
  const { t } = useTranslation(['machines', 'common']);
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const isExpertMode = uiMode === 'expert';

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
  const [selectedFunction, setSelectedFunction] = useState<QueueFunction | null>(null);
  const [functionParams, setFunctionParams] = useState<Record<string, any>>({});
  const [functionPriority, setFunctionPriority] = useState(5);
  const [functionDescription, setFunctionDescription] = useState('');
  const [functionSearchTerm, setFunctionSearchTerm] = useState('');
  
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
  const deleteMachine = useDeleteMachine();
  const createMachineMutation = useCreateMachine();
  const updateMachineNameMutation = useUpdateMachineName();
  const updateMachineBridgeMutation = useUpdateMachineBridge();
  const updateMachineVaultMutation = useUpdateMachineVault();
  const createQueueItemMutation = useCreateQueueItem();

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
      bridgeName: uiMode === 'simple' ? 'Shared Bridge' : '',
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
        bridgeName: uiMode === 'simple' ? 'Shared Bridge' : data.bridgeName,
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

  // Handle add function to queue
  const handleAddFunctionToQueue = async () => {
    if (!functionModalMachine || !selectedFunction) return;

    // Build the queue vault
    const queueVault = {
      function: selectedFunction.name,
      params: functionParams,
      priority: functionPriority,
      description: functionDescription || selectedFunction.description,
      addedVia: 'machine-table'
    };

    try {
      await createQueueItemMutation.mutateAsync({
        teamName: functionModalMachine.teamName,
        machineName: functionModalMachine.machineName,
        bridgeName: functionModalMachine.bridgeName,
        queueVault: JSON.stringify(queueVault)
      });
      
      // Reset the modal
      setFunctionModalMachine(null);
      setSelectedFunction(null);
      setFunctionParams({});
      setFunctionPriority(5);
      setFunctionDescription('');
      setFunctionSearchTerm('');
    } catch (error) {
      // Error is handled by the mutation
    }
  };

  // Filter system functions based on search
  const filteredSystemFunctions = useMemo(() => {
    const systemFunctions = Object.values(QUEUE_FUNCTIONS).filter(
      func => func.category === 'System Functions'
    );
    
    if (!functionSearchTerm) return systemFunctions;
    
    const searchLower = functionSearchTerm.toLowerCase();
    return systemFunctions.filter(
      func =>
        func.name.toLowerCase().includes(searchLower) ||
        func.description.toLowerCase().includes(searchLower)
    );
  }, [functionSearchTerm]);

  // Machine columns
  const columns: ColumnsType<Machine> = React.useMemo(() => {
    const baseColumns: ColumnsType<Machine> = [];

    // Actions column first if showActions is true
    if (showActions) {
      baseColumns.push({
        title: t('common:table.actions'),
        key: 'actions',
        width: 50,
        align: 'center' as const,
        fixed: 'left' as const,
        render: (_: unknown, record: Machine) => (
          <Dropdown
            menu={{
              items: [
                {
                  key: 'vault',
                  label: t('machines:vault'),
                  icon: <KeyOutlined />,
                  onClick: () => {
                    setVaultMachine(record);
                  },
                },
                {
                  key: 'edit',
                  label: t('common:actions.edit'),
                  icon: <EditOutlined />,
                  onClick: () => {
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
                  },
                },
                {
                  type: 'divider',
                },
                {
                  key: 'systemFunctions',
                  label: t('machines:systemFunctions'),
                  icon: <FunctionOutlined />,
                  onClick: () => {
                    setFunctionModalMachine(record);
                    setSelectedFunction(null);
                    setFunctionParams({});
                    setFunctionPriority(5);
                    setFunctionDescription('');
                    setFunctionSearchTerm('');
                  },
                },
                {
                  type: 'divider',
                },
                {
                  key: 'delete',
                  label: t('common:actions.delete'),
                  icon: <DeleteOutlined />,
                  danger: true,
                  onClick: () => handleDelete(record),
                },
              ],
            }}
            trigger={['click']}
          >
            <Button type="text" icon={<MoreOutlined />} />
          </Dropdown>
        ),
      });
    }

    // Then add the other columns
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
        render: (teamName: string) => <Tag color="blue">{teamName}</Tag>,
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
        render: (bridge: string) => <Tag color="blue">{bridge}</Tag>,
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
                  <Tag color={groupBy === 'bridge' ? 'green' : groupBy === 'team' ? 'blue' : 'purple'} style={{ fontSize: '14px' }}>
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
                                <Tag color="blue" style={{ marginRight: 4 }}>{machine.teamName}</Tag>
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
  const machineFormFields = uiMode === 'simple' 
    ? [
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
    }
  }, [showCreateModal, selectedTeam, teamFilter, machineForm]);

  return (
    <div className={className}>
      {renderFilters()}
      {renderViewToggle()}
      
      {viewMode === 'table' ? (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <Table
            columns={columns}
            dataSource={filteredMachines}
            rowKey="machineName"
            loading={isLoading}
            scroll={{ x: 'max-content', y: 'calc(100vh - 400px)' }}
            pagination={{
              showSizeChanger: true,
              showTotal: (total) => t('common:table.total') + ': ' + total,
            }}
            sticky
          />
        </div>
      ) : (
        renderGridView()
      )}

      {/* Modals */}
      <Modal
        title={t('machines:createMachine')}
        open={showCreateModal}
        onCancel={() => {
          setShowCreateModal(false);
          machineForm.reset();
        }}
        footer={null}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <ResourceForm
            form={machineForm}
            fields={machineFormFields}
            onSubmit={handleCreateMachine}
            submitText={t('common:actions.create')}
            cancelText={t('common:actions.cancel')}
            onCancel={() => {
              setShowCreateModal(false);
              machineForm.reset();
            }}
            loading={createMachineMutation.isPending}
          />
          
          {uiMode === 'simple' && (
            <div style={{ 
              borderTop: '1px solid #f0f0f0', 
              paddingTop: 16,
              marginTop: 8
            }}>
              <Alert
                message={t('machines:defaultsApplied')}
                description={
                  <Space direction="vertical" size={0}>
                    <Text>{t('machines:team')}: Private Team</Text>
                    <Text>{t('machines:region')}: Default Region</Text>
                    <Text>{t('machines:bridge')}: Shared Bridge</Text>
                  </Space>
                }
                type="info"
                showIcon
              />
            </div>
          )}
        </div>
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

      {/* System Functions Modal */}
      {functionModalMachine && (
        <Modal
          title={t('machines:addSystemFunction')}
          open={!!functionModalMachine}
          onCancel={() => {
            setFunctionModalMachine(null);
            setSelectedFunction(null);
            setFunctionParams({});
            setFunctionPriority(5);
            setFunctionDescription('');
            setFunctionSearchTerm('');
          }}
          width={900}
          footer={[
            <Button key="cancel" onClick={() => {
              setFunctionModalMachine(null);
              setSelectedFunction(null);
              setFunctionParams({});
              setFunctionPriority(5);
              setFunctionDescription('');
              setFunctionSearchTerm('');
            }}>
              {t('common:actions.cancel')}
            </Button>,
            <Button
              key="submit"
              type="primary"
              onClick={handleAddFunctionToQueue}
              disabled={!selectedFunction}
              loading={createQueueItemMutation.isPending}
              style={{ background: '#556b2f', borderColor: '#556b2f' }}
            >
              {t('machines:addToQueue')}
            </Button>
          ]}
        >
          <Row gutter={24}>
            <Col span={10}>
              <Card title={t('machines:availableFunctions')} size="small">
                <Search
                  placeholder={t('machines:searchFunctions')}
                  value={functionSearchTerm}
                  onChange={(e) => setFunctionSearchTerm(e.target.value)}
                  style={{ marginBottom: 16 }}
                />
                <div style={{ maxHeight: 400, overflow: 'auto' }}>
                  {filteredSystemFunctions.map(func => (
                    <div
                      key={func.name}
                      onClick={() => setSelectedFunction(func)}
                      style={{
                        padding: '8px 12px',
                        marginBottom: 4,
                        cursor: 'pointer',
                        borderRadius: 4,
                        backgroundColor: selectedFunction?.name === func.name ? '#f0f5ff' : 'transparent',
                        border: selectedFunction?.name === func.name ? '1px solid #1890ff' : '1px solid transparent'
                      }}
                    >
                      <Text strong>{func.name}</Text>
                      <br />
                      <Text type="secondary" style={{ fontSize: 12 }}>{func.description}</Text>
                    </div>
                  ))}
                </div>
              </Card>
            </Col>
            
            <Col span={14}>
              {selectedFunction ? (
                <Space direction="vertical" size={16} style={{ width: '100%' }}>
                  <Card title={`${t('machines:configure')}: ${selectedFunction.name}`} size="small">
                    <Paragraph>{selectedFunction.description}</Paragraph>
                    
                    <Form layout="vertical">
                      {/* Function Parameters */}
                      {Object.entries(selectedFunction.params).map(([paramName, paramInfo]) => (
                        <Form.Item
                          key={paramName}
                          label={paramName}
                          required={paramInfo.required}
                          help={paramInfo.help}
                        >
                          <Input
                            value={functionParams[paramName] || ''}
                            onChange={(e) => setFunctionParams({
                              ...functionParams,
                              [paramName]: e.target.value
                            })}
                            placeholder={paramInfo.help}
                          />
                        </Form.Item>
                      ))}
                      
                      {/* Team Selection - Disabled */}
                      <Form.Item label={t('machines:team')} required>
                        <Input
                          value={functionModalMachine.teamName}
                          disabled
                          style={{ backgroundColor: '#f5f5f5' }}
                        />
                      </Form.Item>
                      
                      {/* Machine Selection - Disabled */}
                      <Form.Item label={t('machines:machine')} required>
                        <Input
                          value={functionModalMachine.machineName}
                          disabled
                          style={{ backgroundColor: '#f5f5f5' }}
                        />
                      </Form.Item>
                      
                      {/* Priority */}
                      <Form.Item label={t('machines:priority')}>
                        <Slider
                          min={1}
                          max={10}
                          value={functionPriority}
                          onChange={setFunctionPriority}
                          marks={{
                            1: t('machines:priorityLow'),
                            5: t('machines:priorityNormal'),
                            10: t('machines:priorityHigh')
                          }}
                        />
                      </Form.Item>
                      
                      {/* Description */}
                      <Form.Item label={t('machines:description')}>
                        <Input.TextArea
                          value={functionDescription}
                          onChange={(e) => setFunctionDescription(e.target.value)}
                          placeholder={t('machines:descriptionPlaceholder')}
                          rows={2}
                        />
                      </Form.Item>
                    </Form>
                  </Card>
                </Space>
              ) : (
                <Card>
                  <Empty description={t('machines:selectFunctionToConfigure')} />
                </Card>
              )}
            </Col>
          </Row>
        </Modal>
      )}
    </div>
  );
};