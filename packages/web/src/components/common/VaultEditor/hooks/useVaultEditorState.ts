import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Form } from 'antd';
import { useTranslation } from 'react-i18next';
import { useTheme } from 'styled-components';
import { useCreateQueueItem, useQueueItemTrace } from '@/api/queries/queue';
import { useTeams } from '@/api/queries/teams';
import { useMessage } from '@/hooks';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import { STORAGE_FIELDS_TO_KEEP, storageProviderConfig, vaultDefinitionConfig } from '../constants';
import { decodeBase64, encodeBase64, formatValidationErrors, processExtraFields } from '../utils';
import type { ValidateErrorEntity, VaultEditorProps, VaultFormValues } from '../types';

export const useVaultEditorState = (props: VaultEditorProps) => {
  const {
    entityType,
    initialData = {},
    onChange,
    onValidate,
    onFieldMovement,
    onFormReady,
    showValidationErrors = false,
    onTestConnectionStateChange,
    onOsSetupStatusChange,
    isModalOpen,
    isEditMode = false,
  } = props;

  const { t } = useTranslation(['common', 'storageProviders']);
  const message = useMessage();
  const theme = useTheme();
  const [form] = Form.useForm();
  const [extraFields, setExtraFields] = useState<VaultFormValues>({});
  const [importedData, setImportedData] = useState<VaultFormValues>(initialData);
  const [rawJsonValue, setRawJsonValue] = useState<string>(() => {
    return Object.keys(initialData).length > 0 ? JSON.stringify(initialData, null, 2) : '{}';
  });
  const [rawJsonError, setRawJsonError] = useState<string | null>(null);
  const [_sshKeyConfigured, setSshKeyConfigured] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
  const [lastInitializedData, setLastInitializedData] = useState<string>('');
  const [testTaskId, setTestTaskId] = useState<string | null>(null);
  const [isTestingConnection, setIsTestingConnection] = useState(false);
  const [testConnectionSuccess, setTestConnectionSuccess] = useState(false);
  const [osSetupCompleted, setOsSetupCompleted] = useState<boolean | null>(null);
  const formatJsonRef = useRef<(() => void) | null>(null);
  const formGutter: [number, number] = [theme.spacing.SM, theme.spacing.SM];

  const { buildQueueVault } = useQueueVaultBuilder();
  const { mutate: createQueueItem, isPending: isCreatingQueueItem } = useCreateQueueItem();
  const { data: testTraceData } = useQueueItemTrace(testTaskId, isTestingConnection);
  const { data: teams } = useTeams();

  // Track previous modal open state
  const prevModalOpenRef = useRef(isModalOpen);

  // Get entity definition from JSON
  const entityDef = useMemo(() => {
    return vaultDefinitionConfig.entities[
      entityType as keyof typeof vaultDefinitionConfig.entities
    ];
  }, [entityType]);

  // Get provider-specific fields for STORAGE entity
  const providerFields = useMemo(() => {
    if (
      entityType === 'STORAGE' &&
      selectedProvider &&
      selectedProvider in storageProviderConfig.providers
    ) {
      return storageProviderConfig.providers[
        selectedProvider as keyof typeof storageProviderConfig.providers
      ];
    }
    return null;
  }, [entityType, selectedProvider]);

  // Direct onChange callback - no debouncing to avoid race conditions
  const directOnChange = useCallback(
    (data: VaultFormValues, hasChanges: boolean) => {
      onChange?.(data, hasChanges);
    },
    [onChange]
  );

  // Update raw JSON when form data changes
  const updateRawJson = useCallback(
    (data: VaultFormValues) => {
      try {
        const jsonString = JSON.stringify(data, null, 2);
        setRawJsonValue(jsonString);
        setRawJsonError(null);
      } catch {
        setRawJsonError(t('vaultEditor.failedToSerialize'));
      }
    },
    [t]
  );

  // Helper to show field movement toast messages
  const showFieldMovementToasts = useCallback(
    (movedToExtra: string[], movedFromExtra: string[]) => {
      if (movedToExtra.length > 0) {
        message.info('common:vaultEditor.fieldsMovedToExtra', {
          count: movedToExtra.length,
          fields: movedToExtra.join(', '),
        });
      }
      if (movedFromExtra.length > 0) {
        message.success('common:vaultEditor.fieldsMovedFromExtra', {
          count: movedFromExtra.length,
          fields: movedFromExtra.join(', '),
        });
      }
    },
    [message]
  );

  // Reset when modal opens (transitions from closed to open)
  useEffect(() => {
    if (isModalOpen && !prevModalOpenRef.current) {
      setLastInitializedData('');
      form.resetFields();
      form.setFields([]);
      setExtraFields({});
      setImportedData({});
      setRawJsonValue('{}');
      setRawJsonError(null);
      setSshKeyConfigured(false);
      setSelectedProvider(null);
      setTestConnectionSuccess(false);
    }
    prevModalOpenRef.current = isModalOpen;
  }, [isModalOpen, form]);

  // Update importedData when initialData prop changes
  useEffect(() => {
    setImportedData(initialData);
  }, [initialData]);

  // Monitor SSH test results
  useEffect(() => {
    if (testTraceData?.queueDetails && testTraceData?.responseVaultContent?.vaultContent) {
      const status =
        testTraceData.queueDetails.status ||
        (testTraceData.queueDetails as { Status?: string }).Status;

      if (status === 'COMPLETED') {
        try {
          const responseVault =
            typeof testTraceData.responseVaultContent.vaultContent === 'string'
              ? JSON.parse(testTraceData.responseVaultContent.vaultContent)
              : testTraceData.responseVaultContent.vaultContent;

          const result = responseVault.result ? JSON.parse(responseVault.result) : null;

          if (result) {
            if (result.status === 'success') {
              message.success('common:vaultEditor.testConnection.success');

              if (result.ssh_key_configured !== undefined) {
                form.setFieldValue('ssh_key_configured', result.ssh_key_configured);
                setSshKeyConfigured(result.ssh_key_configured);
              }

              if (result.host_entry) {
                form.setFieldValue('host_entry', result.host_entry);
              }

              if (result.kernel_compatibility) {
                form.setFieldValue('kernel_compatibility', result.kernel_compatibility);
              }

              if (
                result.kernel_compatibility &&
                result.kernel_compatibility.os_setup_completed !== undefined
              ) {
                setOsSetupCompleted(result.kernel_compatibility.os_setup_completed);
                if (onOsSetupStatusChange) {
                  onOsSetupStatusChange(result.kernel_compatibility.os_setup_completed);
                }
              }

              form.setFieldValue('ssh_password', '');
              setTestConnectionSuccess(true);

              if (onTestConnectionStateChange) {
                onTestConnectionStateChange(true);
              }

              handleFormChange({
                ssh_key_configured: result.ssh_key_configured,
                host_entry: result.host_entry,
                ssh_password: '',
              });
            } else {
              message.error(result.message || 'common:vaultEditor.testConnection.failed');
              setTestConnectionSuccess(false);
              if (onTestConnectionStateChange) {
                onTestConnectionStateChange(false);
              }
            }
          }
        } catch {
          message.error('common:vaultEditor.testConnection.failed');
          setTestConnectionSuccess(false);
          if (onTestConnectionStateChange) {
            onTestConnectionStateChange(false);
          }
        } finally {
          setIsTestingConnection(false);
          setTestTaskId(null);
        }
      } else if (status === 'FAILED' || status === 'CANCELLED') {
        message.error('common:vaultEditor.testConnection.failed');
        setIsTestingConnection(false);
        setTestTaskId(null);
        setTestConnectionSuccess(false);
        if (onTestConnectionStateChange) {
          onTestConnectionStateChange(false);
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [testTraceData, form, message, onOsSetupStatusChange, onTestConnectionStateChange]);

  // Stabilize importedData to prevent unnecessary re-renders
  const importedDataString = useMemo(() => JSON.stringify(importedData), [importedData]);

  // Calculate extra fields not in schema
  useEffect(() => {
    if (!entityDef) return;

    let schemaFields = Object.keys(entityDef.fields || {});

    if (entityType === 'STORAGE' && importedData.provider) {
      const provider =
        storageProviderConfig.providers[
          importedData.provider as keyof typeof storageProviderConfig.providers
        ];
      if (provider && provider.fields) {
        schemaFields = [...schemaFields, ...Object.keys(provider.fields)];
      }
    }

    const { extras, movedToExtra, movedFromExtra } = processExtraFields(
      importedData,
      schemaFields,
      extraFields
    );

    const extrasString = JSON.stringify(extras);
    const currentExtrasString = JSON.stringify(extraFields);

    if (extrasString !== currentExtrasString) {
      setExtraFields(extras);

      if ((movedToExtra.length > 0 || movedFromExtra.length > 0) && onFieldMovement) {
        onFieldMovement(movedToExtra, movedFromExtra);
      }

      showFieldMovementToasts(movedToExtra, movedFromExtra);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [importedDataString, entityDef, entityType, onFieldMovement, showFieldMovementToasts]);

  // Initialize form with data
  useEffect(() => {
    if (entityDef) {
      const currentDataString = JSON.stringify(initialData);
      const wasNonEmpty = lastInitializedData && lastInitializedData !== '{}';
      const isNowEmpty = currentDataString === '{}';

      if (currentDataString === lastInitializedData && !(wasNonEmpty && isNowEmpty)) {
        return;
      }

      const formData: VaultFormValues = {};
      Object.entries(entityDef.fields || {}).forEach(([key, field]) => {
        if (initialData[key] !== undefined) {
          if (field.format === 'base64' && typeof initialData[key] === 'string') {
            formData[key] = decodeBase64(initialData[key]);
          } else {
            formData[key] = initialData[key];
          }
        } else if (field.default !== undefined) {
          formData[key] = field.default;
        }
      });

      if (entityType === 'STORAGE' && initialData.provider) {
        const provider =
          storageProviderConfig.providers[
            initialData.provider as keyof typeof storageProviderConfig.providers
          ];
        if (provider && provider.fields) {
          Object.entries(provider.fields).forEach(([key, field]) => {
            if (initialData[key] !== undefined) {
              if (field.format === 'base64' && typeof initialData[key] === 'string') {
                formData[key] = decodeBase64(initialData[key]);
              } else {
                formData[key] = initialData[key];
              }
            } else if (field.default !== undefined) {
              formData[key] = field.default;
            }
          });
        }
      }

      form.resetFields();
      form.setFieldsValue(formData);

      setSshKeyConfigured(false);
      setSelectedProvider(null);
      setRawJsonError(null);

      if (
        (entityType === 'MACHINE' || entityType === 'BRIDGE') &&
        formData.ssh_key_configured !== undefined
      ) {
        setSshKeyConfigured(
          typeof formData.ssh_key_configured === 'boolean' ? formData.ssh_key_configured : false
        );
      }

      if (entityType === 'STORAGE' && formData.provider) {
        setSelectedProvider(typeof formData.provider === 'string' ? formData.provider : null);
      }

      let schemaFields = Object.keys(entityDef.fields || {});

      if (entityType === 'STORAGE' && initialData.provider) {
        const provider =
          storageProviderConfig.providers[
            initialData.provider as keyof typeof storageProviderConfig.providers
          ];
        if (provider && provider.fields) {
          schemaFields = [...schemaFields, ...Object.keys(provider.fields)];
        }
      }

      const extras: VaultFormValues = {};

      if (initialData.extraFields && typeof initialData.extraFields === 'object') {
        Object.assign(extras, initialData.extraFields);
      }

      Object.entries(initialData).forEach(([key, value]) => {
        if (key !== 'extraFields' && !schemaFields.includes(key)) {
          extras[key] = value;
        }
      });

      const completeData = { ...formData };
      if (Object.keys(extras).length > 0) {
        completeData.extraFields = extras;
      }

      updateRawJson(completeData);
      setLastInitializedData(currentDataString);

      setTimeout(() => {
        if (!(isEditMode && entityType === 'REPOSITORY')) {
          form
            .validateFields(undefined, { validateOnly: true })
            .then(() => {
              onValidate?.(true);
              if (!showValidationErrors) {
                form.getFieldsError().forEach(({ name }) => {
                  form.setFields([{ name, errors: [] }]);
                });
              }
            })
            .catch((errorInfo: ValidateErrorEntity<VaultFormValues>) => {
              const errors = formatValidationErrors(errorInfo);
              onValidate?.(false, errors);
              if (!showValidationErrors) {
                form.getFieldsError().forEach(({ name }) => {
                  form.setFields([{ name, errors: [] }]);
                });
              }
            });
        } else {
          onValidate?.(true);
        }
      }, 100);
    }
  }, [
    form,
    entityDef,
    entityType,
    initialData,
    updateRawJson,
    isEditMode,
    onValidate,
    lastInitializedData,
    showValidationErrors,
  ]);

  // Pass form instance to parent when ready
  useEffect(() => {
    if (onFormReady && form) {
      onFormReady(form);
    }
  }, [onFormReady, form]);

  // When showValidationErrors changes to true, re-validate to show errors
  useEffect(() => {
    if (showValidationErrors) {
      form.validateFields().catch(() => {
        // Errors will be shown on fields
      });
    }
  }, [showValidationErrors, form]);

  const handleFormChange = useCallback(
    (changedValues?: Partial<VaultFormValues>) => {
      const formData = form.getFieldsValue() as VaultFormValues;

      if (entityType === 'STORAGE' && changedValues?.provider !== undefined) {
        setSelectedProvider(
          typeof changedValues.provider === 'string' ? changedValues.provider : null
        );

        if (providerFields) {
          const currentValues = form.getFieldsValue();
          const newValues: Partial<VaultFormValues> = {};

          STORAGE_FIELDS_TO_KEEP.forEach((field) => {
            if (currentValues[field] !== undefined) {
              newValues[field] = currentValues[field];
            }
          });

          form.setFieldsValue(newValues);
        }
      }

      const encodedData: VaultFormValues = { ...formData };
      Object.entries(entityDef?.fields || {}).forEach(([key, field]) => {
        if (
          field.format === 'base64' &&
          encodedData[key] !== undefined &&
          typeof encodedData[key] === 'string'
        ) {
          encodedData[key] = encodeBase64(encodedData[key]);
        }
      });

      if (entityType === 'STORAGE' && selectedProvider && providerFields?.fields) {
        Object.entries(providerFields.fields).forEach(([key, field]) => {
          if (
            field.format === 'base64' &&
            encodedData[key] !== undefined &&
            typeof encodedData[key] === 'string'
          ) {
            encodedData[key] = encodeBase64(encodedData[key]);
          }
        });
      }

      const completeData: VaultFormValues = { ...encodedData };
      if (Object.keys(extraFields).length > 0) {
        completeData.extraFields = extraFields;
      }

      updateRawJson(completeData);

      const hasChanges = JSON.stringify(completeData) !== JSON.stringify(initialData);
      directOnChange(completeData, hasChanges);

      const validateOptions = showValidationErrors ? undefined : { validateOnly: true };

      form
        .validateFields(undefined, validateOptions)
        .then(() => {
          onValidate?.(true);
        })
        .catch((errorInfo: ValidateErrorEntity<VaultFormValues>) => {
          const errors = formatValidationErrors(errorInfo);
          onValidate?.(false, errors);

          if (!showValidationErrors) {
            form.getFieldsError().forEach(({ name }) => {
              form.setFields([{ name, errors: [] }]);
            });
          }
        });
    },
    [
      entityType,
      providerFields,
      form,
      selectedProvider,
      extraFields,
      initialData,
      updateRawJson,
      directOnChange,
      onValidate,
      entityDef,
      showValidationErrors,
    ]
  );

  return {
    // Form instance
    form,
    formGutter,

    // State
    extraFields,
    setExtraFields,
    importedData,
    setImportedData,
    rawJsonValue,
    setRawJsonValue,
    rawJsonError,
    setRawJsonError,
    selectedProvider,
    setSelectedProvider,
    testConnectionSuccess,
    setTestConnectionSuccess,
    osSetupCompleted,
    setOsSetupCompleted,
    formatJsonRef,

    // Test connection state
    testTaskId,
    setTestTaskId,
    isTestingConnection,
    setIsTestingConnection,
    isCreatingQueueItem,

    // Data
    entityDef,
    providerFields,
    teams,

    // Functions
    handleFormChange,
    updateRawJson,

    // API hooks
    createQueueItem,
    buildQueueVault,

    // Translation
    t,
  };
};
