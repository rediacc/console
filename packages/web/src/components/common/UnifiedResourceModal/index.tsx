import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Modal, message, Space, Upload } from 'antd';
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
import { RediaccButton, RediaccText } from '@/components/ui';
import { useDialogState } from '@/hooks/useDialogState';
import { templateService } from '@/services/templateService';
import { RootState } from '@/store/store';
import type { Machine, Repository } from '@/types';
import { ModalSize } from '@/types/modal';
import { AppstoreOutlined } from '@/utils/optimizedIcons';
import type { GetCompanyTeams_ResultSet1 } from '@rediacc/shared/types';
import {
  renderModalTitle,
  resolveTeamName,
  resolveBridgeName,
  createFunctionSubtitle,
  getFunctionTitle,
} from './components/ModalHeaderRenderer';
import { ResourceModalDialogs } from './components/ResourceModalDialogs';
import { useBridgeSelection } from './hooks/useBridgeSelection';
import { useResourceSchema } from './hooks/useResourceSchema';
import { useTemplateSelection } from './hooks/useTemplateSelection';
import {
  AutoSetupCheckbox,
  DownloadIcon,
  FooterLeftActions,
  SelectedTemplateTag,
  TemplateCollapse,
  UploadIcon,
} from './styles';
import { getFormFields } from './utils/formFieldGenerators';

export type ResourceType =
  | 'machine'
  | 'repository'
  | 'storage'
  | 'team'
  | 'region'
  | 'bridge'
  | 'cluster'
  | 'pool'
  | 'image'
  | 'snapshot'
  | 'clone';

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

type ResourceFormValues = Record<string, unknown>;

type ExistingResourceData = Partial<Machine> &
  Partial<Repository> &
  Partial<GetCompanyTeams_ResultSet1> & {
    prefilledMachine?: boolean;
    clusters?: Array<{ clusterName: string }>;
    pools?: Array<{ poolName: string; clusterName: string }>;
    availableMachines?: Array<{
      machineName: string;
      bridgeName: string;
      regionName: string;
      status?: string;
    }>;
    images?: Array<{ imageName: string }>;
    snapshots?: Array<{ snapshotName: string }>;
  } & Record<string, unknown>;

type FunctionParamsMap = Record<string, string | number | string[] | undefined>;

