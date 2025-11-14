import React, { useState, useEffect } from 'react'
import { Button, Tooltip, Space, Tag, Card, Row, Col, Table, Modal, Alert, Spin, Typography, Popconfirm, Result, Empty, Form, Checkbox } from 'antd'
import {
  EnvironmentOutlined,
  ApiOutlined,
  EditOutlined,
  HistoryOutlined,
  PlusOutlined,
  DeleteOutlined,
  KeyOutlined,
  SyncOutlined,
  DesktopOutlined,
  CloudServerOutlined,
  CheckCircleOutlined,
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import ResourceListView from '@/components/common/ResourceListView'
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal'
import AuditTraceModal from '@/components/common/AuditTraceModal'
import { ModalSize } from '@/types/modal'
import { featureFlags } from '@/config/featureFlags'
import {
  useRegions,
  useCreateRegion,
  useUpdateRegionName,
  useDeleteRegion,
  useUpdateRegionVault,
  Region,
} from '@/api/queries/regions'
import {
  useBridges,
  useCreateBridge,
  useUpdateBridgeName,
  useDeleteBridge,
  useUpdateBridgeVault,
  useResetBridgeAuthorization,
  Bridge,
} from '@/api/queries/bridges'
import {
  InfrastructurePageWrapper,
  InfrastructureSectionStack,
  InfrastructureSectionHeading,
} from './styles'
import {
  RegionsListWrapper,
  ListTitleRow,
  ListTitle,
  ListSubtitle,
  CardHeaderRow,
  CardTitle,
  SecondaryText,
  PaddedEmpty,
  CenteredState,
  LoadingHint,
  ModalStack,
  ModalStackLarge,
  ModalAlert,
  TokenCopyRow,
  FullWidthInput,
  ErrorWrapper,
  ACTIONS_COLUMN_WIDTH,
} from '@/pages/system/styles'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'

const InfrastructurePage: React.FC = () => {
  const { t } = useTranslation('resources')
  const { t: tSystem } = useTranslation('system')
  const { t: tCommon } = useTranslation('common')
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)

  const [selectedRegion, setSelectedRegion] = useState<string | null>(null)
  const [bridgeCredentialsModal, setBridgeCredentialsModal] = useState<{
    open: boolean
    bridge?: Bridge
  }>({ open: false })
  const [resetAuthModal, setResetAuthModal] = useState<{
    open: boolean
    bridgeName: string
    isCloudManaged: boolean
  }>({ open: false, bridgeName: '', isCloudManaged: false })
  const [auditTraceModal, setAuditTraceModal] = useState<{
    open: boolean
    entityType: string | null
    entityIdentifier: string | null
    entityName?: string
  }>({ open: false, entityType: null, entityIdentifier: null })
  const [unifiedModalState, setUnifiedModalState] = useState<{
    open: boolean
    resourceType: 'region' | 'bridge'
    mode: 'create' | 'edit'
    data?: any
  }>({ open: false, resourceType: 'region', mode: 'create' })

  const { data: regions, isLoading: regionsLoading } = useRegions(true)
  const regionsList: Region[] = regions || []

  const { data: bridges, isLoading: bridgesLoading } = useBridges(selectedRegion || undefined)
  const bridgesList: Bridge[] = bridges || []

  const createRegionMutation = useCreateRegion()
  const updateRegionNameMutation = useUpdateRegionName()
  const deleteRegionMutation = useDeleteRegion()
  const updateRegionVaultMutation = useUpdateRegionVault()

  const createBridgeMutation = useCreateBridge()
  const updateBridgeNameMutation = useUpdateBridgeName()
  const deleteBridgeMutation = useDeleteBridge()
  const updateBridgeVaultMutation = useUpdateBridgeVault()
  const resetBridgeAuthMutation = useResetBridgeAuthorization()

  useEffect(() => {
    if (regionsList.length > 0 && !selectedRegion) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedRegion(regionsList[0].regionName)
    }
  }, [regionsList, selectedRegion])

  const openUnifiedModal = (resourceType: 'region' | 'bridge', mode: 'create' | 'edit', data?: any) => {
    setUnifiedModalState({ open: true, resourceType, mode, data })
  }

  const closeUnifiedModal = () => {
    setUnifiedModalState({ open: false, resourceType: 'region', mode: 'create', data: null })
  }

  const handleUnifiedModalSubmit = async (data: any) => {
    try {
      switch (unifiedModalState.resourceType) {
        case 'region':
          if (unifiedModalState.mode === 'create') {
            await createRegionMutation.mutateAsync(data)
          } else if (unifiedModalState.data) {
            if (data.regionName !== unifiedModalState.data.regionName) {
              await updateRegionNameMutation.mutateAsync({
                currentRegionName: unifiedModalState.data.regionName,
                newRegionName: data.regionName,
              })
            }
            const vaultData = data.regionVault
            if (vaultData && vaultData !== unifiedModalState.data.vaultContent) {
              await updateRegionVaultMutation.mutateAsync({
                regionName: data.regionName || unifiedModalState.data.regionName,
                regionVault: vaultData,
                vaultVersion: unifiedModalState.data.vaultVersion + 1,
              })
            }
          }
          break
        case 'bridge':
          if (unifiedModalState.mode === 'create') {
            await createBridgeMutation.mutateAsync(data)
          } else if (unifiedModalState.data) {
            if (data.bridgeName !== unifiedModalState.data.bridgeName) {
              await updateBridgeNameMutation.mutateAsync({
                regionName: unifiedModalState.data.regionName,
                currentBridgeName: unifiedModalState.data.bridgeName,
                newBridgeName: data.bridgeName,
              })
            }
            const vaultData = data.bridgeVault
            if (vaultData && vaultData !== unifiedModalState.data.vaultContent) {
              await updateBridgeVaultMutation.mutateAsync({
                regionName: data.regionName || unifiedModalState.data.regionName,
                bridgeName: data.bridgeName || unifiedModalState.data.bridgeName,
                bridgeVault: vaultData,
                vaultVersion: unifiedModalState.data.vaultVersion + 1,
              })
            }
          }
          break
      }
      closeUnifiedModal()
    } catch {
      // handled by mutation
    }
  }

  const handleUnifiedVaultUpdate = async (vault: string, version: number) => {
    if (!unifiedModalState.data) return

    try {
      if (unifiedModalState.resourceType === 'region') {
        await updateRegionVaultMutation.mutateAsync({
          regionName: unifiedModalState.data.regionName,
          regionVault: vault,
          vaultVersion: version,
        })
      } else {
        await updateBridgeVaultMutation.mutateAsync({
          regionName: unifiedModalState.data.regionName,
          bridgeName: unifiedModalState.data.bridgeName,
          bridgeVault: vault,
          vaultVersion: version,
        })
      }
    } catch {
      // handled by mutation
    }
  }

  const handleDeleteRegion = async (regionName: string) => {
    try {
      await deleteRegionMutation.mutateAsync(regionName)
      if (selectedRegion === regionName) {
        setSelectedRegion(null)
      }
    } catch {
      // handled by mutation
    }
  }

  const handleDeleteBridge = async (bridge: Bridge) => {
    try {
      await deleteBridgeMutation.mutateAsync({
        regionName: bridge.regionName,
        bridgeName: bridge.bridgeName,
      })
    } catch {
      // handled by mutation
    }
  }

  const handleResetBridgeAuth = async () => {
    try {
      await resetBridgeAuthMutation.mutateAsync({
        bridgeName: resetAuthModal.bridgeName,
        isCloudManaged: resetAuthModal.isCloudManaged,
      })
      setResetAuthModal({ open: false, bridgeName: '', isCloudManaged: false })
    } catch {
      // handled by mutation
    }
  }

  const regionColumns = [
    {
      title: t('regions.regionName'),
      dataIndex: 'regionName',
      key: 'regionName',
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
            render: (count: number) => (
              <Space>
                <ApiOutlined />
                <span>{count}</span>
              </Space>
            ),
          },
        ]
      : []),
    ...(featureFlags.isEnabled('vaultVersionColumns')
      ? [
          {
            title: t('general.vaultVersion'),
            dataIndex: 'vaultVersion',
            key: 'vaultVersion',
            width: 120,
            render: (version: number) => <Tag>{tCommon('general.versionFormat', { version })}</Tag>,
          },
        ]
      : []),
    {
      title: t('general.actions'),
      key: 'actions',
      width: 300,
      render: (_: any, record: Region) => (
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
                setAuditTraceModal({
                  open: true,
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
  ]

  const bridgeColumns = [
    {
      title: t('bridges.bridgeName'),
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      render: (text: string, record: Bridge) => (
        <Space>
          <ApiOutlined />
          <strong>{text}</strong>
          {(record.hasAccess as number) === 1 && (
            <Tag color="green" icon={<CheckCircleOutlined />}>
              {t('bridges.access')}
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: t('teams.machines'),
      dataIndex: 'machineCount',
      key: 'machineCount',
      width: 120,
      render: (count: number) => (
        <Space>
          <DesktopOutlined />
          <span>{count}</span>
        </Space>
      ),
    },
    {
      title: t('bridges.type'),
      dataIndex: 'isGlobalBridge',
      key: 'isGlobalBridge',
      width: 120,
      render: (isGlobal: boolean) =>
        isGlobal ? (
          <Tag color="purple" icon={<CloudServerOutlined />}>
            {t('bridges.global')}
          </Tag>
        ) : (
          <Tag color="blue" icon={<ApiOutlined />}>
            {t('bridges.regular')}
          </Tag>
        ),
    },
    {
      title: t('bridges.management'),
      dataIndex: 'managementMode',
      key: 'managementMode',
      width: 140,
      render: (mode: string) => {
        if (!mode) return <Tag>{t('bridges.local')}</Tag>
        const color = mode === 'Cloud' ? 'green' : 'default'
        const icon = mode === 'Cloud' ? <CloudServerOutlined /> : <DesktopOutlined />
        return <Tag color={color} icon={icon}>{mode}</Tag>
      },
    },
    ...(featureFlags.isEnabled('vaultVersionColumns')
      ? [
          {
            title: t('general.vaultVersion'),
            dataIndex: 'vaultVersion',
            key: 'vaultVersion',
            width: 120,
            render: (version: number) => <Tag>{tCommon('general.versionFormat', { version })}</Tag>,
          },
        ]
      : []),
    {
      title: t('general.actions'),
      key: 'actions',
      width: ACTIONS_COLUMN_WIDTH,
      render: (_: any, record: Bridge) => (
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
              onClick={() => setBridgeCredentialsModal({ open: true, bridge: record })}
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
                setResetAuthModal({
                  open: true,
                  bridgeName: record.bridgeName,
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
                setAuditTraceModal({
                  open: true,
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
  ]

  if (uiMode === 'simple') {
    return (
      <InfrastructurePageWrapper>
        <Result
          status="403"
          title={tSystem('accessControl.expertOnlyTitle', { defaultValue: 'Expert Mode Required' })}
          subTitle={tSystem('accessControl.expertOnlyMessage', { defaultValue: 'Switch to expert mode to manage infrastructure.' })}
        />
      </InfrastructurePageWrapper>
    )
  }

  if (!featureFlags.isEnabled('regionsInfrastructure')) {
    return (
      <InfrastructurePageWrapper>
        <Result
          status="info"
          title={t('regionsInfrastructure.unavailableTitle', { defaultValue: 'Regions & Infrastructure Disabled' })}
          subTitle={t('regionsInfrastructure.unavailableDescription', { defaultValue: 'Enable the regionsInfrastructure feature flag to access this page.' })}
        />
      </InfrastructurePageWrapper>
    )
  }

  return (
    <InfrastructurePageWrapper>
      <InfrastructureSectionStack>
        <InfrastructureSectionHeading level={3}>{tSystem('regionsInfrastructure.title')}</InfrastructureSectionHeading>

        <Row gutter={[24, 24]}>
          <Col span={24}>
            <RegionsListWrapper>
              <ResourceListView
                title={
                  <ListTitleRow>
                    <ListTitle>{t('regions.title')}</ListTitle>
                    <ListSubtitle>{t('regions.selectRegionPrompt')}</ListSubtitle>
                  </ListTitleRow>
                }
                loading={regionsLoading}
                data={regionsList}
                columns={regionColumns}
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
                  selectedRowKeys: selectedRegion ? [selectedRegion] : [],
                  onChange: (selectedRowKeys) => setSelectedRegion((selectedRowKeys[0] as string) || null),
                }}
                onRow={(record) => ({
                  onClick: () => setSelectedRegion(record.regionName),
                  className: [
                    'clickable-row',
                    selectedRegion === record.regionName ? 'selected-row' : '',
                  ]
                    .filter(Boolean)
                    .join(' '),
                })}
              />
            </RegionsListWrapper>
          </Col>

          {!featureFlags.isEnabled('disableBridge') && (
            <Col span={24}>
              <Card>
                <CardHeaderRow>
                  <div>
                    <CardTitle level={4}>
                      {selectedRegion
                        ? t('regions.bridgesInRegion', { region: selectedRegion })
                        : t('bridges.title')}
                    </CardTitle>
                    {!selectedRegion && (
                      <SecondaryText>{t('regions.selectRegionToView')}</SecondaryText>
                    )}
                  </div>
                  {selectedRegion && (
                    <Tooltip title={t('bridges.createBridge')}>
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => openUnifiedModal('bridge', 'create', { regionName: selectedRegion })}
                        data-testid="system-create-bridge-button"
                        aria-label={t('bridges.createBridge')}
                      />
                    </Tooltip>
                  )}
                </CardHeaderRow>

                {!selectedRegion ? (
                  <PaddedEmpty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('regions.selectRegionPrompt')} />
                ) : bridgesLoading ? (
                  <CenteredState>
                    <Spin size="large" />
                    <LoadingHint>{tCommon('general.loading')}</LoadingHint>
                  </CenteredState>
                ) : (
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
                )}
              </Card>
            </Col>
          )}
        </Row>
      </InfrastructureSectionStack>

      {!featureFlags.isEnabled('disableBridge') && (
        <Modal
          title={`${t('bridges.bridgeToken')} - ${bridgeCredentialsModal.bridge?.bridgeName || ''}`}
          open={bridgeCredentialsModal.open}
          onCancel={() => setBridgeCredentialsModal({ open: false })}
          footer={[
            <Button key="close" onClick={() => setBridgeCredentialsModal({ open: false })}>
              {tCommon('actions.close')}
            </Button>,
          ]}
          className={ModalSize.Medium}
        >
          {(() => {
            const bridge = bridgeCredentialsModal.bridge
            if (!bridge) return null

            const token = bridge.bridgeCredentials

            if (bridge.hasAccess === 0) {
              return (
                <ErrorWrapper>
                  <Alert
                    message={t('bridges.accessDenied')}
                    description={t('bridges.accessDeniedDescription')}
                    type="error"
                    showIcon
                  />
                </ErrorWrapper>
              )
            }

            if (!token) {
              return (
                <ErrorWrapper>
                  <Alert
                    message={t('bridges.noToken')}
                    description={t('bridges.noTokenDescription')}
                    type="info"
                    showIcon
                  />
                </ErrorWrapper>
              )
            }

            return (
              <ModalStackLarge>
                <ModalAlert
                  message={t('bridges.tokenHeading')}
                  description={t('bridges.tokenDescription')}
                  type="warning"
                  showIcon
                />

                <div>
                  <Typography.Text strong>{t('bridges.tokenLabel')}</Typography.Text>
                  <TokenCopyRow>
                    <FullWidthInput value={token} readOnly autoComplete="off" />
                    <Button
                      icon={<KeyOutlined />}
                      onClick={() => {
                        navigator.clipboard.writeText(token)
                      }}
                    >
                      {tCommon('actions.copy')}
                    </Button>
                  </TokenCopyRow>
                </div>

                <ModalAlert
                  message={tCommon('general.important')}
                  description={t('bridges.tokenImportant')}
                  type="info"
                  showIcon
                />
              </ModalStackLarge>
            )
          })()}
        </Modal>
      )}

      <AuditTraceModal
        open={auditTraceModal.open}
        onCancel={() => setAuditTraceModal({ open: false, entityType: null, entityIdentifier: null })}
        entityType={auditTraceModal.entityType}
        entityIdentifier={auditTraceModal.entityIdentifier}
        entityName={auditTraceModal.entityName}
      />

      <UnifiedResourceModal
        open={unifiedModalState.open}
        onCancel={closeUnifiedModal}
        resourceType={unifiedModalState.resourceType}
        mode={unifiedModalState.mode}
        existingData={unifiedModalState.data}
        onSubmit={handleUnifiedModalSubmit}
        onUpdateVault={unifiedModalState.mode === 'edit' ? handleUnifiedVaultUpdate : undefined}
        isSubmitting={
          createRegionMutation.isPending ||
          updateRegionNameMutation.isPending ||
          createBridgeMutation.isPending ||
          updateBridgeNameMutation.isPending
        }
        isUpdatingVault={
          updateRegionVaultMutation.isPending ||
          updateBridgeVaultMutation.isPending
        }
      />

      {!featureFlags.isEnabled('disableBridge') && (
        <Modal
          title={t('bridges.resetAuth')}
          open={resetAuthModal.open}
          onCancel={() => setResetAuthModal({ open: false, bridgeName: '', isCloudManaged: false })}
          footer={[
            <Button
              key="cancel"
              onClick={() => setResetAuthModal({ open: false, bridgeName: '', isCloudManaged: false })}
            >
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
          <ModalStack>
            <ModalAlert
              message={tCommon('general.warning')}
              description={t('bridges.resetAuthWarning', { bridge: resetAuthModal.bridgeName })}
              type="warning"
              showIcon
            />

            <Form layout="vertical">
              <Form.Item
                label={t('bridges.cloudManagement')}
                help={t('bridges.cloudManagementHelp')}
              >
                <Checkbox
                  checked={resetAuthModal.isCloudManaged}
                  onChange={(e) =>
                    setResetAuthModal((prev) => ({
                      ...prev,
                      isCloudManaged: e.target.checked,
                    }))
                  }
                >
                  {t('bridges.enableCloudManagement')}
                </Checkbox>
              </Form.Item>
            </Form>
          </ModalStack>
        </Modal>
      )}
    </InfrastructurePageWrapper>
  )
}

export default InfrastructurePage
