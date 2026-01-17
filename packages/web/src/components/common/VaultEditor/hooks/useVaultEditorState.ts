import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Form, theme } from 'antd';
import { useTranslation } from 'react-i18next';
import { useGetOrganizationTeams } from '@/api/api-hooks.generated';
import { useCreateQueueItemWithValidation, useQueueItemTraceWithEnabled } from '@/api/hooks-queue';
import { useMessage } from '@/hooks';
import { useQueueVaultBuilder } from '@/hooks/useQueueVaultBuilder';
import { parseSshTestResult } from '@rediacc/shared/utils';
import type { SSHTestResult } from '@rediacc/shared/utils';
import { STORAGE_FIELDS_TO_KEEP, storageProviderConfig, vaultDefinitionConfig } from '../constants';
import { decodeBase64, encodeBase64, formatValidationErrors, processExtraFields } from '../utils';
import type {
  FieldDefinition,
  ValidateErrorEntity,
  VaultEditorProps,
  VaultFormValues,
} from '../types';
import type { FormInstance } from 'antd/es/form';

// Helper: Get storage provider fields if applicable
const getStorageProviderFields = (
  entityType: string,
  providerKey: unknown
): Record<string, FieldDefinition> | null => {
  if (entityType !== 'STORAGE' || !providerKey || typeof providerKey !== 'string') {
    return null;
  }
  // Check if provider key exists in config
  if (!(providerKey in storageProviderConfig.providers)) {
    return null;
  }
  const provider = storageProviderConfig.providers[providerKey];
  return provider.fields ?? null;
};

// Helper: Build schema fields array including storage provider fields
const buildSchemaFieldsList = (
  entityDef: { fields?: Record<string, FieldDefinition> },
  entityType: string,
  providerKey: unknown
): string[] => {
  const baseFields = Object.keys(entityDef.fields ?? {});
  const providerFields = getStorageProviderFields(entityType, providerKey);
  return providerFields ? [...baseFields, ...Object.keys(providerFields)] : baseFields;
};

// Helper: Process field value for form (handle base64 decoding)
const processFieldValue = (value: unknown, field: FieldDefinition): unknown => {
  if (field.format === 'base64' && typeof value === 'string') {
    return decodeBase64(value);
  }
  return value;
};

// Helper: Build form data from initial data and entity definition
const buildFormDataFromFields = (
  fields: Record<string, FieldDefinition>,
  sourceData: VaultFormValues
): VaultFormValues => {
  const formData: VaultFormValues = {};
  Object.entries(fields).forEach(([key, field]) => {
    if (sourceData[key] !== undefined) {
      formData[key] = processFieldValue(sourceData[key], field);
    } else if (field.default !== undefined) {
      formData[key] = field.default;
    }
  });
  return formData;
};

// Helper: Extract extras from initial data
const extractExtrasFromData = (
  initialData: VaultFormValues,
  schemaFields: string[]
): VaultFormValues => {
  const extras: VaultFormValues = {};

  if (initialData.extraFields && typeof initialData.extraFields === 'object') {
    Object.assign(extras, initialData.extraFields);
  }

  Object.entries(initialData).forEach(([key, value]) => {
    if (key !== 'extraFields' && !schemaFields.includes(key)) {
      extras[key] = value;
    }
  });

  return extras;
};

// Helper: Handle successful SSH test result
const handleSshTestSuccess = (
  result: SSHTestResult,
  form: FormInstance<VaultFormValues>,
  setSshKeyConfigured: (value: boolean) => void,
  setOsSetupCompleted: (value: boolean | null) => void,
  onOsSetupStatusChange: ((status: boolean) => void) | undefined,
  setTestConnectionSuccess: (value: boolean) => void,
  onTestConnectionStateChange: ((success: boolean) => void) | undefined,
  handleFormChange: (values: Partial<VaultFormValues>) => void
): void => {
  if (result.ssh_key_configured !== undefined) {
    form.setFieldValue('ssh_key_configured', result.ssh_key_configured);
    setSshKeyConfigured(result.ssh_key_configured);
  }

  if (result.known_hosts) {
    form.setFieldValue('known_hosts', result.known_hosts);
  }

  if (result.kernel_compatibility) {
    form.setFieldValue('kernel_compatibility', result.kernel_compatibility);
  }

  if (result.kernel_compatibility?.os_setup_completed !== undefined) {
    setOsSetupCompleted(result.kernel_compatibility.os_setup_completed);
    onOsSetupStatusChange?.(result.kernel_compatibility.os_setup_completed);
  }

  form.setFieldValue('ssh_password', '');
  setTestConnectionSuccess(true);
  onTestConnectionStateChange?.(true);

  handleFormChange({
    ssh_key_configured: result.ssh_key_configured,
    known_hosts: result.known_hosts,
    ssh_password: '',
  });
};

