import React, { useEffect, useRef, useState } from 'react';
import { Button, Flex, Modal, Result, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { useGetOrganizationVault, useUpdateOrganizationVault } from '@/api/api-hooks.generated';
import {
  useExportOrganizationData,
  useImportOrganizationData,
  useOrganizationVaults,
  useUpdateOrganizationBlockUserRequests,
  useUpdateOrganizationVaults,
} from '@/api/hooks-organization';
import VaultEditorModal from '@/components/common/VaultEditorModal';
import { featureFlags } from '@/config/featureFlags';
import { useDialogState } from '@/hooks/useDialogState';
import { masterPasswordService } from '@/services/auth';
import { cryptoService } from '@/services/crypto';
import { logout } from '@/store/auth/authSlice';
import { RootState } from '@/store/store';
import { ModalSize } from '@/types/modal';
import { showMessage } from '@/utils/messages';
import { DangerZoneSection } from '../components/organization/DangerZoneSection';
import { ImportModal } from '../components/organization/ImportModal';
import { MasterPasswordModal } from '../components/organization/MasterPasswordModal';
import { OrganizationVaultSection } from '../components/organization/OrganizationVaultSection';

const OrganizationPage: React.FC = () => {
  const { t } = useTranslation('settings');
  const { t: tSystem } = useTranslation('system');
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);

  const organizationVaultModal = useDialogState<void>();
  const masterPasswordModal = useDialogState<void>();
  const [masterPasswordOperation, setMasterPasswordOperation] = useState<
    'create' | 'update' | 'remove'
  >('create');
  const [completedOperation, setCompletedOperation] = useState<'create' | 'update' | 'remove'>(
    'update'
  );
  const successModal = useDialogState<void>();
  const [countdown, setCountdown] = useState(60);
  const countdownInterval = useRef<NodeJS.Timeout | null>(null);
  const importModal = useDialogState<void>();
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importMode, setImportMode] = useState<'skip' | 'override'>('skip');
  const [currentMasterPassword, setCurrentMasterPassword] = useState<string | null>(null);

  const { data: organizationVault } = useGetOrganizationVault();
  const updateOrganizationVaultMutation = useUpdateOrganizationVault();
  const blockUserRequestsMutation = useUpdateOrganizationBlockUserRequests();
  const exportVaultsQuery = useOrganizationVaults();
  const updateVaultsMutation = useUpdateOrganizationVaults();
  const exportOrganizationDataQuery = useExportOrganizationData();
  const importOrganizationDataMutation = useImportOrganizationData();

  useEffect(() => {
    const loadMasterPassword = async () => {
      const password = await masterPasswordService.getMasterPassword();
      setCurrentMasterPassword(password);
      setMasterPasswordOperation(password ? 'update' : 'create');
    };
    void loadMasterPassword();
  }, []);

  const handleOpenMasterPasswordModal = () => {
    setMasterPasswordOperation(currentMasterPassword ? 'update' : 'create');
    masterPasswordModal.open();
  };

  useEffect(() => {
    if (successModal.isOpen && countdown > 0) {
      countdownInterval.current = setInterval(() => {
        setCountdown((prev) => prev - 1);
      }, 1000);
    } else if (countdown === 0) {
      dispatch(logout());
      void navigate('/login');
    }

    return () => {
      if (countdownInterval.current) {
        clearInterval(countdownInterval.current);
      }
    };
  }, [successModal.isOpen, countdown, dispatch, navigate]);

  const handleUpdateOrganizationVault = async (vault: string, version: number) => {
    await updateOrganizationVaultMutation.mutateAsync({
      vaultContent: vault,
      vaultVersion: version,
    });
    organizationVaultModal.close();
  };

  const handleExportVaults = async () => {
    try {
      const result = await exportVaultsQuery.refetch();
      if (result.data) {
        const timestamp = new Date().toISOString().replaceAll(/[:.]/g, '-').split('T')[0];
        const { allVaults } = result.data;

        const exportData = {
          exportDate: new Date().toISOString(),
          vaults: allVaults,
          metadata: {
            totalVaults: allVaults.length,
          },
        };

        const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `organization-vaults-export-${timestamp}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showMessage('success', tSystem('dangerZone.exportVaults.success'));
      }
    } catch {
      showMessage('error', tSystem('dangerZone.exportVaults.error'));
    }
  };

  const handleExportOrganizationData = async () => {
    try {
      const result = await exportOrganizationDataQuery.refetch();
      if (result.data) {
        const timestamp = new Date().toISOString().replaceAll(/[:.]/g, '-').split('T')[0];
        const blob = new Blob([JSON.stringify(result.data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `organization-data-export-${timestamp}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showMessage('success', tSystem('dangerZone.exportData.success'));
      }
    } catch {
      showMessage('error', tSystem('dangerZone.exportData.error'));
    }
  };

  const handleImportOrganizationData = async () => {
    if (!importFile) {
      showMessage('error', tSystem('dangerZone.importData.modal.fileRequired'));
      return;
    }

    try {
      const fileContent = await importFile.text();
      try {
        JSON.parse(fileContent);
      } catch {
        showMessage('error', tSystem('dangerZone.importData.modal.invalidFile'));
        return;
      }

      await importOrganizationDataMutation.mutateAsync({
        organizationDataJson: fileContent,
        importMode,
      });

      importModal.close();
      setImportFile(null);
    } catch {
      // handled by mutation
    }
  };

  const decryptVaultContent = async (content: string): Promise<string> => {
    if (typeof content !== 'string') return content;
    if (!currentMasterPassword) return content;
    if (masterPasswordOperation === 'create') return content;
    if (!/^[A-Za-z0-9+/]+=*$/.exec(content)) return content;

    try {
      return await cryptoService.decryptString(content, currentMasterPassword);
    } catch {
      return content;
    }
  };

  const processVaultForPasswordChange = async (
    vault: { decryptedVault?: string; credential?: string; vaultName?: string; version?: number },
    newPassword: string
  ): Promise<{ credential: string; name: string; content: string; version: number } | null> => {
    if (!vault.decryptedVault || !vault.credential || !vault.vaultName) {
      return null;
    }

    try {
      let vaultContent = await decryptVaultContent(vault.decryptedVault);

      if (typeof vaultContent === 'string' && masterPasswordOperation !== 'remove') {
        vaultContent = await cryptoService.encryptString(vaultContent, newPassword);
      }

      return {
        credential: vault.credential,
        name: vault.vaultName,
        content: vaultContent,
        version: vault.version ?? 1,
      };
    } catch {
      showMessage('error', `Failed to process vault ${vault.vaultName}`);
      return null;
    }
  };

  const handleUpdateMasterPassword = async (values: {
    password?: string;
    confirmPassword?: string;
  }) => {
    if (updateVaultsMutation.isPending) return;

    try {
      const vaultsResult = await exportVaultsQuery.refetch();
      if (!vaultsResult.data?.allVaults) {
        showMessage('error', tSystem('dangerZone.updateMasterPassword.error.noVaults'));
        return;
      }

      const newPassword = masterPasswordOperation === 'remove' ? '' : values.password!;
      const processedVaults = await Promise.all(
        vaultsResult.data.allVaults.map((vault) =>
          processVaultForPasswordChange(vault, newPassword)
        )
      );
      const vaultUpdates = processedVaults.filter((v): v is NonNullable<typeof v> => v !== null);

      if (!vaultUpdates.length) {
        showMessage('error', tSystem('dangerZone.updateMasterPassword.error.noVaults'));
        return;
      }

      await updateVaultsMutation.mutateAsync(vaultUpdates);
      await blockUserRequestsMutation.mutateAsync(false);

      const finalPassword = masterPasswordOperation === 'remove' ? null : newPassword;
      await masterPasswordService.setMasterPassword(finalPassword);
      setCurrentMasterPassword(finalPassword);

      masterPasswordModal.close();
      setCompletedOperation(masterPasswordOperation);
      setMasterPasswordOperation(currentMasterPassword ? 'update' : 'create');
      setCountdown(60);
      successModal.open();
    } catch {
      // handled by mutation
    }
  };

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
        <OrganizationVaultSection
          t={t}
          showConfigureVault={featureFlags.isEnabled('organizationVaultConfiguration')}
          onConfigureVault={() => organizationVaultModal.open()}
        />

        {featureFlags.isEnabled('dangerZone') && (
          <DangerZoneSection
            t={t}
            onBlockUserRequests={(block) => blockUserRequestsMutation.mutate(block)}
            isBlockingUserRequests={blockUserRequestsMutation.isPending}
            onExportVaults={handleExportVaults}
            isExportingVaults={exportVaultsQuery.isFetching}
            onExportOrganizationData={handleExportOrganizationData}
            isExportingOrganizationData={exportOrganizationDataQuery.isFetching}
            onOpenImportModal={() => importModal.open()}
            onOpenMasterPasswordModal={handleOpenMasterPasswordModal}
          />
        )}
      </Flex>

      <VaultEditorModal
        open={organizationVaultModal.isOpen}
        onCancel={organizationVaultModal.close}
        onSave={handleUpdateOrganizationVault}
        entityType="ORGANIZATION"
        title={t('organization.modalTitle')}
        initialVault={organizationVault?.[0]?.vaultContent ?? '{}'}
        initialVersion={organizationVault?.[0]?.vaultVersion ?? 1}
        loading={updateOrganizationVaultMutation.isPending}
      />

      <MasterPasswordModal
        t={t}
        open={masterPasswordModal.isOpen}
        currentMasterPassword={currentMasterPassword}
        masterPasswordOperation={masterPasswordOperation}
        onOperationChange={setMasterPasswordOperation}
        onCancel={() => {
          masterPasswordModal.close();
          setMasterPasswordOperation(currentMasterPassword ? 'update' : 'create');
        }}
        onSubmit={handleUpdateMasterPassword}
        isSubmitting={updateVaultsMutation.isPending}
      />

      <Modal
        open={successModal.isOpen}
        closable={false}
        footer={null}
        className={ModalSize.Medium}
        centered
        data-testid="system-master-password-success-modal"
      >
        <Result
          status="success"
          title={tSystem(
            `dangerZone.updateMasterPassword.success.title${
              completedOperation.charAt(0).toUpperCase() + completedOperation.slice(1)
            }`
          )}
          subTitle={
            <Flex vertical className="w-full">
              <Flex vertical>
                <Typography.Paragraph>
                  {tSystem('dangerZone.updateMasterPassword.success.nextSteps')}
                </Typography.Paragraph>
                <ol className="ordered-list">
                  <li>{tSystem('dangerZone.updateMasterPassword.success.step1')}</li>
                  <li>
                    {tSystem(
                      `dangerZone.updateMasterPassword.success.step2${
                        completedOperation === 'remove' ? 'Remove' : ''
                      }`
                    )}
                  </li>
                  <li>
                    {tSystem(
                      `dangerZone.updateMasterPassword.success.step3${
                        completedOperation === 'remove' ? 'Remove' : ''
                      }`
                    )}
                  </li>
                  <li>
                    {tSystem(
                      `dangerZone.updateMasterPassword.success.step4${
                        completedOperation === 'remove' ? 'Remove' : ''
                      }`
                    )}
                  </li>
                </ol>
              </Flex>

              <Flex vertical className="text-center" align="center">
                <Typography.Title level={4}>
                  {tSystem('dangerZone.updateMasterPassword.success.redirecting')}
                </Typography.Title>
                <Typography.Title level={1} type="danger">
                  {countdown}
                </Typography.Title>
                <Typography.Text>
                  {tSystem('dangerZone.updateMasterPassword.success.seconds')}
                </Typography.Text>
              </Flex>

              <Button
                block
                onClick={() => {
                  dispatch(logout());
                  void navigate('/login');
                }}
              >
                {tSystem('dangerZone.updateMasterPassword.success.loginNow')}
              </Button>
            </Flex>
          }
        />
      </Modal>

      <ImportModal
        t={t}
        open={importModal.isOpen}
        onCancel={() => {
          importModal.close();
          setImportFile(null);
          setImportMode('skip');
        }}
        onSubmit={handleImportOrganizationData}
        importFile={importFile}
        setImportFile={setImportFile}
        importMode={importMode}
        setImportMode={setImportMode}
        isSubmitting={importOrganizationDataMutation.isPending}
      />
    </Flex>
  );
};

export default OrganizationPage;
