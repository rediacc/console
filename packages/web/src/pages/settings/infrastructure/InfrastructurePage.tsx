import React, { useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Dropdown,
  Empty,
  Flex,
  Form,
  Input,
  Modal,
  Popconfirm,
  Result,
  Row,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  type MenuProps,
} from 'antd';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import {
  Bridge,
  useBridges,
  useCreateBridge,
  useDeleteBridge,
  useResetBridgeAuthorization,
  useUpdateBridgeName,
  useUpdateBridgeVault,
} from '@/api/queries/bridges';
import {
  Region,
  useCreateRegion,
  useDeleteRegion,
  useRegions,
  useUpdateRegionName,
  useUpdateRegionVault,
} from '@/api/queries/regions';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { createVersionColumn } from '@/components/common/columns';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { MobileCard } from '@/components/common/MobileCard';
import ResourceListView from '@/components/common/ResourceListView';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import { featureFlags } from '@/config/featureFlags';
import { useCopyToClipboard } from '@/hooks';
import { useDialogState, useTraceModal } from '@/hooks/useDialogState';
import { createSorter } from '@/platform';
import { RootState } from '@/store/store';
import { ModalSize } from '@/types/modal';
import {
  ApiOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  DeleteOutlined,
  DesktopOutlined,
  EditOutlined,
  EnvironmentOutlined,
  HistoryOutlined,
  KeyOutlined,
  MoreOutlined,
  PlusOutlined,
  SyncOutlined,
} from '@/utils/optimizedIcons';
import type { ColumnsType } from 'antd/es/table';

const ACTIONS_COLUMN_WIDTH = 640;

