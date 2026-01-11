import React, { useCallback, useMemo, useState } from 'react';
import { Flex, Result, Space, Typography, type MenuProps } from 'antd';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import {
  useGetRegionBridges,
  useCreateBridge,
  useDeleteBridge,
  useResetBridgeAuthorization,
  useUpdateBridgeName,
  useUpdateBridgeVault,
  useCreateRegion,
  useDeleteRegion,
  useGetOrganizationRegions,
  useUpdateRegionName,
  useUpdateRegionVault,
} from '@/api/api-hooks.generated';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import {
  buildBridgeColumns,
  buildRegionColumns,
} from '@/components/common/columns/builders/infrastructureColumns';
import {
  buildDeleteMenuItem,
  buildDivider,
  buildEditMenuItem,
  buildResetAuthMenuItem,
  buildTokenMenuItem,
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
import type {
  GetRegionBridges_ResultSet1,
  GetOrganizationRegions_ResultSet1,
} from '@rediacc/shared/types';
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
  const bridgeCredentialsModal = useDialogState<GetRegionBridges_ResultSet1>();
  const resetAuthModal = useDialogState<{
    bridgeName: string;
    regionName: string;
    isCloudManaged: boolean;
  }>();
  const auditTrace = useTraceModal();
  const unifiedModal = useDialogState<{
    resourceType: 'region' | 'bridge';
    mode: 'create' | 'edit';
    data?: Partial<GetOrganizationRegions_ResultSet1> | Partial<GetRegionBridges_ResultSet1> | null;
  }>();

  const { data: regions, isLoading: regionsLoading } = useGetOrganizationRegions();
  const regionsList: GetOrganizationRegions_ResultSet1[] = useMemo(() => regions ?? [], [regions]);

  const effectiveRegion = useMemo(() => {
    if (selectedRegion) return selectedRegion;
    if (regionsList.length > 0) return regionsList[0].regionName ?? '';
    return '';
  }, [selectedRegion, regionsList]);

  const { data: bridges, isLoading: bridgesLoading } = useGetRegionBridges(effectiveRegion);
  const bridgesList: GetRegionBridges_ResultSet1[] = useMemo(() => bridges ?? [], [bridges]);

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
      data?:
        | Partial<GetOrganizationRegions_ResultSet1>
        | Partial<GetRegionBridges_ResultSet1>
        | null
    ) => {
      unifiedModal.open({ resourceType, mode, data });
    },
    [unifiedModal]
  );

  const closeUnifiedModal = useCallback(() => {
    unifiedModal.close();
  }, [unifiedModal]);

  type UnifiedFormData = {
    regionName?: string;
    bridgeName?: string;
    vaultContent?: string;
    vaultVersion?: number;
    [key: string]: unknown;
  };

  const handleRegionSubmit = useCallback(
    async (
      data: UnifiedFormData,
      mode: 'create' | 'edit',
      existingData?: Partial<GetOrganizationRegions_ResultSet1> | null
    ) => {
      if (mode === 'create') {
        await createRegionMutation.mutateAsync({
          regionName: data.regionName as string,
          vaultContent: data.vaultContent ?? '',
        });
        return;
      }

      if (!existingData) return;

      if (data.regionName && data.regionName !== existingData.regionName) {
        await updateRegionNameMutation.mutateAsync({
          currentRegionName: existingData.regionName as string,
          newRegionName: data.regionName,
        });
      }

      const vaultData = data.vaultContent;
      if (vaultData && vaultData !== existingData.vaultContent) {
        await updateRegionVaultMutation.mutateAsync({
          regionName: (data.regionName ?? existingData.regionName) as string,
          vaultContent: vaultData,
          vaultVersion: (existingData.vaultVersion ?? 0) + 1,
        });
      }
    },
    [createRegionMutation, updateRegionNameMutation, updateRegionVaultMutation]
  );

  const handleBridgeSubmit = useCallback(
    async (
      data: UnifiedFormData,
      mode: 'create' | 'edit',
      existingData?: Partial<GetRegionBridges_ResultSet1> | null
    ) => {
      if (mode === 'create') {
        await createBridgeMutation.mutateAsync({
          regionName: data.regionName as string,
          bridgeName: data.bridgeName as string,
          vaultContent: data.vaultContent ?? '',
        });
        return;
      }

      if (!existingData) return;

      if (data.bridgeName && data.bridgeName !== existingData.bridgeName) {
        await updateBridgeNameMutation.mutateAsync({
          regionName: existingData.regionName as string,
          currentBridgeName: existingData.bridgeName as string,
          newBridgeName: data.bridgeName,
        });
      }

      const vaultData = data.vaultContent;
      if (vaultData && vaultData !== existingData.vaultContent) {
        await updateBridgeVaultMutation.mutateAsync({
          regionName: (data.regionName ?? existingData.regionName) as string,
          bridgeName: (data.bridgeName ?? existingData.bridgeName) as string,
          vaultContent: vaultData,
          vaultVersion: (existingData.vaultVersion ?? 0) + 1,
        });
      }
    },
    [createBridgeMutation, updateBridgeNameMutation, updateBridgeVaultMutation]
  );

  const handleUnifiedModalSubmit = useCallback(
    async (data: UnifiedFormData) => {
      const modalData = unifiedModal.state.data;
      if (!modalData) return;

      try {
        if (modalData.resourceType === 'region') {
          await handleRegionSubmit(
            data,
            modalData.mode,
            modalData.data as Partial<GetOrganizationRegions_ResultSet1> | null
          );
        } else {
          await handleBridgeSubmit(
            data,
            modalData.mode,
            modalData.data as Partial<GetRegionBridges_ResultSet1> | null
          );
        }
        closeUnifiedModal();
      } catch {
        // handled by mutation
      }
    },
    [unifiedModal.state.data, closeUnifiedModal, handleRegionSubmit, handleBridgeSubmit]
  );

  const handleUnifiedVaultUpdate = useCallback(
    async (vault: string, version: number) => {
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
          const bridgeData = modalData.data as Partial<GetRegionBridges_ResultSet1>;
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
    },
    [unifiedModal.state.data, updateRegionVaultMutation, updateBridgeVaultMutation]
  );

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
    async (bridge: GetRegionBridges_ResultSet1) => {
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
        onEdit: (record) => openUnifiedModal('region', 'edit', record),
        onTrace: (record) =>
          auditTrace.open({
            entityType: 'Region',
            entityIdentifier: record.regionName ?? '',
            entityName: record.regionName ?? undefined,
          }),
        onDelete: handleDeleteRegion,
        isDeleting: deleteRegionMutation.isPending,
      }),
    [t, auditTrace, handleDeleteRegion, openUnifiedModal, deleteRegionMutation.isPending]
  );

  const bridgeColumns = useMemo(
    () =>
      buildBridgeColumns({
        t,
        onEdit: (record) => openUnifiedModal('bridge', 'edit', record),
        onOpenToken: bridgeCredentialsModal.open,
        onResetAuth: (record) =>
          resetAuthModal.open({
            bridgeName: record.bridgeName ?? '',
            regionName: record.regionName ?? '',
            isCloudManaged: false,
          }),
        onTrace: (record) =>
          auditTrace.open({
            entityType: 'Bridge',
            entityIdentifier: record.bridgeName ?? '',
            entityName: record.bridgeName ?? undefined,
          }),
        onDelete: handleDeleteBridge,
        isDeleting: deleteBridgeMutation.isPending,
      }),
    [
      t,
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
    () => (record: GetOrganizationRegions_ResultSet1) => {
      const menuItems: MenuProps['items'] = [
        buildEditMenuItem(tCommon, () => openUnifiedModal('region', 'edit', record)),
        buildTraceMenuItem(tCommon, () =>
          auditTrace.open({
            entityType: 'Region',
            entityIdentifier: record.regionName ?? '',
            entityName: record.regionName ?? undefined,
          })
        ),
        buildDivider(),
        buildDeleteMenuItem(tCommon, () => handleDeleteRegion(record.regionName ?? '')),
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
            <Typography.Text>
              {t('resources:bridges.bridgeCount', { count: record.bridgeCount ?? 0 })}
            </Typography.Text>
          </Space>
        </MobileCard>
      );
    },

    [t, tCommon, auditTrace, handleDeleteRegion, openUnifiedModal]
  );

  const bridgeMobileRender = useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: GetRegionBridges_ResultSet1) => {
      const menuItems: MenuProps['items'] = [
        buildEditMenuItem(tCommon, () => openUnifiedModal('bridge', 'edit', record)),
        buildTokenMenuItem(tCommon, () => bridgeCredentialsModal.open(record)),
        buildResetAuthMenuItem(tCommon, () =>
          resetAuthModal.open({
            bridgeName: record.bridgeName ?? '',
            regionName: record.regionName ?? '',
            isCloudManaged: false,
          })
        ),
        buildTraceMenuItem(tCommon, () =>
          auditTrace.open({
            entityType: 'Bridge',
            entityIdentifier: record.bridgeName ?? '',
            entityName: record.bridgeName ?? undefined,
          })
        ),
        buildDivider(),
        buildDeleteMenuItem(tCommon, () => handleDeleteBridge(record)),
      ];

      return (
        <MobileCard actions={<ResourceActionsDropdown menuItems={menuItems} />}>
          <Space>
            <ApiOutlined />
            <Typography.Text strong className="truncate">
              {record.bridgeName}
            </Typography.Text>
          </Space>
          <Space size="small">
            <Typography.Text>
              {t('resources:bridges.machineCount', { count: record.machineCount ?? 0 })}
            </Typography.Text>
          </Space>
        </MobileCard>
      );
    },
    [
      t,
      tCommon,
      auditTrace,
      bridgeCredentialsModal,
      resetAuthModal,
      handleDeleteBridge,
      openUnifiedModal,
    ]
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

  return (
    <Flex vertical>
      <Flex vertical>
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

        {featureFlags.isEnabled('bridgeManageEnabled') && (
          <BridgeSection
            t={t}
            bridgesLoading={bridgesLoading}
            bridgesList={bridgesList}
            columns={bridgeColumns}
            mobileRender={bridgeMobileRender}
            effectiveRegion={effectiveRegion}
            onCreateBridge={(regionName) => openUnifiedModal('bridge', 'create', { regionName })}
          />
        )}
      </Flex>

      {featureFlags.isEnabled('bridgeManageEnabled') && (
        <BridgeCredentialsModal
          t={t}
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
        resourceType={unifiedModal.state.data?.resourceType ?? 'region'}
        mode={unifiedModal.state.data?.mode ?? 'create'}
        existingData={
          unifiedModal.state.data?.data as
            | (Partial<GetOrganizationRegions_ResultSet1> & { vaultVersion?: number })
            | (Partial<GetRegionBridges_ResultSet1> & { vaultVersion?: number })
            | undefined
        }
        onSubmit={handleUnifiedModalSubmit}
        onUpdateVault={
          unifiedModal.state.data?.mode === 'edit' ? handleUnifiedVaultUpdate : undefined
        }
        isSubmitting={[
          createRegionMutation.isPending,
          updateRegionNameMutation.isPending,
          createBridgeMutation.isPending,
          updateBridgeNameMutation.isPending,
        ].some(Boolean)}
        isUpdatingVault={[
          updateRegionVaultMutation.isPending,
          updateBridgeVaultMutation.isPending,
        ].some(Boolean)}
      />

      {featureFlags.isEnabled('bridgeManageEnabled') && (
        <ResetAuthModal
          t={t}
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
