import React, { useState, useMemo } from 'react';
import { Card, Button, Table, Space, Select, Tag, Dropdown, Modal, message, Row, Col, Segmented } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, MoreOutlined, KeyOutlined, FilterOutlined, AppstoreOutlined, TableOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMachines, useDeleteMachine, useCreateMachine, useUpdateMachineName, useUpdateMachineVault } from '../../api/queries/machines';
import { useDropdownData } from '../../api/queries/useDropdownData';
import { useTeams } from '../../api/queries/teams';
import VaultConfigModal from '../../components/common/VaultConfigModal';
import ResourceForm from '../../components/forms/ResourceForm';
import { createMachineSchema, CreateMachineForm } from '../../utils/validation';
import type { Machine } from '../../types';

const { Option } = Select;

export const MachinePage: React.FC = () => {
  const { t } = useTranslation('machines');
  const { t: tCommon } = useTranslation('common');
  const { t: tOrg } = useTranslation('organization');
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [selectedMachine, setSelectedMachine] = useState<Machine | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isVaultModalOpen, setIsVaultModalOpen] = useState(false);
  const [filterBridge, setFilterBridge] = useState<string | undefined>(undefined);
  const [filterTeam, setFilterTeam] = useState<string | undefined>(undefined);
  const [viewMode, setViewMode] = useState<'table' | 'grid'>('table');

  // Fetch all machines (we'll need to update the API to support this)
  const { data: machinesData, isLoading: isLoadingMachines } = useMachines();
  const { data: dropdownData } = useDropdownData();
  const { data: teamsData } = useTeams();
  const deleteMachineMutation = useDeleteMachine();
  const createMachineMutation = useCreateMachine();
  const updateMachineVaultMutation = useUpdateMachineVault();

  // Machine form setup
  const machineForm = useForm<CreateMachineForm>({
    resolver: zodResolver(createMachineSchema) as any,
    defaultValues: {
      teamName: '',
      machineName: '',
      regionName: '',
      bridgeName: '',
      machineVault: '{}',
    },
  });

  const machines = machinesData || [];
  // Extract all bridges from dropdown data
  const bridges = useMemo(() => {
    if (!dropdownData?.bridgesByRegion) return [];
    const allBridges: Array<{ value: string; label: string }> = [];
    dropdownData.bridgesByRegion.forEach(region => {
      if (region.bridges && Array.isArray(region.bridges)) {
        region.bridges.forEach(bridge => {
          allBridges.push(bridge);
        });
      }
    });
    return allBridges;
  }, [dropdownData]);
  const teams = teamsData || [];

  // Get filtered bridges based on selected region (for machine form)
  const selectedRegionForMachine = machineForm.watch('regionName');
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

  // Clear bridge selection when region changes
  React.useEffect(() => {
    const currentBridge = machineForm.getValues('bridgeName');
    if (currentBridge && !filteredBridgesForMachine.find((b: any) => b.value === currentBridge)) {
      machineForm.setValue('bridgeName', '');
    }
  }, [selectedRegionForMachine, filteredBridgesForMachine, machineForm]);

  // Machine form fields (same as OrganizationPage)
  const machineFormFields = [
    {
      name: 'teamName',
      label: tOrg('general.team'),
      placeholder: tOrg('teams.placeholders.selectTeam'),
      required: true,
      type: 'select' as const,
      options: dropdownData?.teams?.map(t => ({ value: t.value, label: t.label })) || [],
    },
    {
      name: 'regionName',
      label: tOrg('general.region'),
      placeholder: tOrg('regions.placeholders.selectRegion'),
      required: true,
      type: 'select' as const,
      options: dropdownData?.regions?.map((r: any) => ({ value: r.value, label: r.label })) || [],
    },
    {
      name: 'bridgeName',
      label: tOrg('bridges.bridge'),
      placeholder: selectedRegionForMachine ? tOrg('bridges.placeholders.selectBridge') : tOrg('bridges.placeholders.selectRegionFirst'),
      required: true,
      type: 'select' as const,
      options: filteredBridgesForMachine,
      disabled: !selectedRegionForMachine,
    },
    {
      name: 'machineName',
      label: tOrg('machines.machineName'),
      placeholder: tOrg('machines.placeholders.enterMachineName'),
      required: true,
    },
  ];

  // Filter machines based on selected bridge and team
  const filteredMachines = useMemo(() => {
    return machines.filter(machine => {
      const bridgeMatch = !filterBridge || machine.bridgeName === filterBridge;
      const teamMatch = !filterTeam || machine.teamName === filterTeam;
      return bridgeMatch && teamMatch;
    });
  }, [machines, filterBridge, filterTeam]);

  // Group machines by bridge for grid view
  const groupedMachinesByBridge = useMemo(() => {
    const grouped = filteredMachines.reduce((acc, machine) => {
      if (!acc[machine.bridgeName]) {
        acc[machine.bridgeName] = [];
      }
      acc[machine.bridgeName].push(machine);
      return acc;
    }, {} as Record<string, Machine[]>);
    return grouped;
  }, [filteredMachines]);

  // Handle create machine
  const handleCreateMachine = async (data: CreateMachineForm) => {
    try {
      // Extract only the fields needed by the API (exclude regionName)
      const { teamName, bridgeName, machineName, machineVault } = data;
      await createMachineMutation.mutateAsync({
        teamName,
        bridgeName,
        machineName,
        machineVault
      });
      setIsCreateModalOpen(false);
      machineForm.reset();
      message.success(t('createSuccess'));
    } catch (error) {
      // Error handled by mutation
    }
  };

  // Handle update vault
  const handleUpdateVault = async (vault: string, version: number) => {
    if (!selectedMachine) return;
    
    try {
      await updateMachineVaultMutation.mutateAsync({
        teamName: selectedMachine.teamName,
        machineName: selectedMachine.machineName,
        machineVault: vault,
        vaultVersion: version,
      });
      message.success(t('vaultUpdateSuccess'));
      setIsVaultModalOpen(false);
      setSelectedMachine(null);
    } catch (error) {
      // Error handled by mutation
    }
  };

  const handleDelete = async (machine: Machine) => {
    Modal.confirm({
      title: t('confirmDelete'),
      content: t('deleteWarning', { name: machine.machineName }),
      okText: tCommon('actions.delete'),
      okType: 'danger',
      cancelText: tCommon('actions.cancel'),
      onOk: async () => {
        try {
          await deleteMachineMutation.mutateAsync({
            machineName: machine.machineName,
            teamName: machine.teamName,
          });
          message.success(t('deleteSuccess'));
        } catch (error) {
          message.error(t('deleteError'));
        }
      },
    });
  };

  const columns = [
    {
      title: t('machineName'),
      dataIndex: 'machineName',
      key: 'machineName',
      sorter: (a: Machine, b: Machine) => a.machineName.localeCompare(b.machineName),
    },
    {
      title: t('team'),
      dataIndex: 'teamName',
      key: 'teamName',
      render: (teamName: string) => <Tag color="blue">{teamName}</Tag>,
      sorter: (a: Machine, b: Machine) => a.teamName.localeCompare(b.teamName),
    },
    {
      title: t('bridge'),
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      render: (bridgeName: string) => <Tag color="green">{bridgeName}</Tag>,
      sorter: (a: Machine, b: Machine) => a.bridgeName.localeCompare(b.bridgeName),
    },
    {
      title: t('queueItems'),
      dataIndex: 'queueCount',
      key: 'queueCount',
      align: 'center' as const,
      sorter: (a: Machine, b: Machine) => a.queueCount - b.queueCount,
    },
    {
      title: t('vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      align: 'center' as const,
    },
    {
      title: tCommon('table.actions'),
      key: 'actions',
      align: 'center' as const,
      render: (_: unknown, record: Machine) => (
        <Dropdown
          menu={{
            items: [
              {
                key: 'vault',
                label: t('vault'),
                icon: <KeyOutlined />,
                onClick: () => {
                  setSelectedMachine(record);
                  setIsVaultModalOpen(true);
                },
              },
              {
                key: 'edit',
                label: tCommon('actions.edit'),
                icon: <EditOutlined />,
                onClick: () => {
                  setSelectedMachine(record);
                  setIsEditModalOpen(true);
                },
              },
              {
                type: 'divider',
              },
              {
                key: 'delete',
                label: tCommon('actions.delete'),
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
    },
  ];

  const renderGridView = () => {
    return (
      <Row gutter={[16, 16]}>
        {Object.entries(groupedMachinesByBridge).map(([bridgeName, machines]) => (
          <Col span={24} key={bridgeName}>
            <Card
              title={
                <Space>
                  <Tag color="green" style={{ fontSize: '14px' }}>{bridgeName}</Tag>
                  <span style={{ fontSize: '14px', color: '#666' }}>
                    {machines.length} {t('machineCount', { count: machines.length })}
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
                      actions={[
                        <KeyOutlined key="vault" onClick={() => {
                          setSelectedMachine(machine);
                          setIsVaultModalOpen(true);
                        }} />,
                        <EditOutlined key="edit" onClick={() => {
                          setSelectedMachine(machine);
                          setIsEditModalOpen(true);
                        }} />,
                        <DeleteOutlined key="delete" onClick={() => handleDelete(machine)} />,
                      ]}
                    >
                      <Card.Meta
                        title={machine.machineName}
                        description={
                          <Space direction="vertical" size="small" style={{ width: '100%' }}>
                            <div>
                              <Tag color="blue" style={{ marginRight: 0 }}>{machine.teamName}</Tag>
                            </div>
                            <div style={{ fontSize: '12px', color: '#666' }}>
                              {t('queueItems')}: {machine.queueCount}
                            </div>
                            <div style={{ fontSize: '12px', color: '#666' }}>
                              {t('vaultVersion')}: {machine.vaultVersion}
                            </div>
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

  return (
    <div>
      <Card>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ margin: 0 }}>{t('title')}</h2>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setIsCreateModalOpen(true)}
            >
              {t('createMachine')}
            </Button>
          </div>

          <Space wrap>
            <Select
              style={{ width: 200 }}
              placeholder={t('filterByBridge')}
              allowClear
              value={filterBridge}
              onChange={setFilterBridge}
              suffixIcon={<FilterOutlined />}
            >
              {bridges.map((bridge) => (
                <Option key={bridge.value} value={bridge.value}>
                  {bridge.label}
                </Option>
              ))}
            </Select>

            <Select
              style={{ width: 200 }}
              placeholder={t('filterByTeam')}
              allowClear
              value={filterTeam}
              onChange={setFilterTeam}
              suffixIcon={<FilterOutlined />}
            >
              {teams.map((team) => (
                <Option key={team.teamName} value={team.teamName}>
                  {team.teamName}
                </Option>
              ))}
            </Select>

            <Segmented
              options={[
                { label: 'Table', value: 'table', icon: <TableOutlined /> },
                { label: 'Grid', value: 'grid', icon: <AppstoreOutlined /> },
              ]}
              value={viewMode}
              onChange={(value) => setViewMode(value as 'table' | 'grid')}
            />
          </Space>

          {viewMode === 'table' ? (
            <Table
              columns={columns}
              dataSource={filteredMachines}
              rowKey="machineName"
              loading={isLoadingMachines}
              pagination={{
                showSizeChanger: true,
                showTotal: (total) => `${tCommon('table.total')}: ${total}`,
              }}
            />
          ) : (
            renderGridView()
          )}
        </Space>
      </Card>

      {/* Create Machine Modal */}
      <Modal
        title={t('createMachine')}
        open={isCreateModalOpen}
        onCancel={() => {
          setIsCreateModalOpen(false);
          machineForm.reset();
        }}
        footer={null}
      >
        <ResourceForm
          form={machineForm}
          fields={machineFormFields}
          onSubmit={handleCreateMachine}
          submitText={tCommon('actions.create')}
          cancelText={tCommon('actions.cancel')}
          onCancel={() => {
            setIsCreateModalOpen(false);
            machineForm.reset();
          }}
          loading={createMachineMutation.isPending}
        />
      </Modal>

      {/* Edit Machine Modal */}
      {selectedMachine && (
        <Modal
          title={t('form.title.edit')}
          open={isEditModalOpen}
          onCancel={() => {
            setIsEditModalOpen(false);
            setSelectedMachine(null);
          }}
          footer={null}
        >
          <p>{t('form.title.edit')}</p>
          {/* Machine edit form will be implemented later */}
        </Modal>
      )}

      {/* Vault Configuration Modal */}
      {selectedMachine && (
        <VaultConfigModal
          open={isVaultModalOpen}
          onCancel={() => {
            setIsVaultModalOpen(false);
            setSelectedMachine(null);
          }}
          onSave={handleUpdateVault}
          title={t('form.title.vault')}
          initialVault="{}"
          initialVersion={selectedMachine.vaultVersion}
          loading={updateMachineVaultMutation.isPending}
        />
      )}
    </div>
  );
};

export default MachinePage;