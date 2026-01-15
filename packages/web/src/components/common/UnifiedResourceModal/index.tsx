/* eslint-disable max-lines */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Collapse, Form, Space, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import { useDropdownData } from '@/api/queries/useDropdownData';
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal';
import { SizedModal } from '@/components/common/SizedModal';
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
import { AppstoreOutlined } from '@/utils/optimizedIcons';
import type { QueueFunction } from '@rediacc/shared/types';
import { InfrastructurePills } from './components/InfrastructurePills';
import { ModalFooter } from './components/ModalFooter';
import {
  createFunctionSubtitle,
  getBridgeName,
  getFunctionTitle,
  ModalTitleRenderer,
  resolveTeamName,
} from './components/ModalHeaderRenderer';
import { ResourceModalDialogs } from './components/ResourceModalDialogs';
import { useBridgeSelection } from './hooks/useBridgeSelection';
import { useResourceDefaults } from './hooks/useResourceDefaults';
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

const buildExistingDataKey = (
  resourceType: ResourceType,
  mode: 'create' | 'edit' | 'vault',
  existingData?: ExistingResourceData
): string => {
  if (!existingData) {
    return `${resourceType}:${mode}:none`;
  }
  const resourceNameKey = `${resourceType}Name`;
  const resourceName = existingData[resourceNameKey];
  if (typeof resourceName === 'string' && resourceName) {
    const vaultVersion = existingData.vaultVersion ?? '';
    return `${resourceType}:${mode}:${resourceName}:${vaultVersion}`;
  }
  try {
    return `${resourceType}:${mode}:${JSON.stringify(existingData)}`;
  } catch {
    return `${resourceType}:${mode}:unstringifiable`;
  }
};

const normalizeExistingData = (
  existingData?: ExistingResourceData
): ExistingResourceData | undefined => {
  if (!existingData) return undefined;
  if (existingData.vaultVersion == null) {
    const { vaultVersion: _vaultVersion, ...rest } = existingData;
    return { ...rest, vaultVersion: undefined };
  }
  return existingData;
};

const DEFAULT_VAULT_CONTENT = '{}';
const EMPTY_STRING_LIST: string[] = [];
const EMPTY_PARAMS: FunctionParamsMap = {};

const EDIT_EXTRAS: Partial<
  Record<ResourceType, (data: ExistingResourceData) => Partial<ResourceFormValues>>
> = {
  machine: (data) => ({ regionName: data.regionName, bridgeName: data.bridgeName }),
  bridge: (data) => ({ regionName: data.regionName }),
  pool: (data) => ({ clusterName: data.clusterName }),
  image: (data) => ({ poolName: data.poolName }),
  snapshot: (data) => ({ poolName: data.poolName, imageName: data.imageName }),
  clone: (data) => ({
    poolName: data.poolName,
    imageName: data.imageName,
    snapshotName: data.snapshotName,
  }),
};

const CREATE_EXTRAS: Partial<
  Record<ResourceType, (uiMode: 'simple' | 'expert') => Partial<ResourceFormValues>>
> = {
  machine: (uiMode) => ({
    regionName: uiMode === 'simple' ? 'Default Region' : '',
    bridgeName: uiMode === 'simple' ? 'Global Bridges' : '',
  }),
  repository: () => ({ machineName: '', size: '', repositoryGuid: '' }),
  team: () => ({ teamName: '' }),
  bridge: () => ({ regionName: '' }),
  pool: () => ({ clusterName: '' }),
  image: () => ({ poolName: '' }),
  snapshot: () => ({ poolName: '', imageName: '' }),
  clone: () => ({ poolName: '', imageName: '', snapshotName: '' }),
};

type MachineValidationResult =
  | { valid: true; warn?: boolean }
  | { valid: false; errorKey?: string };

const validateMachineCreation = (
  data: ResourceFormValues,
  testConnectionSuccess: boolean
): MachineValidationResult => {
  const vaultString = typeof data.machineVault === 'string' ? data.machineVault : '';
  const vaultData: Record<string, unknown> = vaultString ? JSON.parse(vaultString) : {};
  const sshPassword = vaultData.ssh_password;
  const sshKeyConfigured = vaultData.ssh_key_configured;

  if (typeof sshPassword === 'string' && sshPassword && !sshKeyConfigured) {
    return { valid: false, errorKey: 'machines:validation.sshPasswordNotAllowed' };
  }

  if (!testConnectionSuccess) {
    return { valid: true, warn: true };
  }

  return { valid: true };
};