type FunctionSubmitPayload = {
  function: QueueFunction;
  params: FunctionParamsMap;
  priority: number;
  description: string;
  selectedMachine?: string;
};

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

  // Set default values when modal opens
  useEffect(() => {
    if (open && mode === 'create') {
      // Reset form to default values first
      form.reset(getDefaultValues());

      // Reset template selection for repositories (unless preselected)
      if (resourceType === 'repository') {
        const preselected =
          existingData &&
          typeof (existingData as Record<string, unknown>).preselectedTemplate === 'string'
            ? (existingData as Record<string, string>).preselectedTemplate || null
            : null;
        setSelectedTemplate(preselected);
      }

      // Set team if preselected or from existing data
      if (existingData?.teamName) {
        form.setValue('teamName', existingData.teamName);
      } else if (teamFilter) {
        if (Array.isArray(teamFilter) && teamFilter.length === 1) {
          const [singleTeam] = teamFilter;
          if (singleTeam) {
            form.setValue('teamName', singleTeam);
          }
        } else if (!Array.isArray(teamFilter)) {
          form.setValue('teamName', teamFilter);
        }
      }

      // For repositories, set prefilled machine
      if (resourceType === 'repository' && existingData?.machineName) {
        form.setValue('machineName', existingData.machineName);
      }

      // For machines, set default region and bridge
      // NOTE: Even when disableBridge is enabled and bridge field is hidden,
      // we still auto-select the first bridge to satisfy backend requirements
      if (resourceType === 'machine' && dropdownData?.regions && dropdownData.regions.length > 0) {
        const firstRegion = dropdownData.regions[0].value;
        form.setValue('regionName', firstRegion);

        const regionBridges = dropdownData.bridgesByRegion?.find(
          (region) => region.regionName === firstRegion
        );

        if (regionBridges?.bridges && regionBridges.bridges.length > 0) {
          const firstBridge = regionBridges.bridges[0].value;
          form.setValue('bridgeName', firstBridge);
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, mode, teamFilter, resourceType, form, dropdownData, existingData]);

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
      // Only block if password exists AND SSH key is not configured
      if (typeof sshPassword === 'string' && sshPassword && !sshKeyConfigured) {
        message.error(t('machines:validation.sshPasswordNotAllowed'));
        return;
      }

      if (!testConnectionSuccess) {
        message.warning(
          t('machines:validation.sshConnectionNotTested', {
            defaultValue:
              'SSH connection has not been tested yet. We recommend running Test Connection before creating.',
          })
        );
      }
    }

    if (uiMode === 'simple' && mode === 'create') {
      // Only set defaults if not already provided
      const defaults: ResourceFormValues = {};

      // Preserve teamName from existingData if available (e.g., when creating repository from machine)
      if (!data.teamName) {
        if (existingData?.teamName) {
          defaults.teamName = existingData.teamName;
        } else {
          defaults.teamName = 'Private Team';
        }
      }

      // Set machine-specific defaults
      if (resourceType === 'machine') {
        defaults.regionName = 'Default Region';
        defaults.bridgeName = 'Global Bridges';
      }

      Object.assign(data, defaults);
    }

    // For repository creation from machine, ensure machine name is included
    if (
      resourceType === 'repository' &&
      existingData?.machineName &&
      existingData?.prefilledMachine
    ) {
      data.machineName = existingData.machineName;
      // Also ensure teamName is preserved
      if (existingData?.teamName && !data.teamName) {
        data.teamName = existingData.teamName;
      }
    }

    // Add template parameter for repository creation
    if (resourceType === 'repository' && mode === 'create' && selectedTemplate) {
      try {
        // Fetch the template details by ID using templateService
        data.tmpl = await templateService.getEncodedTemplateDataById(selectedTemplate);
      } catch (error) {
        console.error('Failed to load template:', error);
        message.warning(t('resources:templates.failedToLoadTemplate'));
      }
    }

    // Always keep repository open after creation
    if (resourceType === 'repository' && mode === 'create') {
      data.keep_open = true;
    }

    // Add auto-setup flag for machine creation
    if (mode === 'create' && resourceType === 'machine') {
      data.autoSetup = autoSetupEnabled;
    }

    // For credential-only repository creation, ensure repositoryGuid is included
    if (mode === 'create' && resourceType === 'repository' && existingData?.repositoryGuid) {
      data.repositoryGuid = existingData.repositoryGuid;
    }

    await onSubmit(data);
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
          ...(mode === 'create' && uiMode === 'expert'
            ? [
                <FooterLeftActions key="left-buttons">
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
                      <RediaccButton
                        data-testid="resource-modal-import-button"
                        icon={<UploadIcon />}
                      >
                        {t('common:vaultEditor.importJson')}
                      </RediaccButton>
                    </Upload>
                    <RediaccButton
                      data-testid="resource-modal-export-button"
                      icon={<DownloadIcon />}
                      onClick={() => {
                        if (importExportHandlers.current) {
                          importExportHandlers.current.handleExport();
                        }
                      }}
                    >
                      {t('common:vaultEditor.exportJson')}
                    </RediaccButton>
                  </Space>
                </FooterLeftActions>,
              ]
            : []),
          ...(mode === 'create' && resourceType === 'machine'
            ? [
                <AutoSetupCheckbox
                  key="auto-setup"
                  data-testid="resource-modal-auto-setup-checkbox"
                  checked={autoSetupEnabled}
                  onChange={(e) => setAutoSetupEnabled(e.target.checked)}
                >
                  {t('machines:autoSetupAfterCreation')}
                </AutoSetupCheckbox>,
              ]
            : []),
          <RediaccButton key="cancel" data-testid="resource-modal-cancel-button" onClick={onCancel}>
            {t('general.cancel')}
          </RediaccButton>,
          ...(mode === 'create' && existingData && onUpdateVault
            ? [
                <RediaccButton
                  key="vault"
                  data-testid="resource-modal-vault-button"
                  onClick={() => vaultModal.open()}
                >
                  {t('general.vault')}
                </RediaccButton>,
              ]
            : []),
          ...(showFunctions
            ? [
                <RediaccButton
                  key="functions"
                  data-testid="resource-modal-functions-button"
                  onClick={() => functionModal.open()}
                >
                  {t(`${resourceType}s.${resourceType}Functions`)}
                </RediaccButton>,
              ]
            : []),
          <RediaccButton
            key="submit"
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
          </RediaccButton>,
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
          initialVaultData={(() => {
            if (existingData?.vaultContent) {
              try {
                let parsed = JSON.parse(existingData.vaultContent);
                // Special handling for repositories - map the vault data correctly
                if (resourceType === 'repository') {
                  // The vault data might have the credential at root level or nested
                  // We need to ensure it's in the format VaultEditor expects
                  if (!parsed.credential && parsed.repositoryVault) {
                    // If repositoryVault exists, it might contain the credential
                    try {
                      const innerVault =
                        typeof parsed.repositoryVault === 'string'
                          ? JSON.parse(parsed.repositoryVault)
                          : parsed.repositoryVault;
                      if (innerVault.credential) {
                        parsed = { credential: innerVault.credential };
                      }
                    } catch (e) {
                      console.error('[UnifiedResourceModal] Failed to parse inner vault:', e);
                    }
                  } else if (parsed.repositoryVault) {
                    // Or it might be in repositoryVault
                    try {
                      const innerVault =
                        typeof parsed.repositoryVault === 'string'
                          ? JSON.parse(parsed.repositoryVault)
                          : parsed.repositoryVault;
                      if (innerVault.credential) {
                        parsed = { credential: innerVault.credential };
                      }
                    } catch (e) {
                      console.error('[UnifiedResourceModal] Failed to parse repository vault:', e);
                    }
                  }
                  // If still no credential field but we have other fields, check if any could be the credential
                  if (!parsed.credential) {
                    // Check for any 32-character string that might be the credential
                    for (const [, value] of Object.entries(parsed)) {
                      if (
                        typeof value === 'string' &&
                        value.length === 32 &&
                        /^[A-Za-z0-9!@#$%^&*()_+{}|:<>,.?/]+$/.test(value)
                      ) {
                        parsed = { credential: value };
                        break;
                      }
                    }
                  }
                }
                return parsed;
              } catch (e) {
                console.error('[UnifiedResourceModal] Failed to parse vault content:', e);
                return {};
              }
            }
            return {};
          })()}
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
              <TemplateCollapse
                data-testid="resource-modal-template-collapse"
                items={[
                  {
                    key: 'template',
                    label: (
                      <Space size="small">
                        <AppstoreOutlined />
                        <RediaccText>{t('resources:templates.selectTemplate')}</RediaccText>
                        {selectedTemplate && (
                          <SelectedTemplateTag variant="primary">
                            {selectedTemplate.replace(/^(db_|kick_|route_)/, '')}
                          </SelectedTemplateTag>
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
              <RediaccText>{t('general.team')}: Private Team</RediaccText>
              {resourceType === 'machine' && (
                <>
                  <RediaccText>{t('machines:region')}: Default Region</RediaccText>
                  <RediaccText>{t('machines:bridge')}: Global Bridges</RediaccText>
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
export type { ExistingResourceData };
