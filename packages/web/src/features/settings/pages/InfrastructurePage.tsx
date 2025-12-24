import React, { useCallback, useMemo, useState } from 'react';
import { Flex, Result, Space, Typography, type MenuProps } from 'antd';
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
import {
  buildBridgeColumns,
  buildRegionColumns,
} from '@/components/common/columns/builders/infrastructureColumns';
import {
  buildDeleteMenuItem,
  buildDivider,
  buildEditMenuItem,
  buildTraceMenuItem,
} from '@/components/common/menuBuilders';
import { MobileCard } from '@/components/common/MobileCard';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import UnifiedResourceModal from '@/components/common/UnifiedResourceModal';
import { featureFlags } from '@/config/featureFlags';
import { useCopyToClipboard } from '@/hooks';
import { useDialogState, useTraceModal } from '@/hooks/useDialogState';
import { RootState } from '@/store/store';
import { ApiOutlined, EnvironmentOutlined } from '@/utils/optimizedIcons';
import { BridgeCredentialsModal } from '../components/infrastructure/BridgeCredentialsModal';
import { BridgeSection } from '../components/infrastructure/BridgeSection';
import { RegionSection } from '../components/infrastructure/RegionSection';
import { ResetAuthModal } from '../components/infrastructure/ResetAuthModal';

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

  const openUnifiedModal = useCallback(
    (
      resourceType: 'region' | 'bridge',
      mode: 'create' | 'edit',
      data?: Partial<Region> | Partial<Bridge> | null
    ) => {
      unifiedModal.open({ resourceType, mode, data });
    },
    [unifiedModal]
  );

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

  const handleDeleteRegion = useCallback(
    async (regionName: string) => {
      try {
        await deleteRegionMutation.mutateAsync({ regionName });
        if (selectedRegion === regionName) {
          setSelectedRegion(null);
        }
      } catch {
        // handled by mutation
      }
    },
    [deleteRegionMutation, selectedRegion]
  );

  const handleDeleteBridge = useCallback(
    async (bridge: Bridge) => {
      try {
        await deleteBridgeMutation.mutateAsync({
          regionName: bridge.regionName,
          bridgeName: bridge.bridgeName,
        });
      } catch {
        // handled by mutation
      }
    },
    [deleteBridgeMutation]
  );

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

  const regionColumns = useMemo(
    () =>
      buildRegionColumns({
        t,
        tCommon,
        tSystem,
        onEdit: (record) => openUnifiedModal('region', 'edit', record),
        onTrace: (record) =>
          auditTrace.open({
            entityType: 'Region',
            entityIdentifier: record.regionName,
            entityName: record.regionName,
          }),
        onDelete: handleDeleteRegion,
        isDeleting: deleteRegionMutation.isPending,
      }),
    [
      t,
      tCommon,
      tSystem,
      auditTrace,
      handleDeleteRegion,
      openUnifiedModal,
      deleteRegionMutation.isPending,
    ]
  );

  const bridgeColumns = useMemo(
    () =>
      buildBridgeColumns({
        t,
        tCommon,
        tSystem,
        onEdit: (record) => openUnifiedModal('bridge', 'edit', record),
        onOpenToken: bridgeCredentialsModal.open,
        onResetAuth: (record) =>
          resetAuthModal.open({
            bridgeName: record.bridgeName,
            regionName: record.regionName,
            isCloudManaged: false,
          }),
        onTrace: (record) =>
          auditTrace.open({
            entityType: 'Bridge',
            entityIdentifier: record.bridgeName,
            entityName: record.bridgeName,
          }),
        onDelete: handleDeleteBridge,
        isDeleting: deleteBridgeMutation.isPending,
      }),
    [
      t,
      tCommon,
      tSystem,
      auditTrace,
      bridgeCredentialsModal.open,
      handleDeleteBridge,
      openUnifiedModal,
      resetAuthModal,
      deleteBridgeMutation.isPending,
    ]
  );

  const mobileRender = useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: Region) => {
      const menuItems: MenuProps['items'] = [
        buildEditMenuItem(tCommon, () => openUnifiedModal('region', 'edit', record)),
        buildTraceMenuItem(tCommon, () =>
          auditTrace.open({
            entityType: 'Region',
            entityIdentifier: record.regionName,
            entityName: record.regionName,
          })
        ),
        buildDivider(),
        buildDeleteMenuItem(tCommon, () => handleDeleteRegion(record.regionName)),
      ];

      return (
        <MobileCard actions={<ResourceActionsDropdown menuItems={menuItems} />}>
          <Space>
            <EnvironmentOutlined />
            <Typography.Text strong className="truncate">
              {record.regionName}
            </Typography.Text>
          </Space>
          <Space size="small">
            <ApiOutlined />
            <Typography.Text>{record.bridgeCount} bridges</Typography.Text>
          </Space>
        </MobileCard>
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [t, tCommon, auditTrace, handleDeleteRegion, openUnifiedModal]
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
      <Flex vertical gap={24}>
        <RegionSection
          t={t}
          regionsLoading={regionsLoading}
          regionsList={regionsList}
          columns={regionColumns}
          mobileRender={mobileRender}
          effectiveRegion={effectiveRegion}
          onSelectRegion={(regionName) => setSelectedRegion(regionName)}
          onCreateRegion={() => openUnifiedModal('region', 'create')}
        />

        {!featureFlags.isEnabled('disableBridge') && (
          <BridgeSection
            t={t}
            tCommon={tCommon}
            bridgesLoading={bridgesLoading}
            bridgesList={bridgesList}
            columns={bridgeColumns}
            effectiveRegion={effectiveRegion}
            onCreateBridge={(regionName) => openUnifiedModal('bridge', 'create', { regionName })}
          />
        )}
      </Flex>

      {!featureFlags.isEnabled('disableBridge') && (
        <BridgeCredentialsModal
          t={t}
          tCommon={tCommon}
          open={bridgeCredentialsModal.isOpen}
          bridge={bridgeCredentialsModal.state.data ?? undefined}
          tokenCopied={tokenCopied}
          onCopyToken={copyToken}
          onClose={() => bridgeCredentialsModal.close()}
        />
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
        <ResetAuthModal
          t={t}
          tCommon={tCommon}
          open={resetAuthModal.isOpen}
          data={resetAuthModal.state.data ?? undefined}
          isSubmitting={resetBridgeAuthMutation.isPending}
          onClose={() => resetAuthModal.close()}
          onReset={handleResetBridgeAuth}
          onToggleCloudManaged={(value) => {
            if (!resetAuthModal.state.data) return;
            resetAuthModal.setData({
              bridgeName: resetAuthModal.state.data.bridgeName,
              regionName: resetAuthModal.state.data.regionName,
              isCloudManaged: value,
            });
          }}
        />
      )}
    </Flex>
  );
};

export default InfrastructurePage;
