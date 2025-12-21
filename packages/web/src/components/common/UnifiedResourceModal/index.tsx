import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button, Checkbox, Collapse, Flex, Modal, Space, Tag, Typography, Upload } from 'antd';
import { type Resolver, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import type { QueueFunction } from '@/api/queries/queue';
import { useDropdownData } from '@/api/queries/useDropdownData';
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal';
import TemplateSelector from '@/components/common/TemplateSelector';
import ResourceFormWithVault, {
  type ImportExportHandlers,
  type ResourceFormWithVaultRef,
} from '@/components/common/UnifiedResourceModal/components/ResourceFormWithVault';
import VaultEditorModal from '@/components/common/VaultEditorModal';
import { useMessage } from '@/hooks';
import { useDialogState } from '@/hooks/useDialogState';
import { RootState } from '@/store/store';
import { ModalSize } from '@/types/modal';
import { AppstoreOutlined, DownloadOutlined, UploadOutlined } from '@/utils/optimizedIcons';
import {
  renderModalTitle,
  resolveTeamName,
  resolveBridgeName,
  createFunctionSubtitle,
  getFunctionTitle,
} from './components/ModalHeaderRenderer';
import { ResourceModalDialogs } from './components/ResourceModalDialogs';
import { useBridgeSelection } from './hooks/useBridgeSelection';
import { useResourceDefaults } from './hooks/useResourceDefaults';
import { useResourceSchema } from './hooks/useResourceSchema';
import { useTemplateSelection } from './hooks/useTemplateSelection';
import { getFormFields } from './utils/formFieldGenerators';
import { parseVaultData } from './utils/parseVaultData';
import { transformFormData } from './utils/transformFormData';
import type { ExistingResourceData, ResourceFormValues, ResourceType } from './types';

type FunctionParamsMap = Record<string, string | number | string[] | undefined>;

type FunctionSubmitPayload = {
  function: QueueFunction;
  params: FunctionParamsMap;
  priority: number;
  description: string;
  selectedMachine?: string;
};

export interface UnifiedResourceModalProps {
  open: boolean;
  onCancel: () => void;
  resourceType: ResourceType;
  mode: 'create' | 'edit' | 'vault';
  existingData?: ExistingResourceData;
  teamFilter?: string | string[];
  onSubmit: (data: ResourceFormValues) => Promise<void>;
  onUpdateVault?: (vault: string, version: number) => Promise<void>;
  onFunctionSubmit?: (functionData: FunctionSubmitPayload) => Promise<void>;
  isSubmitting?: boolean;
  isUpdatingVault?: boolean;
  functionCategories?: string[];
  hiddenParams?: string[];
  defaultParams?: FunctionParamsMap;
  preselectedFunction?: string;
  creationContext?: 'credentials-only' | 'normal';
}

const UnifiedResourceModal: React.FC<UnifiedResourceModalProps> = ({
  open,
  onCancel,
  resourceType,
  mode,
  existingData,
  teamFilter,
  onSubmit,
  onUpdateVault,
  onFunctionSubmit,
  isSubmitting = false,
  isUpdatingVault = false,
  functionCategories = [],
  hiddenParams = [],
  defaultParams = {},
  preselectedFunction,
  creationContext,
}) => {
  const { t } = useTranslation(['resources', 'machines', 'common', 'ceph', 'system']);
  const message = useMessage();
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const isExpertMode = uiMode === 'expert';
  const { data: dropdownData } = useDropdownData();
  const formRef = useRef<ResourceFormWithVaultRef | null>(null);

  // State for sub-modals
  const vaultModal = useDialogState<void>();
  const functionModal = useDialogState<void>();
  const { isOpen: isFunctionModalOpen, open: openFunctionModal } = functionModal;

  // State for test connection (for machines)
  const [testConnectionSuccess, setTestConnectionSuccess] = useState(false);

  // Track test connection state changes
  useEffect(() => {
    // Test connection state updated
  }, [testConnectionSuccess, resourceType, mode]);

  // State for auto-setup after machine creation
  const [autoSetupEnabled, setAutoSetupEnabled] = useState(true);

  // Hook: Template selection
  const {
    selectedTemplate,
    setSelectedTemplate,
    showTemplateDetails,
    setShowTemplateDetails,
    templateToView,
    setTemplateToView,
  } = useTemplateSelection({ existingData });

  // Import/Export handlers ref
  const importExportHandlers = useRef<ImportExportHandlers | null>(null);

  // Hook: Resource schema and defaults
  const { getSchema, getDefaultValues } = useResourceSchema({
    resourceType,
    mode,
    uiMode,
    creationContext,
    existingData,
  });

  // Log when modal opens
  useEffect(() => {
    if (open) {
      // Modal opened with resource configuration
    }
  }, [open, resourceType, mode, uiMode, existingData, teamFilter]);

  const schema = useMemo(() => getSchema(), [getSchema]);

  const form = useForm<ResourceFormValues>({
    resolver: zodResolver(schema) as unknown as Resolver<
      ResourceFormValues,
      Record<string, unknown>,
      ResourceFormValues
    >,
    defaultValues: getDefaultValues(),
  });

  const getFormValue = useCallback(
    (field: string): string | undefined => {
      const rawValue = form.getValues(field as keyof ResourceFormValues);
      return typeof rawValue === 'string' ? rawValue : undefined;
    },
    [form]
  );

  // Hook: Bridge selection logic
  const { getFilteredBridges } = useBridgeSelection({
    resourceType,
    dropdownData,
    form,
    getFormValue,
  });

  // Set default values when modal opens using custom hook
  useResourceDefaults({
    open,
    mode,
    resourceType,
    form,
    dropdownData,
    existingData,
    teamFilter,
    setSelectedTemplate,
  });

  // Reset form values when modal opens in edit mode
  useEffect(() => {
    if (open && mode === 'edit' && existingData) {
      form.reset({
        [`${resourceType}Name`]: existingData[`${resourceType}Name`],
        ...(resourceType === 'machine' && {
          regionName: existingData.regionName,
          // NOTE: bridgeName is preserved even when disableBridge is enabled and field is hidden
          bridgeName: existingData.bridgeName,
        }),
        ...(resourceType === 'bridge' && {
          regionName: existingData.regionName,
        }),
        ...(resourceType === 'pool' && {
          clusterName: existingData.clusterName,
        }),
        ...(resourceType === 'image' && {
          poolName: existingData.poolName,
        }),
        ...(resourceType === 'snapshot' && {
          poolName: existingData.poolName,
          imageName: existingData.imageName,
        }),
        ...(resourceType === 'clone' && {
          poolName: existingData.poolName,
          imageName: existingData.imageName,
          snapshotName: existingData.snapshotName,
        }),
        vaultContent: existingData.vaultContent || '{}',
      });
    }
  }, [open, mode, existingData, resourceType, form]);

  // Determine if team is already selected/known
  const isTeamPreselected =
    uiMode === 'simple' ||
    (!!teamFilter && !Array.isArray(teamFilter)) ||
    (!!teamFilter && Array.isArray(teamFilter) && teamFilter.length === 1);

  // Get form fields based on resource type and mode
  const formFields = useMemo(
    () =>
      getFormFields({
        resourceType,
        mode,
        uiMode,
        isExpertMode,
        isTeamPreselected,
        existingData,
        dropdownData,
        teamFilter,
        creationContext,
        getFormValue,
        getFilteredBridges,
        t,
      }),
    [
      resourceType,
      mode,
      uiMode,
      isExpertMode,
      isTeamPreselected,
      existingData,
      dropdownData,
      teamFilter,
      creationContext,
      getFormValue,
      getFilteredBridges,
      t,
    ]
  );

  // Helper functions
  const getEntityType = () => resourceType.toUpperCase();
  const getVaultFieldName = () => 'vaultContent';

  // Modal header renderer props
  const modalHeaderProps = {
    resourceType,
    mode,
    uiMode,
    isExpertMode,
    isTeamPreselected,
    existingData,
    teamFilter,
    creationContext,
    getFormValue,
    t,
  };

  // Handle form submission
  const handleSubmit = async (data: ResourceFormValues) => {
    // Validate machine creation - check if SSH password is present without SSH key configured
    if (mode === 'create' && resourceType === 'machine') {
      const vaultString = typeof data.machineVault === 'string' ? data.machineVault : '';
      const vaultData: Record<string, unknown> = vaultString ? JSON.parse(vaultString) : {};
      const sshPassword = vaultData.ssh_password;
      const sshKeyConfigured = vaultData.ssh_key_configured;

      if (typeof sshPassword === 'string' && sshPassword && !sshKeyConfigured) {
        message.error('machines:validation.sshPasswordNotAllowed');
        return;
      }

      if (!testConnectionSuccess) {
        message.warning('machines:validation.sshConnectionNotTested');
      }
    }

    // Transform form data using utility
    const transformedData = await transformFormData(data, {
      resourceType,
      mode,
      uiMode,
      existingData,
      selectedTemplate,
      autoSetupEnabled,
    });

    await onSubmit(transformedData);
  };

  // Show functions button only for machines, repositories, and storage
  const showFunctions =
    (resourceType === 'machine' || resourceType === 'repository' || resourceType === 'storage') &&
    mode === 'create' &&
    existingData &&
    !existingData.prefilledMachine && // Don't show functions when creating repository from machine
    onFunctionSubmit &&
    functionCategories.length > 0;

  // Auto-open function modal if we're in create mode with existing data (for repository functions)
  // WARNING: The !functionModal.isOpen check is critical to prevent infinite render loops!
  // Without it, each call to functionModal.open() triggers a state change, causing re-render,
  // which triggers this effect again, leading to "Maximum update depth exceeded" error.
  useEffect(() => {
    if (open && mode === 'create' && existingData && showFunctions && !isFunctionModalOpen) {
      openFunctionModal();
    }
  }, [open, mode, existingData, showFunctions, isFunctionModalOpen, openFunctionModal]);

  // If we're in vault mode, show the vault editor directly
  if (mode === 'vault' && existingData && onUpdateVault) {
    return (
      <VaultEditorModal
        open={open}
        onCancel={onCancel}
        onSave={async (vault, version) => {
          await onUpdateVault(vault, version);
          onCancel();
        }}
        entityType={getEntityType()}
        title={t('general.configureVault', { name: existingData[`${resourceType}Name`] || '' })}
        initialVault={existingData.vaultContent || '{}'}
        initialVersion={existingData.vaultVersion || 1}
        loading={isUpdatingVault}
      />
    );
  }

  // If we're showing functions directly, don't show the main modal
  if (
    mode === 'create' &&
    existingData &&
    showFunctions &&
    functionModal.isOpen &&
    !existingData.prefilledMachine
  ) {
    return (
      <>
        {/* Function Selection Modal */}
        <FunctionSelectionModal
          open={functionModal.isOpen}
          onCancel={() => {
            functionModal.close();
            onCancel();
          }}
          onSubmit={async (functionData) => {
            await onFunctionSubmit(functionData);
            functionModal.close();
            onCancel();
          }}
          title={getFunctionTitle(resourceType, t)}
          subtitle={createFunctionSubtitle(resourceType, existingData, t)}
          allowedCategories={functionCategories}
          loading={isSubmitting}
          showMachineSelection={resourceType === 'repository' || resourceType === 'storage'}
          teamName={existingData?.teamName}
          machines={(
            dropdownData?.machinesByTeam?.find((tm) => tm.teamName === existingData?.teamName)
              ?.machines || []
          ).map((m) => ({ ...m, bridgeName: '' }))}
          hiddenParams={hiddenParams}
          defaultParams={defaultParams}
          preselectedFunction={preselectedFunction}
        />
      </>
    );
  }

  return (
    <>
      <Modal
        data-testid="resource-modal"
        title={renderModalTitle(modalHeaderProps)}
        open={open}
        onCancel={onCancel}
        destroyOnClose
        footer={[
          <Flex align="center" justify="space-between" gap={16} key="footer-container">
            <Flex align="center" gap={8}>
              {mode === 'create' && uiMode === 'expert' && (
                <Space>
                  <Upload
                    data-testid="resource-modal-upload-json"
                    accept=".json"
                    showUploadList={false}
                    beforeUpload={(file) => {
                      if (importExportHandlers.current) {
                        return importExportHandlers.current.handleImport(file);
                      }
                      return false;
                    }}
                  >
                    <Button
                      data-testid="resource-modal-import-button"
                      icon={<UploadOutlined style={{ fontSize: 12 }} />}
                    >
                      {t('common:vaultEditor.importJson')}
                    </Button>
                  </Upload>
                  <Button
                    data-testid="resource-modal-export-button"
                    icon={<DownloadOutlined style={{ fontSize: 12 }} />}
                    onClick={() => {
                      if (importExportHandlers.current) {
                        importExportHandlers.current.handleExport();
                      }
                    }}
                  >
                    {t('common:vaultEditor.exportJson')}
                  </Button>
                </Space>
              )}
            </Flex>
            <Flex align="center" gap={8}>
              {mode === 'create' && resourceType === 'machine' && (
                <Checkbox
                  data-testid="resource-modal-auto-setup-checkbox"
                  checked={autoSetupEnabled}
                  onChange={(e) => setAutoSetupEnabled(e.target.checked)}
                >
                  {t('machines:autoSetupAfterCreation')}
                </Checkbox>
              )}
              <Button data-testid="resource-modal-cancel-button" onClick={onCancel}>
                {t('general.cancel')}
              </Button>
              {mode === 'create' && existingData && onUpdateVault && (
                <Button data-testid="resource-modal-vault-button" onClick={() => vaultModal.open()}>
                  {t('general.vault')}
                </Button>
              )}
              {showFunctions && (
                <Button
                  data-testid="resource-modal-functions-button"
                  onClick={() => functionModal.open()}
                >
                  {t(`${resourceType}s.${resourceType}Functions`)}
                </Button>
              )}
              <Button
                data-testid="resource-modal-ok-button"
                loading={isSubmitting}
                disabled={mode === 'create' && resourceType === 'machine' && !testConnectionSuccess}
                onClick={() => {
                  if (formRef.current) {
                    formRef.current.submit();
                  }
                }}
              >
                {mode === 'create' ? t('general.create') : t('general.save')}
              </Button>
            </Flex>
          </Flex>,
        ]}
        className={ModalSize.Fullscreen}
      >
        <ResourceFormWithVault
          ref={formRef}
          form={form}
          fields={formFields}
          onSubmit={handleSubmit}
          entityType={getEntityType()}
          vaultFieldName={getVaultFieldName()}
          showDefaultsAlert={false}
          creationContext={creationContext}
          uiMode={uiMode}
          initialVaultData={parseVaultData(resourceType, existingData)}
          hideImportExport={true}
          isEditMode={mode === 'edit'}
          onImportExportRef={(handlers) => {
            importExportHandlers.current = handlers;
          }}
          teamName={resolveTeamName(getFormValue, existingData, teamFilter)}
          bridgeName={resolveBridgeName(getFormValue)}
          onTestConnectionStateChange={setTestConnectionSuccess}
          isModalOpen={open}
          beforeVaultContent={undefined}
          afterVaultContent={
            resourceType === 'repository' &&
            mode === 'create' &&
            creationContext !== 'credentials-only' ? (
              <Collapse
                data-testid="resource-modal-template-collapse"
                items={[
                  {
                    key: 'template',
                    label: (
                      <Space size="small">
                        <AppstoreOutlined />
                        <Typography.Text>{t('resources:templates.selectTemplate')}</Typography.Text>
                        {selectedTemplate && (
                          <Tag color="processing">
                            {selectedTemplate.replace(/^(db_|kick_|route_)/, '')}
                          </Tag>
                        )}
                      </Space>
                    ),
                    children: (
                      <TemplateSelector
                        value={selectedTemplate}
                        onChange={(templateId) => {
                          if (Array.isArray(templateId)) {
                            setSelectedTemplate(templateId[0] || null);
                          } else {
                            setSelectedTemplate(templateId);
                          }
                        }}
                        onViewDetails={(templateName) => {
                          setTemplateToView(templateName);
                          setShowTemplateDetails(true);
                        }}
                      />
                    ),
                  },
                ]}
              />
            ) : undefined
          }
          defaultsContent={
            <Space direction="vertical" size={4}>
              <Typography.Text>{t('general.team')}: Private Team</Typography.Text>
              {resourceType === 'machine' && (
                <>
                  <Typography.Text>{t('machines:region')}: Default Region</Typography.Text>
                  <Typography.Text>{t('machines:bridge')}: Global Bridges</Typography.Text>
                </>
              )}
            </Space>
          }
        />
      </Modal>

      {/* Sub-modals */}
      <ResourceModalDialogs
        // Vault Editor
        showVaultEditor={!!(existingData && onUpdateVault)}
        vaultModal={vaultModal}
        entityType={getEntityType()}
        vaultTitle={t('general.configureVault', {
          name: existingData?.[`${resourceType}Name`] || '',
        })}
        initialVault={existingData?.vaultContent || '{}'}
        initialVersion={existingData?.vaultVersion || 1}
        isUpdatingVault={isUpdatingVault}
        onVaultSave={async (vault, version) => {
          if (onUpdateVault) {
            await onUpdateVault(vault, version);
            vaultModal.close();
          }
        }}
        onVaultCancel={vaultModal.close}
        // Function Selection
        showFunctionModal={!!(showFunctions && existingData)}
        functionModal={functionModal}
        functionTitle={getFunctionTitle(resourceType, t)}
        functionSubtitle={createFunctionSubtitle(resourceType, existingData, t)}
        functionCategories={functionCategories}
        isSubmitting={isSubmitting}
        showMachineSelection={resourceType === 'repository' || resourceType === 'storage'}
        teamName={existingData?.teamName}
        machines={(
          dropdownData?.machinesByTeam?.find((tm) => tm.teamName === existingData?.teamName)
            ?.machines || []
        ).map((m) => ({ ...m, bridgeName: '' }))}
        hiddenParams={hiddenParams}
        defaultParams={defaultParams}
        preselectedFunction={preselectedFunction}
        onFunctionSubmit={async (functionData) => {
          if (onFunctionSubmit) {
            await onFunctionSubmit(functionData);
            functionModal.close();
          }
        }}
        onFunctionCancel={functionModal.close}
        // Template Preview
        showTemplatePreview={showTemplateDetails}
        templateToView={templateToView}
        onTemplateClose={() => {
          setShowTemplateDetails(false);
          setTemplateToView(null);
        }}
        onTemplateUse={(templateName) => {
          setSelectedTemplate(typeof templateName === 'string' ? templateName : templateName.name);
          setShowTemplateDetails(false);
          setTemplateToView(null);
        }}
      />
    </>
  );
};

export default UnifiedResourceModal;
export type { ExistingResourceData, ResourceType, ResourceFormValues };
