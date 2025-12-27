import React, { useEffect, useRef, useState } from 'react';
import { Button, Flex, Form, Modal, Result, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import {
  useCompanyVault,
  useCompanyVaults,
  useExportCompanyData,
  useImportCompanyData,
  useUpdateCompanyBlockUserRequests,
  useUpdateCompanyVault,
  useUpdateCompanyVaults,
} from '@/api/queries/company';
import VaultEditorModal from '@/components/common/VaultEditorModal';
import { featureFlags } from '@/config/featureFlags';
import { useDialogState } from '@/hooks/useDialogState';
import { masterPasswordService } from '@/services/auth';
import { cryptoService } from '@/services/crypto';
import { logout } from '@/store/auth/authSlice';
import { RootState } from '@/store/store';
import { ModalSize } from '@/types/modal';
import { showMessage } from '@/utils/messages';
import { CompanyVaultSection } from '../components/company/CompanyVaultSection';
import { DangerZoneSection } from '../components/company/DangerZoneSection';
import { ImportModal } from '../components/company/ImportModal';
import { MasterPasswordModal } from '../components/company/MasterPasswordModal';

const CompanyPage: React.FC = () => {
  const { t } = useTranslation('settings');
  const { t: tSystem } = useTranslation('system');
  const { t: tCommon } = useTranslation('common');
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);

  const companyVaultModal = useDialogState<void>();
  const masterPasswordModal = useDialogState<void>();
  const [masterPasswordForm] = Form.useForm();
  const [importForm] = Form.useForm();
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

  const { data: companyVault } = useCompanyVault();
  const updateCompanyVaultMutation = useUpdateCompanyVault();
  const blockUserRequestsMutation = useUpdateCompanyBlockUserRequests();
  const exportVaultsQuery = useCompanyVaults();
  const updateVaultsMutation = useUpdateCompanyVaults();
  const exportCompanyDataQuery = useExportCompanyData();
  const importCompanyDataMutation = useImportCompanyData();

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

  const handleUpdateCompanyVault = async (vault: string, version: number) => {
    await updateCompanyVaultMutation.mutateAsync({
      vaultContent: vault,
      vaultVersion: version,
    });
    companyVaultModal.close();
  };

  const handleExportVaults = async () => {
    try {
      const result = await exportVaultsQuery.refetch();
      if (result.data) {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').split('T')[0];
        const { allVaults, bridgesWithRequestToken, ...vaultsByType } = result.data;

        const exportData = {
          exportDate: new Date().toISOString(),
          vaults: vaultsByType,
          bridgesWithRequestToken,
          metadata: {
            totalVaults: allVaults.length,
            vaultTypes: Object.keys(vaultsByType).map((type) => ({
              type,
              count: (vaultsByType as Record<string, unknown[]>)[type].length,
            })),
          },
        };

        const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `company-vaults-export-${timestamp}.json`;
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

  const handleExportCompanyData = async () => {
    try {
      const result = await exportCompanyDataQuery.refetch();
      if (result.data) {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').split('T')[0];
        const blob = new Blob([JSON.stringify(result.data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `company-data-export-${timestamp}.json`;
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

  const handleImportCompanyData = async () => {
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

      await importCompanyDataMutation.mutateAsync({
        companyDataJson: fileContent,
        importMode,
      });

      importModal.close();
      setImportFile(null);
      importForm.resetFields();
    } catch {
      // handled by mutation
    }
  };

  const handleUpdateMasterPassword = async (values: {
    password?: string;
    confirmPassword?: string;
  }) => {
    if (updateVaultsMutation.isPending) {
      return;
    }

    try {
      const vaultsResult = await exportVaultsQuery.refetch();
      if (!vaultsResult.data?.allVaults) {
        showMessage('error', tSystem('dangerZone.updateMasterPassword.error.noVaults'));
        return;
      }

      const vaultUpdates: {
        credential: string;
        name: string;
        content: string;
        version: number;
      }[] = [];
      const newPassword = masterPasswordOperation === 'remove' ? '' : values.password!;

      for (const vault of vaultsResult.data.allVaults) {
        if (vault.decryptedVault && vault.credential && vault.vaultName) {
          try {
            let vaultContent = vault.decryptedVault;

            if (
              typeof vaultContent === 'string' &&
              currentMasterPassword &&
              masterPasswordOperation !== 'create'
            ) {
              try {
                if (vaultContent.match(/^[A-Za-z0-9+/]+=*$/)) {
                  vaultContent = await cryptoService.decryptString(
                    vaultContent,
                    currentMasterPassword
                  );
                }
              } catch {
                // ignore
              }
            }

            let finalContent = vaultContent;
            if (typeof vaultContent === 'string' && masterPasswordOperation !== 'remove') {
              finalContent = await cryptoService.encryptString(vaultContent, newPassword);
            }

            vaultUpdates.push({
              credential: vault.credential,
              name: vault.vaultName,
              content: finalContent,
              version: vault.version || 1,
            });
          } catch {
            showMessage('error', `Failed to process vault ${vault.vaultName}`);
          }
        }
      }

      if (!vaultUpdates.length) {
        showMessage('error', tSystem('dangerZone.updateMasterPassword.error.noVaults'));
        return;
      }

      await updateVaultsMutation.mutateAsync(vaultUpdates);
      await blockUserRequestsMutation.mutateAsync(false);

      await masterPasswordService.setMasterPassword(
        masterPasswordOperation === 'remove' ? null : newPassword
      );
      setCurrentMasterPassword(masterPasswordOperation === 'remove' ? null : newPassword);

      masterPasswordModal.close();
      masterPasswordForm.resetFields();
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
      <Flex vertical gap={24}>
        <CompanyVaultSection
          t={t}
          showConfigureVault={featureFlags.isEnabled('companyVaultConfiguration')}
          onConfigureVault={() => companyVaultModal.open()}
        />

        {featureFlags.isEnabled('dangerZone') && (
          <DangerZoneSection
            tSystem={tSystem}
            tCommon={tCommon}
            onBlockUserRequests={(block) => blockUserRequestsMutation.mutate(block)}
            isBlockingUserRequests={blockUserRequestsMutation.isPending}
            onExportVaults={handleExportVaults}
            isExportingVaults={exportVaultsQuery.isFetching}
            onExportCompanyData={handleExportCompanyData}
            isExportingCompanyData={exportCompanyDataQuery.isFetching}
            onOpenImportModal={() => importModal.open()}
            onOpenMasterPasswordModal={handleOpenMasterPasswordModal}
          />
        )}
      </Flex>

      <VaultEditorModal
        open={companyVaultModal.isOpen}
        onCancel={companyVaultModal.close}
        onSave={handleUpdateCompanyVault}
        entityType="COMPANY"
        title={t('company.modalTitle')}
        initialVault={companyVault?.vaultContent ?? '{}'}
        initialVersion={companyVault?.vaultVersion ?? 1}
        loading={updateCompanyVaultMutation.isPending}
      />

      <MasterPasswordModal
        tSystem={tSystem}
        tCommon={tCommon}
        open={masterPasswordModal.isOpen}
        currentMasterPassword={currentMasterPassword}
        masterPasswordOperation={masterPasswordOperation}
        onOperationChange={setMasterPasswordOperation}
        onCancel={() => {
          masterPasswordModal.close();
          masterPasswordForm.resetFields();
          setMasterPasswordOperation(currentMasterPassword ? 'update' : 'create');
        }}
        onSubmit={handleUpdateMasterPassword}
        form={masterPasswordForm}
        isSubmitting={updateVaultsMutation.isPending}
      />

      <Modal
        open={successModal.isOpen}
        closable={false}
        footer={null}
        className={ModalSize.Medium}
        centered
      >
        <Result
          status="success"
          title={tSystem(
            `dangerZone.updateMasterPassword.success.title${
              completedOperation.charAt(0).toUpperCase() + completedOperation.slice(1)
            }`
          )}
          subTitle={
            <Flex vertical gap={16} className="w-full">
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
        tSystem={tSystem}
        open={importModal.isOpen}
        onCancel={() => {
          importModal.close();
          setImportFile(null);
          importForm.resetFields();
          setImportMode('skip');
        }}
        onSubmit={handleImportCompanyData}
        importForm={importForm}
        importFile={importFile}
        setImportFile={setImportFile}
        importMode={importMode}
        setImportMode={setImportMode}
        isSubmitting={importCompanyDataMutation.isPending}
      />
    </Flex>
  );
};

export default CompanyPage;