const applyExistingData = (
  defaults: ResourceFormValues,
  existingData?: ExistingResourceData
): ResourceFormValues => {
  if (!existingData) return defaults;
  Object.keys(existingData).forEach((key) => {
    if (existingData[key] !== undefined) {
      defaults[key] = existingData[key];
    }
  });
  return defaults;
};

const buildDefaultValues = ({
  resourceType,
  mode,
  uiMode,
  existingData,
}: {
  resourceType: ResourceType;
  mode: 'create' | 'edit' | 'vault';
  uiMode: 'simple' | 'expert';
  existingData?: ExistingResourceData;
}): ResourceFormValues => {
  const nameKey = `${resourceType}Name`;

  if (mode === 'edit' && existingData) {
    return {
      [nameKey]: existingData[nameKey],
      ...(EDIT_EXTRAS[resourceType]?.(existingData) ?? {}),
      vaultContent: existingData.vaultContent ?? DEFAULT_VAULT_CONTENT,
    };
  }

  const baseDefaults: ResourceFormValues = {
    teamName: uiMode === 'simple' ? 'Private Team' : '',
    vaultContent: DEFAULT_VAULT_CONTENT,
    [nameKey]: '',
  };

  const resourceDefaults = CREATE_EXTRAS[resourceType]?.(uiMode) ?? {};
  return applyExistingData({ ...baseDefaults, ...resourceDefaults }, existingData);
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
  functionCategories = EMPTY_STRING_LIST,
  hiddenParams = EMPTY_STRING_LIST,
  defaultParams = EMPTY_PARAMS,
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

  const existingDataKey = useMemo(
    () => buildExistingDataKey(resourceType, mode, existingData),
    [resourceType, mode, existingData]
  );
  // eslint-disable-next-line react-hooks/exhaustive-deps -- Intentionally using existingDataKey for stable reference
  const stableExistingData = useMemo(() => normalizeExistingData(existingData), [existingDataKey]);

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
  } = useTemplateSelection({ existingData: stableExistingData });

  // Import/Export handlers ref
  const importExportHandlers = useRef<ImportExportHandlers | null>(null);
  const handleImportExportRef = useCallback((handlers: ImportExportHandlers) => {
    importExportHandlers.current = handlers;
  }, []);

  // Ant Design Form instance
  const [form] = Form.useForm<ResourceFormValues>();

  const getFormValue = useCallback(
    (field: string): string | undefined => {
      const rawValue = form.getFieldValue(field);
      return typeof rawValue === 'string' ? rawValue : undefined;
    },
    [form]
  );

  // Get default values for form initialization
  const defaultValues = useMemo(
    () =>
      buildDefaultValues({
        resourceType,
        mode,
        uiMode,
        existingData: stableExistingData,
      }),
    [mode, resourceType, uiMode, stableExistingData]
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
    existingData: stableExistingData,
    teamFilter,
    setSelectedTemplate,
  });

  // Reset form values when modal opens
  const formInitKey = useMemo(
    () => `${resourceType}:${mode}:${existingDataKey}:${open ? 'open' : 'closed'}`,
    [resourceType, mode, existingDataKey, open]
  );
  const lastFormInitKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!open) {
      lastFormInitKeyRef.current = null;
      return;
    }

    if (lastFormInitKeyRef.current === formInitKey) {
      return;
    }

    lastFormInitKeyRef.current = formInitKey;
    form.resetFields();
    // Type assertion needed: Ant Design expects { [x: string]: {} | undefined }
    // but ResourceFormValues uses unknown for flexibility
    form.setFieldsValue(defaultValues as Record<string, {} | undefined>);
  }, [open, form, defaultValues, formInitKey]);

  // Determine if team is already selected/known
  // In simple mode, team is always preselected (uses "Private Team")
  // In expert mode, always show team dropdown so user can select any team
  const isTeamPreselected = uiMode === 'simple';

  // Get form fields based on resource type and mode
  const formFields = useMemo(
    () =>
      getFormFields({
        resourceType,
        mode,
        uiMode,
        isExpertMode,
        isTeamPreselected,
        existingData: stableExistingData,
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
      stableExistingData,
      dropdownData,
      teamFilter,
      creationContext,
      getFormValue,
      getFilteredBridges,
      t,
    ]
  );

  const initialVaultData = useMemo(
    () => parseVaultData(resourceType, stableExistingData),
    [resourceType, stableExistingData]
  );
  const entityType = resourceType.toUpperCase();

  // Modal header renderer props
  const modalHeaderProps = useMemo(
    () => ({
      resourceType,
      mode,
      uiMode,
      isExpertMode,
      isTeamPreselected,
      existingData: stableExistingData,
      teamFilter,
      creationContext,
      getFormValue,
      t,
    }),
    [
      resourceType,
      mode,
      uiMode,
      isExpertMode,
      isTeamPreselected,
      stableExistingData,
      teamFilter,
      creationContext,
      getFormValue,
      t,
    ]
  );

  // Handle form submission
  const handleSubmit = useCallback(
    async (data: ResourceFormValues) => {
      // Validate machine creation
      if (mode === 'create' && resourceType === 'machine') {
        const validation = validateMachineCreation(data, testConnectionSuccess);
        if (!validation.valid) {
          message.error(validation.errorKey ?? 'machines:validation.errorOccurred');
          return;
        }
        if ('warn' in validation && validation.warn) {
          message.warning('machines:validation.sshConnectionNotTested');
        }
      }

      // Transform form data using utility
      const transformedData = await transformFormData(data, {
        resourceType,
        mode,
        uiMode,
        existingData: stableExistingData,
        selectedTemplate,
        autoSetupEnabled,
      });

      await onSubmit(transformedData);
    },
    [
      mode,
      resourceType,
      message,
      testConnectionSuccess,
      uiMode,
      stableExistingData,
      selectedTemplate,
      autoSetupEnabled,
      onSubmit,
    ]
  );

  // Show functions button only for machines, repositories, and storage
  const showFunctions = Boolean(
    (resourceType === 'machine' || resourceType === 'repository' || resourceType === 'storage') &&
      mode === 'create' &&
      stableExistingData &&
      !stableExistingData.prefilledMachine && // Don't show functions when creating repository from machine
      onFunctionSubmit &&
      functionCategories.length > 0
  );

  // Auto-open function modal if we're in create mode with existing data (for repository functions)
  // WARNING: The !functionModal.isOpen check is critical to prevent infinite render loops!
  // Without it, each call to functionModal.open() triggers a state change, causing re-render,
  // which triggers this effect again, leading to "Maximum update depth exceeded" error.
  useEffect(() => {
    if (open && mode === 'create' && stableExistingData && showFunctions && !isFunctionModalOpen) {
      openFunctionModal();
    }
  }, [open, mode, stableExistingData, showFunctions, isFunctionModalOpen, openFunctionModal]);

  // If we're in vault mode, show the vault editor directly
  if (mode === 'vault' && stableExistingData && onUpdateVault) {
    return (
      // Connect form instance to prevent "useForm not connected" warning
      <Form form={form} component={false}>
        <VaultEditorModal
          open={open}
          onCancel={onCancel}
          onSave={async (vault, version) => {
            await onUpdateVault(vault, version);
            onCancel();
          }}
          entityType={entityType}
          title={t('general.configureVault', {
            name: (stableExistingData[`${resourceType}Name`] as string | null) ?? '',
          })}
          initialVault={stableExistingData.vaultContent ?? '{}'}
          initialVersion={stableExistingData.vaultVersion ?? 1}
          loading={isUpdatingVault}
        />
      </Form>
    );
  }

  // If we're showing functions directly, don't show the main modal
  if (
    mode === 'create' &&
    stableExistingData &&
    showFunctions &&
    functionModal.isOpen &&
    !stableExistingData.prefilledMachine
  ) {
    return (
      // Connect form instance to prevent "useForm not connected" warning
      <Form form={form} component={false}>
        {/* Function Selection Modal */}
        <FunctionSelectionModal
          open={functionModal.isOpen}
          onCancel={() => {
            functionModal.close();
            onCancel();
          }}
          onSubmit={async (functionData) => {
            if (onFunctionSubmit) {
              await onFunctionSubmit(functionData);
            }
            functionModal.close();
            onCancel();
          }}
          title={getFunctionTitle(resourceType, t)}
          subtitle={createFunctionSubtitle(resourceType, stableExistingData, t)}
          allowedCategories={functionCategories}
          loading={isSubmitting}
          showMachineSelection={resourceType === 'repository' || resourceType === 'storage'}
          teamName={stableExistingData.teamName ?? undefined}
          machines={(
            dropdownData?.machinesByTeam.find((tm) => tm.teamName === stableExistingData.teamName)
              ?.machines ?? []
          ).map((m) => ({ ...m, bridgeName: '' }))}
          hiddenParams={hiddenParams}
          defaultParams={defaultParams}
          preselectedFunction={preselectedFunction}
        />
      </Form>
    );
  }

  return (
    <>
      <SizedModal
        data-testid="resource-modal"
        title={<ModalTitleRenderer {...modalHeaderProps} />}
        open={open}
        onCancel={onCancel}
        destroyOnHidden
        size={ModalSize.Fullscreen}
        footer={[
          <ModalFooter
            key="footer"
            mode={mode}
            resourceType={resourceType}
            uiMode={uiMode}
            isSubmitting={isSubmitting}
            testConnectionSuccess={testConnectionSuccess}
            autoSetupEnabled={autoSetupEnabled}
            setAutoSetupEnabled={setAutoSetupEnabled}
            existingData={stableExistingData}
            showFunctions={showFunctions}
            onCancel={onCancel}
            onUpdateVault={onUpdateVault}
            onVaultOpen={() => vaultModal.open()}
            onFunctionOpen={() => functionModal.open()}
            onSubmit={() => {
              if (formRef.current) {
                void formRef.current.submit();
              }
            }}
            importExportHandlers={importExportHandlers}
            t={t}
          />,
        ]}
      >
        <ResourceFormWithVault
          key={existingDataKey}
          ref={formRef}
          form={form}
          fields={formFields}
          onSubmit={handleSubmit}
          entityType={entityType}
          showDefaultsAlert={false}
          uiMode={uiMode}
          initialVaultData={initialVaultData}
          hideImportExport
          isEditMode={mode === 'edit'}
          onImportExportRef={handleImportExportRef}
          teamName={resolveTeamName(getFormValue, stableExistingData, teamFilter)}
          bridgeName={getBridgeName(getFormValue)}
          onTestConnectionStateChange={setTestConnectionSuccess}
          isModalOpen={open}
          beforeVaultContent={
            <InfrastructurePills
              resourceType={resourceType}
              mode={mode}
              uiMode={uiMode}
              form={form}
              dropdownData={dropdownData}
              getFilteredBridges={getFilteredBridges}
            />
          }
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
                          <Tag>{selectedTemplate.replace(/^(db_|kick_|route_)/, '')}</Tag>
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
              <Typography.Text>
                {t('general.team')}: {t('defaults.privateTeam')}
              </Typography.Text>
              {resourceType === 'machine' && (
                <>
                  <Typography.Text>
                    {t('machines:region')}: {t('defaults.defaultRegion')}
                  </Typography.Text>
                  <Typography.Text>
                    {t('machines:bridge')}: {t('defaults.globalBridges')}
                  </Typography.Text>
                </>
              )}
            </Space>
          }
        />
      </SizedModal>

      {/* Sub-modals */}
      <ResourceModalDialogs
        // Vault Editor
        showVaultEditor={!!(stableExistingData && onUpdateVault)}
        vaultModal={vaultModal}
        entityType={entityType}
        vaultTitle={t('general.configureVault', {
          name: (stableExistingData?.[`${resourceType}Name`] as string | null) ?? '',
        })}
        initialVault={stableExistingData?.vaultContent ?? '{}'}
        initialVersion={stableExistingData?.vaultVersion ?? 1}
        isUpdatingVault={isUpdatingVault}
        onVaultSave={async (vault, version) => {
          if (onUpdateVault) {
            await onUpdateVault(vault, version);
            vaultModal.close();
          }
        }}
        onVaultCancel={vaultModal.close}
        // Function Selection
        showFunctionModal={!!(showFunctions && stableExistingData)}
        functionModal={functionModal}
        functionTitle={getFunctionTitle(resourceType, t)}
        functionSubtitle={createFunctionSubtitle(resourceType, stableExistingData, t)}
        functionCategories={functionCategories}
        isSubmitting={isSubmitting}
        showMachineSelection={resourceType === 'repository' || resourceType === 'storage'}
        teamName={stableExistingData?.teamName ?? undefined}
        machines={(
          dropdownData?.machinesByTeam.find((tm) => tm.teamName === stableExistingData?.teamName)
            ?.machines ?? []
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