const InfrastructurePage: React.FC = () => {
  const { t } = useTranslation('resources');
  const { t: tSystem } = useTranslation('system');
  const { t: tCommon } = useTranslation('common');
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const { copy: copyToken, copied: tokenCopied } = useCopyToClipboard({
    successMessage: 'common:copiedToClipboard',
  });

  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const bridgeCredentialsModal = useDialogState<Bridge>();
  const resetAuthModal = useDialogState<{
    bridgeName: string;
    regionName: string;
    isCloudManaged: boolean;
  }>();
  const auditTrace = useTraceModal();
  const unifiedModal = useDialogState<{
    resourceType: 'region' | 'bridge';
    mode: 'create' | 'edit';
    data?: Partial<Region> | Partial<Bridge> | null;
  }>();

  const { data: regions, isLoading: regionsLoading } = useRegions(true);
  const regionsList: Region[] = useMemo(() => regions || [], [regions]);

  const effectiveRegion = selectedRegion ?? regionsList[0]?.regionName ?? null;

  const { data: bridges, isLoading: bridgesLoading } = useBridges(effectiveRegion ?? undefined);
  const bridgesList: Bridge[] = useMemo(() => bridges || [], [bridges]);

  const createRegionMutation = useCreateRegion();
  const updateRegionNameMutation = useUpdateRegionName();
  const deleteRegionMutation = useDeleteRegion();
  const updateRegionVaultMutation = useUpdateRegionVault();

  const createBridgeMutation = useCreateBridge();
  const updateBridgeNameMutation = useUpdateBridgeName();
  const deleteBridgeMutation = useDeleteBridge();
  const updateBridgeVaultMutation = useUpdateBridgeVault();
  const resetBridgeAuthMutation = useResetBridgeAuthorization();

  const openUnifiedModal = (
    resourceType: 'region' | 'bridge',
    mode: 'create' | 'edit',
    data?: Partial<Region> | Partial<Bridge> | null
  ) => {
    unifiedModal.open({ resourceType, mode, data });
  };

  const closeUnifiedModal = () => {
    unifiedModal.close();
  };

  type UnifiedFormData = {
    regionName?: string;
    bridgeName?: string;
    vaultContent?: string;
    vaultVersion?: number;
    [key: string]: unknown;
  };

  const handleUnifiedModalSubmit = async (data: UnifiedFormData) => {
    const modalData = unifiedModal.state.data;
    if (!modalData) return;

    try {
      switch (modalData.resourceType) {
        case 'region':
          if (modalData.mode === 'create') {
            await createRegionMutation.mutateAsync({
              regionName: data.regionName as string,
              vaultContent: data.vaultContent,
            });
          } else if (modalData.data) {
            if (data.regionName && data.regionName !== modalData.data.regionName) {
              await updateRegionNameMutation.mutateAsync({
                currentRegionName: modalData.data.regionName as string,
                newRegionName: data.regionName,
              });
            }
            const vaultData = data.vaultContent;
            if (vaultData && vaultData !== modalData.data.vaultContent) {
              await updateRegionVaultMutation.mutateAsync({
                regionName: (data.regionName || modalData.data.regionName) as string,
                vaultContent: vaultData,
                vaultVersion: (modalData.data.vaultVersion ?? 0) + 1,
              });
            }
          }
          break;
        case 'bridge':
          if (modalData.mode === 'create') {
            await createBridgeMutation.mutateAsync({
              regionName: data.regionName as string,
              bridgeName: data.bridgeName as string,
              vaultContent: data.vaultContent,
            });
          } else if (modalData.data) {
            const bridgeData = modalData.data as Partial<Bridge>;
            if (data.bridgeName && data.bridgeName !== bridgeData.bridgeName) {
              await updateBridgeNameMutation.mutateAsync({
                regionName: bridgeData.regionName as string,
                currentBridgeName: bridgeData.bridgeName as string,
                newBridgeName: data.bridgeName,
              });
            }
            const vaultData = data.vaultContent;
            if (vaultData && vaultData !== bridgeData.vaultContent) {
              await updateBridgeVaultMutation.mutateAsync({
                regionName: (data.regionName || bridgeData.regionName) as string,
                bridgeName: (data.bridgeName || bridgeData.bridgeName) as string,
                vaultContent: vaultData,
                vaultVersion: (bridgeData.vaultVersion ?? 0) + 1,
              });
            }
          }
          break;
      }
      closeUnifiedModal();
    } catch {
      // handled by mutation
    }
  };

  const handleUnifiedVaultUpdate = async (vault: string, version: number) => {
    const modalData = unifiedModal.state.data;
    if (!modalData?.data) return;

    try {
      if (modalData.resourceType === 'region') {
        await updateRegionVaultMutation.mutateAsync({
          regionName: modalData.data.regionName as string,
          vaultContent: vault,
          vaultVersion: version,
        });
      } else {
        const bridgeData = modalData.data as Partial<Bridge>;
        await updateBridgeVaultMutation.mutateAsync({
          regionName: bridgeData.regionName as string,
          bridgeName: bridgeData.bridgeName as string,
          vaultContent: vault,
          vaultVersion: version,
        });
      }
    } catch {
      // handled by mutation
    }
  };

  const handleDeleteRegion = async (regionName: string) => {
    try {
      await deleteRegionMutation.mutateAsync({ regionName });
      if (selectedRegion === regionName) {
        setSelectedRegion(null);
      }
    } catch {
      // handled by mutation
    }
  };

  const handleDeleteBridge = async (bridge: Bridge) => {
    try {
      await deleteBridgeMutation.mutateAsync({
        regionName: bridge.regionName,
        bridgeName: bridge.bridgeName,
      });
    } catch {
      // handled by mutation
    }
  };

  const handleResetBridgeAuth = async () => {
    const data = resetAuthModal.state.data;
    if (!data) return;

    try {
      await resetBridgeAuthMutation.mutateAsync({
        bridgeName: data.bridgeName,
        isCloudManaged: data.isCloudManaged,
      });
      resetAuthModal.close();
    } catch {
      // handled by mutation
    }
  };

  const regionColumns: ColumnsType<Region> = [
    {
      title: t('regions.regionName'),
      dataIndex: 'regionName',
      key: 'regionName',
      sorter: createSorter<Region>('regionName'),
      render: (text: string) => (
        <Space>
          <EnvironmentOutlined />
          <strong>{text}</strong>
        </Space>
      ),
    },
    ...(!featureFlags.isEnabled('disableBridge')
      ? [
          {
            title: t('regions.bridges'),
            dataIndex: 'bridgeCount',
            key: 'bridgeCount',
            width: 120,
            sorter: createSorter<Region>('bridgeCount'),
            render: (count: number) => (
              <Space>
                <ApiOutlined />
                <Typography.Text>{count}</Typography.Text>
              </Space>
            ),
          } as ColumnsType<Region>[number],
        ]
      : []),
    ...(featureFlags.isEnabled('vaultVersionColumns')
      ? [
          createVersionColumn<Region>({
            title: t('general.vaultVersion'),
            dataIndex: 'vaultVersion',
            key: 'vaultVersion',
            width: 120,
            sorter: createSorter<Region>('vaultVersion'),
            formatVersion: (version: number) => tCommon('general.versionFormat', { version }),
          }),
        ]
      : []),
    {
      title: t('general.actions'),
      key: 'actions',
      width: 300,
      render: (_: unknown, record: Region) => (
        <Space>
          <Tooltip title={t('general.edit')}>
            <Button
              type="primary"
              size="small"
              icon={<EditOutlined />}
              onClick={() => openUnifiedModal('region', 'edit', record)}
              data-testid={`system-region-edit-button-${record.regionName}`}
              aria-label={t('general.edit')}
            />
          </Tooltip>
          <Tooltip title={tSystem('actions.trace')}>
            <Button
              type="primary"
              size="small"
              icon={<HistoryOutlined />}
              onClick={() =>
                auditTrace.open({
                  entityType: 'Region',
                  entityIdentifier: record.regionName,
                  entityName: record.regionName,
                })
              }
              data-testid={`system-region-trace-button-${record.regionName}`}
              aria-label={tSystem('actions.trace')}
            />
          </Tooltip>
          <Popconfirm
            title={t('regions.deleteRegion')}
            description={t('regions.confirmDelete', { regionName: record.regionName })}
            onConfirm={() => handleDeleteRegion(record.regionName)}
            okText={t('general.yes')}
            cancelText={t('general.no')}
            okButtonProps={{ danger: true }}
          >
            <Tooltip title={t('general.delete')}>
              <Button
                type="primary"
                danger
                size="small"
                icon={<DeleteOutlined />}
                loading={deleteRegionMutation.isPending}
                data-testid={`system-region-delete-button-${record.regionName}`}
                aria-label={t('general.delete')}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const bridgeColumns: ColumnsType<Bridge> = [
    {
      title: t('bridges.bridgeName'),
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      sorter: createSorter<Bridge>('bridgeName'),
      render: (text: string, record: Bridge) => (
        <Space>
          <ApiOutlined />
          <strong>{text}</strong>
          {Number(record.hasAccess || 0) === 1 && (
            <Tag icon={<CheckCircleOutlined />}>{t('bridges.access')}</Tag>
          )}
        </Space>
      ),
    },
    {
      title: t('teams.machines'),
      dataIndex: 'machineCount',
      key: 'machineCount',
      width: 120,
      sorter: createSorter<Bridge>('machineCount'),
      render: (count: number) => (
        <Space>
          <DesktopOutlined />
          <Typography.Text>{count}</Typography.Text>
        </Space>
      ),
    },
    {
      title: t('bridges.type'),
      dataIndex: 'isGlobalBridge',
      key: 'isGlobalBridge',
      width: 120,
      sorter: createSorter<Bridge>('isGlobalBridge'),
      render: (isGlobal: boolean) =>
        isGlobal ? (
          <Tag icon={<CloudServerOutlined />}>{t('bridges.global')}</Tag>
        ) : (
          <Tag icon={<ApiOutlined />}>{t('bridges.regular')}</Tag>
        ),
    },
    {
      title: t('bridges.management'),
      dataIndex: 'managementMode',
      key: 'managementMode',
      width: 140,
      sorter: createSorter<Bridge>('managementMode'),
      render: (mode: string) => {
        if (!mode) return <Tag>{t('bridges.local')}</Tag>;
        const icon = mode === 'Cloud' ? <CloudServerOutlined /> : <DesktopOutlined />;
        return <Tag icon={icon}>{mode}</Tag>;
      },
    },
    ...(featureFlags.isEnabled('vaultVersionColumns')
      ? [
          createVersionColumn<Bridge>({
            title: t('general.vaultVersion'),
            dataIndex: 'vaultVersion',
            key: 'vaultVersion',
            width: 120,
            sorter: createSorter<Bridge>('vaultVersion'),
            formatVersion: (version: number) => tCommon('general.versionFormat', { version }),
          }),
        ]
      : []),
    {
      title: t('general.actions'),
      key: 'actions',
      width: ACTIONS_COLUMN_WIDTH,
      render: (_: unknown, record: Bridge) => (
        <Space>
          <Tooltip title={t('general.edit')}>
            <Button
              type="primary"
              size="small"
              icon={<EditOutlined />}
              onClick={() => openUnifiedModal('bridge', 'edit', record)}
              data-testid={`system-bridge-edit-button-${record.bridgeName}`}
              aria-label={t('general.edit')}
            />
          </Tooltip>
          <Tooltip title={tSystem('actions.token')}>
            <Button
              type="primary"
              size="small"
              icon={<KeyOutlined />}
              onClick={() => bridgeCredentialsModal.open(record)}
              data-testid={`system-bridge-token-button-${record.bridgeName}`}
              aria-label={tSystem('actions.token')}
            />
          </Tooltip>
          <Tooltip title={tSystem('actions.resetAuth')}>
            <Button
              type="primary"
              size="small"
              icon={<SyncOutlined />}
              onClick={() =>
                resetAuthModal.open({
                  bridgeName: record.bridgeName,
                  regionName: record.regionName,
                  isCloudManaged: false,
                })
              }
              data-testid={`system-bridge-reset-auth-button-${record.bridgeName}`}
              aria-label={tSystem('actions.resetAuth')}
            />
          </Tooltip>
          <Tooltip title={tSystem('actions.trace')}>
            <Button
              type="primary"
              size="small"
              icon={<HistoryOutlined />}
              onClick={() =>
                auditTrace.open({
                  entityType: 'Bridge',
                  entityIdentifier: record.bridgeName,
                  entityName: record.bridgeName,
                })
              }
              data-testid={`system-bridge-trace-button-${record.bridgeName}`}
              aria-label={tSystem('actions.trace')}
            />
          </Tooltip>
          <Popconfirm
            title={t('bridges.deleteBridge')}
            description={t('bridges.confirmDelete', { bridgeName: record.bridgeName })}
            onConfirm={() => handleDeleteBridge(record)}
            okText={t('general.yes')}
            cancelText={t('general.no')}
            okButtonProps={{ danger: true }}
          >
            <Tooltip title={t('general.delete')}>
              <Button
                type="primary"
                danger
                size="small"
                icon={<DeleteOutlined />}
                loading={deleteBridgeMutation.isPending}
                data-testid={`system-bridge-delete-button-${record.bridgeName}`}
                aria-label={t('general.delete')}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const mobileRender = useMemo(
    () => (record: Region) => {
      const menuItems: MenuProps['items'] = [
        { key: 'edit', label: t('general.edit'), icon: <EditOutlined />, onClick: () => openUnifiedModal('region', 'edit', record) },
        { key: 'trace', label: tSystem('actions.trace'), icon: <HistoryOutlined />, onClick: () => auditTrace.open({
          entityType: 'Region',
          entityIdentifier: record.regionName,
          entityName: record.regionName,
        })},
        { key: 'delete', label: t('general.delete'), icon: <DeleteOutlined />, danger: true, onClick: () => handleDeleteRegion(record.regionName) },
      ];

      return (
        <MobileCard actions={
          <Dropdown menu={{ items: menuItems }} trigger={['click']} placement="bottomRight">
            <Button type="text" size="small" icon={<MoreOutlined />} onClick={(e) => e.stopPropagation()} aria-label="Actions" />
          </Dropdown>
        }>
          <Space>
            <EnvironmentOutlined />
            <Typography.Text strong className="truncate">{record.regionName}</Typography.Text>
          </Space>
          <Space size="small">
            <ApiOutlined />
            <Typography.Text>{record.bridgeCount} bridges</Typography.Text>
          </Space>
        </MobileCard>
      );
    },
    [t, tSystem, auditTrace, handleDeleteRegion, openUnifiedModal]
  );

  if (uiMode === 'simple') {
    return (
      <Flex vertical>
        <Result
          status="403"
          title={tSystem('accessControl.expertOnlyTitle')}
          subTitle={tSystem('accessControl.expertOnlyMessage')}
        />
      </Flex>
    );
  }

  if (!featureFlags.isEnabled('regionsInfrastructure')) {
    return (
      <Flex vertical>
        <Result
          status="info"
          title={t('regionsInfrastructure.unavailableTitle')}
          subTitle={t('regionsInfrastructure.unavailableDescription')}
        />
      </Flex>
    );
  }

  return (
    <Flex vertical>
      <Flex vertical>
        <Row gutter={[24, 24]}>
          <Col span={24}>
            <Flex vertical>
              <ResourceListView
                title={
                  <Space direction="vertical" size={0}>
                    <Typography.Text strong>{t('regions.title')}</Typography.Text>
                    <Typography.Text>{t('regions.selectRegionPrompt')}</Typography.Text>
                  </Space>
                }
                loading={regionsLoading}
                data={regionsList}
                columns={regionColumns}
                mobileRender={mobileRender}
                rowKey="regionName"
                searchPlaceholder={t('regions.searchRegions')}
                data-testid="system-region-table"
                actions={
                  <Tooltip title={t('regions.createRegion')}>
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => openUnifiedModal('region', 'create')}
                      data-testid="system-create-region-button"
                      aria-label={t('regions.createRegion')}
                    />
                  </Tooltip>
                }
                rowSelection={{
                  type: 'radio',
                  selectedRowKeys: effectiveRegion ? [effectiveRegion] : [],
                  onChange: (selectedRowKeys) => {
                    const [first] = selectedRowKeys;
                    setSelectedRegion(typeof first === 'string' ? first : null);
                  },
                }}
                onRow={(record: Region) => ({
                  onClick: () => setSelectedRegion(record.regionName),
                  className: [
                    'clickable-row',
                    effectiveRegion === record.regionName ? 'selected-row' : '',
                  ]
                    .filter(Boolean)
                    .join(' '),
                })}
              />
            </Flex>
          </Col>

          {!featureFlags.isEnabled('disableBridge') && (
            <Col span={24}>
              <Card>
                <Flex wrap align="center" justify="space-between" gap={8}>
                  <Flex vertical>
                    <Typography.Title level={4}>
                      {effectiveRegion
                        ? t('regions.bridgesInRegion', { region: effectiveRegion })
                        : t('bridges.title')}
                    </Typography.Title>
                    {!effectiveRegion && (
                      <Typography.Text>{t('regions.selectRegionToView')}</Typography.Text>
                    )}
                  </Flex>
                  {effectiveRegion && (
                    <Tooltip title={t('bridges.createBridge')}>
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() =>
                          openUnifiedModal('bridge', 'create', { regionName: effectiveRegion })
                        }
                        data-testid="system-create-bridge-button"
                        aria-label={t('bridges.createBridge')}
                      />
                    </Tooltip>
                  )}
                </Flex>

                {!effectiveRegion ? (
                  <Flex>
                    <Empty description={t('regions.selectRegionPrompt')} />
                  </Flex>
                ) : (
                  <LoadingWrapper
                    loading={bridgesLoading}
                    centered
                    minHeight={200}
                    tip={tCommon('general.loading')}
                  >
                    <Table
                      columns={bridgeColumns}
                      dataSource={bridgesList}
                      rowKey="bridgeName"
                      pagination={{
                        total: bridgesList.length || 0,
                        pageSize: 10,
                        showSizeChanger: true,
                        showTotal: (total) => t('bridges.totalBridges', { total }),
                      }}
                      locale={{ emptyText: t('bridges.noBridges') }}
                      data-testid="system-bridge-table"
                    />
                  </LoadingWrapper>
                )}
              </Card>
            </Col>
          )}
        </Row>
      </Flex>

      {!featureFlags.isEnabled('disableBridge') && (
        <Modal
          title={`${t('bridges.bridgeToken')} - ${bridgeCredentialsModal.state.data?.bridgeName || ''}`}
          open={bridgeCredentialsModal.isOpen}
          onCancel={() => bridgeCredentialsModal.close()}
          footer={[
            <Button key="close" onClick={() => bridgeCredentialsModal.close()}>
              {tCommon('actions.close')}
            </Button>,
          ]}
          className={ModalSize.Medium}
        >
          {(() => {
            const bridge = bridgeCredentialsModal.state.data;
            if (!bridge) return null;

            const token = bridge.bridgeCredentials;

            if (bridge.hasAccess === 0) {
              return (
                /* eslint-disable-next-line no-restricted-syntax */
                <Flex style={{ maxWidth: 600, width: '100%' }}>
                  <Alert
                    message={t('bridges.accessDenied')}
                    description={t('bridges.accessDeniedDescription')}
                    type="error"
                    showIcon
                  />
                </Flex>
              );
            }

            if (!token) {
              return (
                /* eslint-disable-next-line no-restricted-syntax */
                <Flex style={{ maxWidth: 600, width: '100%' }}>
                  <Alert
                    message={t('bridges.noToken')}
                    description={t('bridges.noTokenDescription')}
                    type="info"
                    showIcon
                  />
                </Flex>
              );
            }

            return (
              <Flex vertical gap={16} className="w-full">
                <Alert
                  message={t('bridges.tokenHeading')}
                  description={t('bridges.tokenDescription')}
                  type="warning"
                  showIcon
                />

                <Flex vertical>
                  <Typography.Text strong>{t('bridges.tokenLabel')}</Typography.Text>
                  <Space.Compact className="w-full">
                    <Input className="w-full" value={token} readOnly autoComplete="off" />
                    <Button
                      icon={tokenCopied ? <CheckCircleOutlined /> : <KeyOutlined />}
                      onClick={() => copyToken(token)}
                    >
                      {tokenCopied ? tCommon('actions.copied') : tCommon('actions.copy')}
                    </Button>
                  </Space.Compact>
                </Flex>

                <Alert
                  message={tCommon('general.important')}
                  description={t('bridges.tokenImportant')}
                  type="info"
                  showIcon
                />
              </Flex>
            );
          })()}
        </Modal>
      )}

      <AuditTraceModal
        open={auditTrace.isOpen}
        onCancel={auditTrace.close}
        entityType={auditTrace.entityType}
        entityIdentifier={auditTrace.entityIdentifier}
        entityName={auditTrace.entityName}
      />

      <UnifiedResourceModal
        open={unifiedModal.isOpen}
        onCancel={closeUnifiedModal}
        resourceType={unifiedModal.state.data?.resourceType || 'region'}
        mode={unifiedModal.state.data?.mode || 'create'}
        existingData={
          unifiedModal.state.data?.data
            ? {
                ...unifiedModal.state.data.data,
                vaultVersion: unifiedModal.state.data.data.vaultVersion ?? undefined,
              }
            : undefined
        }
        onSubmit={handleUnifiedModalSubmit}
        onUpdateVault={
          unifiedModal.state.data?.mode === 'edit' ? handleUnifiedVaultUpdate : undefined
        }
        isSubmitting={
          createRegionMutation.isPending ||
          updateRegionNameMutation.isPending ||
          createBridgeMutation.isPending ||
          updateBridgeNameMutation.isPending
        }
        isUpdatingVault={updateRegionVaultMutation.isPending || updateBridgeVaultMutation.isPending}
      />

      {!featureFlags.isEnabled('disableBridge') && (
        <Modal
          title={t('bridges.resetAuth')}
          open={resetAuthModal.isOpen}
          onCancel={() => resetAuthModal.close()}
          footer={[
            <Button key="cancel" onClick={() => resetAuthModal.close()}>
              {tCommon('actions.cancel')}
            </Button>,
            <Button
              key="reset"
              type="primary"
              danger
              loading={resetBridgeAuthMutation.isPending}
              onClick={handleResetBridgeAuth}
            >
              {t('bridges.resetAuthConfirm')}
            </Button>,
          ]}
        >
          {resetAuthModal.state.data && (
            <Flex vertical gap={16} className="w-full">
              <Alert
                message={tCommon('general.warning')}
                description={t('bridges.resetAuthWarning', {
                  bridge: resetAuthModal.state.data.bridgeName,
                })}
                type="warning"
                showIcon
              />

              <Form layout="vertical">
                <Form.Item
                  label={t('bridges.cloudManagement')}
                  help={t('bridges.cloudManagementHelp')}
                >
                  <Checkbox
                    checked={resetAuthModal.state.data.isCloudManaged}
                    onChange={(e) =>
                      resetAuthModal.setData({
                        bridgeName: resetAuthModal.state.data!.bridgeName,
                        regionName: resetAuthModal.state.data!.regionName,
                        isCloudManaged: e.target.checked,
                      })
                    }
                  >
                    {t('bridges.enableCloudManagement')}
                  </Checkbox>
                </Form.Item>
              </Form>
            </Flex>
          )}
        </Modal>
      )}
    </Flex>
  );
};

export default InfrastructurePage;