// Helper: Handle failed SSH test result
const handleSshTestFailure = (
  errorMessage: string | undefined,
  message: ReturnType<typeof useMessage>,
  setTestConnectionSuccess: (value: boolean) => void,
  onTestConnectionStateChange: ((success: boolean) => void) | undefined
): void => {
  message.error(errorMessage ?? 'common:vaultEditor.testConnection.failed');
  setTestConnectionSuccess(false);
  onTestConnectionStateChange?.(false);
};

// Helper: Check if initialization should proceed
const shouldInitializeForm = (currentDataString: string, lastInitializedData: string): boolean => {
  const wasNonEmpty = lastInitializedData && lastInitializedData !== '{}';
  const isNowEmpty = currentDataString === '{}';

  // Skip if data hasn't changed (unless transitioning from non-empty to empty)
  if (currentDataString === lastInitializedData && !(wasNonEmpty && isNowEmpty)) {
    return false;
  }
  return true;
};

// Helper: Initialize entity-specific state
const initializeEntityState = (
  entityType: string,
  formData: VaultFormValues,
  setSshKeyConfigured: (value: boolean) => void,
  setSelectedProvider: (value: string | null) => void
): void => {
  // Set SSH key configuration state for MACHINE/BRIDGE entities
  if (entityType === 'MACHINE' || entityType === 'BRIDGE') {
    const sshKeyValue = formData.ssh_key_configured;
    if (typeof sshKeyValue === 'boolean') {
      setSshKeyConfigured(sshKeyValue);
    }
  }

  // Set provider state for STORAGE entity
  if (entityType === 'STORAGE' && typeof formData.provider === 'string') {
    setSelectedProvider(formData.provider);
  }
};

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
  } = props;

  const { t } = useTranslation(['common', 'storageProviders']);
  const message = useMessage();
  const { token } = theme.useToken();
  const [form] = Form.useForm();
  const [extraFields, setExtraFields] = useState<VaultFormValues>({});
  const [importedData, setImportedData] = useState<VaultFormValues>(initialData);
  const [rawJsonValue, setRawJsonValue] = useState<string>(() => {
    return Object.keys(initialData).length > 0 ? JSON.stringify(initialData, null, 2) : '{}';
  });
  const [rawJsonError, setRawJsonError] = useState<string | null>(null);
  // State preserved for future SSH key configuration UI
  const [sshKeyConfigured, setSshKeyConfigured] = useState(false);
  void sshKeyConfigured;
  void setSshKeyConfigured;
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
  const [lastInitializedData, setLastInitializedData] = useState<string>('');
  const [testTaskId, setTestTaskId] = useState<string | null>(null);
  const [isTestingConnection, setIsTestingConnection] = useState(false);
  const [testConnectionSuccess, setTestConnectionSuccess] = useState(false);
  const [osSetupCompleted, setOsSetupCompleted] = useState<boolean | null>(null);
  const formatJsonRef = useRef<(() => void) | null>(null);
  const formGutter: [number, number] = [token.marginSM, token.marginSM];

  const { buildQueueVault } = useQueueVaultBuilder();
  const { mutate: createQueueItem, isPending: isCreatingQueueItem } =
    useCreateQueueItemWithValidation();
  const { data: testTraceData } = useQueueItemTraceWithEnabled(testTaskId, isTestingConnection);
  const { data: teams } = useGetOrganizationTeams();

  // Track previous modal open state
  const prevModalOpenRef = useRef(isModalOpen);
  const initialDataJson = useMemo(() => JSON.stringify(initialData), [initialData]);
  const stableInitialData = useMemo(() => initialData, [initialData]);

  // Get entity definition from JSON
  const entityDef = useMemo(() => {
    return vaultDefinitionConfig.entities[entityType];
  }, [entityType]);

  // Get provider-specific fields for STORAGE entity
  const providerFields = useMemo(() => {
    if (
      entityType === 'STORAGE' &&
      selectedProvider &&
      selectedProvider in storageProviderConfig.providers
    ) {
      return storageProviderConfig.providers[selectedProvider];
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
      setImportedData(stableInitialData);
      setRawJsonValue('{}');
      setRawJsonError(null);
      setSshKeyConfigured(false);
      setSelectedProvider(null);
      setTestConnectionSuccess(false);
    }
    prevModalOpenRef.current = isModalOpen;
  }, [isModalOpen, form, stableInitialData]);

  const importedDataString = useMemo(() => JSON.stringify(importedData), [importedData]);

  // Monitor SSH test results
  useEffect(() => {
    if (!testTraceData?.queueDetails) {
      return;
    }

    const status =
      testTraceData.queueDetails.status ??
      (testTraceData.queueDetails as { Status?: string }).Status;

    // Handle failure states
    if (status === 'FAILED' || status === 'CANCELLED') {
      handleSshTestFailure(
        undefined,
        message,
        setTestConnectionSuccess,
        onTestConnectionStateChange
      );
      setIsTestingConnection(false);
      setTestTaskId(null);
      return;
    }

    // Handle completed state
    if (status !== 'COMPLETED') {
      return;
    }

    try {
      const result = parseSshTestResult({
        responseVaultContent: testTraceData.responseVaultContent?.vaultContent ?? null,
        consoleOutput: testTraceData.summary?.consoleOutput ?? null,
      });

      if (!result) {
        return;
      }

      if (result.status === 'success') {
        message.success('common:vaultEditor.testConnection.success');
        handleSshTestSuccess(
          result,
          form,
          setSshKeyConfigured,
          setOsSetupCompleted,
          onOsSetupStatusChange,
          setTestConnectionSuccess,
          onTestConnectionStateChange,
          handleFormChange
        );
      } else {
        handleSshTestFailure(
          result.message,
          message,
          setTestConnectionSuccess,
          onTestConnectionStateChange
        );
      }
    } catch {
      handleSshTestFailure(
        undefined,
        message,
        setTestConnectionSuccess,
        onTestConnectionStateChange
      );
    } finally {
      setIsTestingConnection(false);
      setTestTaskId(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [testTraceData, form, message, onOsSetupStatusChange, onTestConnectionStateChange]);

  // Calculate extra fields not in schema
  useEffect(() => {
    // entityDef is always defined for known entity types, but we keep this guard
    // for defensive programming against future entity type additions
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- defensive guard
    if (!entityDef) return;

    const schemaFields = buildSchemaFieldsList(entityDef, entityType, importedData.provider);
    const { extras, movedToExtra, movedFromExtra } = processExtraFields(
      importedData,
      schemaFields,
      extraFields
    );

    const extrasString = JSON.stringify(extras);
    const currentExtrasString = JSON.stringify(extraFields);

    if (extrasString === currentExtrasString) {
      return;
    }

    setExtraFields(extras);

    const hasMovements = movedToExtra.length > 0 || movedFromExtra.length > 0;
    if (hasMovements) {
      onFieldMovement?.(movedToExtra, movedFromExtra);
    }

    showFieldMovementToasts(movedToExtra, movedFromExtra);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [importedDataString, entityDef, entityType, onFieldMovement, showFieldMovementToasts]);

  // Initialize form with data
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- defensive guard
    if (!entityDef) return;

    if (!shouldInitializeForm(initialDataJson, lastInitializedData)) {
      return;
    }

    // Build form data from entity definition fields
    const formData = buildFormDataFromFields(entityDef.fields ?? {}, stableInitialData);

    // Add storage provider fields if applicable
    const providerFields = getStorageProviderFields(entityType, stableInitialData.provider);
    if (providerFields) {
      Object.assign(formData, buildFormDataFromFields(providerFields, stableInitialData));
    }

    // Reset and populate form
    form.resetFields();
    form.setFieldsValue(formData);
    setSshKeyConfigured(false);
    setSelectedProvider(null);
    setRawJsonError(null);

    // Initialize entity-specific state
    initializeEntityState(entityType, formData, setSshKeyConfigured, setSelectedProvider);

    // Extract extras and build complete data
    const schemaFields = buildSchemaFieldsList(entityDef, entityType, stableInitialData.provider);
    const extras = extractExtrasFromData(stableInitialData, schemaFields);

    const completeData = { ...formData };
    if (Object.keys(extras).length > 0) {
      completeData.extraFields = extras;
    }

    updateRawJson(completeData);
    setLastInitializedData(initialDataJson);

    const validateOptions = showValidationErrors ? undefined : { validateOnly: true };
    form
      .validateFields(undefined, validateOptions)
      .then(() => {
        onValidate?.(true);
      })
      .catch((errorInfo: unknown) => {
        const errors = formatValidationErrors(errorInfo as ValidateErrorEntity<VaultFormValues>);
        onValidate?.(false, errors);
      });
  }, [
    form,
    entityDef,
    entityType,
    initialDataJson,
    updateRawJson,
    lastInitializedData,
    stableInitialData,
    onValidate,
    showValidationErrors,
  ]);

  // Pass form instance to parent when ready
  useEffect(() => {
    if (onFormReady) {
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
      Object.entries(entityDef.fields ?? {}).forEach(([key, field]) => {
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

      const hasChanges = JSON.stringify(completeData) !== initialDataJson;
      directOnChange(completeData, hasChanges);

      const validateOptions = showValidationErrors ? undefined : { validateOnly: true };

      form
        .validateFields(undefined, validateOptions)
        .then(() => {
          onValidate?.(true);
        })
        .catch((errorInfo: unknown) => {
          const errors = formatValidationErrors(errorInfo as ValidateErrorEntity<VaultFormValues>);
          onValidate?.(false, errors);
        });
    },
    [
      entityType,
      providerFields,
      form,
      selectedProvider,
      extraFields,
      initialDataJson,
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
