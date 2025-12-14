import React, { type JSX, useCallback } from 'react';
import { Alert, Card, Col, Descriptions, Divider, Form, Space } from 'antd';
import {
  RediaccAlert,
  RediaccStack,
  RediaccSwitch,
  RediaccTag,
  RediaccText,
  RediaccTooltip,
} from '@/components/ui';
import {
  RediaccInput,
  RediaccInputNumber,
  RediaccOption,
  RediaccPasswordInput,
  RediaccSelect,
  RediaccTextArea,
} from '@/components/ui/Form';
import { featureFlags } from '@/config/featureFlags';
import { useMessage } from '@/hooks';
import {
  CheckCircleOutlined,
  CodeOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  QuestionCircleOutlined,
  WarningOutlined,
  WifiOutlined,
} from '@/utils/optimizedIcons';
import { FieldFormItem } from './components/FieldFormItem';
import FieldGenerator from './components/FieldGenerator';
import { FieldLabel } from './components/FieldLabel';
import { NestedObjectEditor } from './components/NestedObjectEditor';
import { SimpleJsonEditor } from './components/SimpleJsonEditor';
import { MACHINE_BASIC_FIELD_ORDER, vaultDefinitionConfig } from './constants';
import { useVaultEditorState } from './hooks/useVaultEditorState';
import {
  CompatibilityStatusText,
  DangerAlertIcon,
  EditorContainer,
  EditorForm,
  ExtraFieldsWarningIcon,
  FieldDivider,
  FieldItem,
  FormatActions,
  FormatButton,
  FormRow,
  InfoBanner,
  IssueList,
  ListSection,
  ProviderSectionSpacer,
  RawJsonPreview,
  RecommendationList,
  TestConnectionAlert,
  TestConnectionButton,
  TipsAlert,
  TipsDividerIcon,
} from './styles';
import {
  buildValidationRules,
  decodeBase64,
  encodeBase64,
  getFieldDefinition,
  getJsonFieldProps,
} from './utils';
import type { FieldDefinition, VaultEditorProps, VaultFormValues } from './types';
import type { UploadFile } from 'antd/es/upload/interface';

type NestedFieldDefinition = React.ComponentProps<typeof NestedObjectEditor>['fieldDefinition'];

const VaultEditor: React.FC<VaultEditorProps> = (props) => {
  const {
    entityType,
    initialData = {},
    onChange,
    onValidate,
    onImportExport,
    isEditMode = false,
    uiMode = 'expert',
    teamName = 'Default Team',
    bridgeName = 'Default Bridge',
  } = props;

  // Use the custom hook for state management
  const {
    form,
    formGutter,
    extraFields,
    setExtraFields,
    setImportedData,
    rawJsonValue,
    setRawJsonValue,
    rawJsonError,
    setRawJsonError,
    selectedProvider,
    testConnectionSuccess,
    osSetupCompleted,
    formatJsonRef,
    setTestTaskId,
    isTestingConnection,
    setIsTestingConnection,
    isCreatingQueueItem,
    entityDef,
    providerFields,
    teams,
    handleFormChange,
    createQueueItem,
    buildQueueVault,
    t,
  } = useVaultEditorState(props);

  const message = useMessage();

  // Direct onChange callback
  const directOnChange = useCallback(
    (data: VaultFormValues, hasChanges: boolean) => {
      onChange?.(data, hasChanges);
    },
    [onChange]
  );

  const handleRawJsonChange = (value: string | undefined) => {
    if (!value) return;

    // Update the raw JSON value immediately to preserve user input
    setRawJsonValue(value);

    try {
      const parsed = JSON.parse(value);
      setRawJsonError(null);

      // Update form with known fields
      const formData: VaultFormValues = {};
      const extras: VaultFormValues = {};
      const movedToExtra: string[] = [];
      const movedFromExtra: string[] = [];

      // First, check if there's an extraFields property
      if (parsed.extraFields && typeof parsed.extraFields === 'object') {
        Object.assign(extras, parsed.extraFields);
      }

      // Process all fields
      Object.entries(parsed).forEach(([key, val]) => {
        if (key === 'extraFields') {
          // Skip, already processed
        } else if (entityDef.fields && key in entityDef.fields) {
          const field = (entityDef.fields as Record<string, FieldDefinition>)[key];
          // Decode base64 fields when loading from raw JSON
          if (field.format === 'base64' && typeof val === 'string') {
            formData[key] = decodeBase64(val);
          } else {
            formData[key] = val;
          }
          // Check if this field was previously in extraFields
          if (extraFields[key] !== undefined) {
            movedFromExtra.push(key);
          }
        } else {
          // Non-schema fields at root level also go to extras
          extras[key] = val;
          // Check if this is a new field being moved to extraFields
          if (!extraFields[key] && val !== undefined) {
            movedToExtra.push(key);
          }
        }
      });

      // Check for fields that were in extraFields but are now removed
      Object.keys(extraFields).forEach((key) => {
        if (!extras[key] && !formData[key]) {
          // Field was removed entirely, not moved
        }
      });

      form.setFieldsValue(formData);
      setExtraFields(extras);

      // Show toast messages for field movements
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

      // Encode base64 fields before saving
      const encodedData = { ...formData };
      Object.entries(entityDef?.fields || {}).forEach(([key, field]) => {
        const typedField = field as FieldDefinition;
        if (
          typedField.format === 'base64' &&
          encodedData[key] !== undefined &&
          typeof encodedData[key] === 'string'
        ) {
          encodedData[key] = encodeBase64(encodedData[key]);
        }
      });

      // Build complete data structure for onChange
      const completeData = { ...encodedData };
      if (Object.keys(extras).length > 0) {
        completeData.extraFields = extras;
      }

      setImportedData(completeData);

      // Trigger change event
      const hasChanges = JSON.stringify(completeData) !== JSON.stringify(initialData);
      directOnChange(completeData, hasChanges);

      // Don't validate here to avoid showing errors on raw JSON edit
      // Parent will validate when user submits
      onValidate?.(true);
    } catch {
      setRawJsonError(t('vaultEditor.invalidJsonFormat'));
    }
  };

  const handleImport = useCallback(
    (file: UploadFile) => {
      if (!entityDef) {
        return false;
      }
      const reader = new FileReader();
      reader.onload = (e: ProgressEvent<FileReader>) => {
        try {
          const data = JSON.parse((e.target?.result as string) || '{}') as VaultFormValues;

          // Extract extra fields from imported data
          const extras: VaultFormValues = {};
          const schemaFields = Object.keys(entityDef.fields || {});

          // Check for extraFields structure
          if (data.extraFields && typeof data.extraFields === 'object') {
            Object.assign(extras, data.extraFields as Record<string, unknown>);
          }

          // Check for non-schema fields at root
          Object.entries(data).forEach(([key, value]) => {
            if (key !== 'extraFields' && !schemaFields.includes(key)) {
              extras[key] = value;
            }
          });

          setExtraFields(extras);
          setImportedData(data);

          // Set form values for known fields
          const formData: VaultFormValues = {};
          Object.entries(entityDef.fields || {}).forEach(([key, field]) => {
            const typedField = field as FieldDefinition;
            if (data[key] !== undefined) {
              // Decode base64 fields when importing
              if (typedField.format === 'base64' && typeof data[key] === 'string') {
                formData[key] = decodeBase64(data[key] as string);
              } else {
                formData[key] = data[key];
              }
            }
          });
          form.setFieldsValue(formData);

          // Manually trigger change after import (no delay)
          handleFormChange();
        } catch {
          // Failed to parse JSON file
        }
      };
      const fileSource: Blob = file.originFileObj ?? (file as unknown as Blob);
      reader.readAsText(fileSource);
      return false;
    },
    [entityDef, form, handleFormChange, setExtraFields, setImportedData]
  );

  const handleExport = useCallback(() => {
    const formData = form.getFieldsValue() as VaultFormValues;

    // Encode base64 fields before exporting
    const encodedData: VaultFormValues = { ...formData };
    Object.entries(entityDef?.fields || {}).forEach(([key, field]) => {
      const typedField = field as FieldDefinition;
      if (
        typedField.format === 'base64' &&
        encodedData[key] !== undefined &&
        typeof encodedData[key] === 'string'
      ) {
        encodedData[key] = encodeBase64(encodedData[key]);
      }
    });

    // Build export data with extraFields structure
    const exportData: VaultFormValues = { ...encodedData };
    if (Object.keys(extraFields).length > 0) {
      exportData.extraFields = extraFields;
    }

    // Remove undefined values
    Object.keys(exportData).forEach((key) => {
      if (exportData[key] === undefined) {
        delete exportData[key];
      }
    });

    const dataStr = JSON.stringify(exportData, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${entityType.toLowerCase()}_vault_${Date.now()}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [form, entityDef, extraFields, entityType]);

  // Pass import/export handlers to parent
  React.useEffect(() => {
    if (onImportExport) {
      onImportExport({
        handleImport,
        handleExport,
      });
    }
  }, [onImportExport, handleImport, handleExport]);

  const renderField = (
    fieldName: string,
    fieldDef: FieldDefinition,
    required: boolean,
    isProviderField: boolean = false
  ) => {
    // Note: We no longer hide ssh_password field based on state alone
    // It will be conditionally rendered using Form.Item dependencies

    // Merge with common types if applicable
    const field = getFieldDefinition(fieldDef, vaultDefinitionConfig);

    // Get translated field label and description
    let fieldLabel: string;
    let fieldDescription: string | undefined;
    let fieldPlaceholder: string | undefined;
    let fieldHelpText: string | undefined;

    if (entityType === 'STORAGE' && isProviderField && selectedProvider) {
      // Use storage provider translations
      fieldLabel = t(
        `storageProviders:storageProviders.${selectedProvider}.fields.${fieldName}.label`,
        { defaultValue: fieldName }
      );
      fieldPlaceholder = t(
        `storageProviders:storageProviders.${selectedProvider}.fields.${fieldName}.placeholder`,
        { defaultValue: field.example }
      );
      fieldHelpText = t(
        `storageProviders:storageProviders.${selectedProvider}.fields.${fieldName}.helpText`,
        { defaultValue: field.description }
      );
      fieldDescription = fieldHelpText;
    } else {
      // Use regular vault editor translations
      fieldLabel = t(`vaultEditor.fields.${entityType}.${fieldName}.label`, {
        defaultValue: fieldName,
      });
      fieldDescription = t(`vaultEditor.fields.${entityType}.${fieldName}.description`);
      fieldPlaceholder = field.example;
    }

    // Build validation rules (ssh_password field handles its own dynamic rules)
    const rules = buildValidationRules(field, required, fieldLabel, t);

    const commonProps = {
      placeholder: fieldPlaceholder,
    };

    // Render based on type using helper components
    if (field.type === 'boolean') {
      // Default Switch for boolean fields
      return (
        <FieldFormItem
          name={fieldName}
          label={fieldLabel}
          description={fieldDescription}
          initialValue={field.default}
          valuePropName="checked"
        >
          <RediaccSwitch data-testid={`vault-editor-field-${fieldName}`} />
        </FieldFormItem>
      );
    }

    if (field.enum) {
      return (
        <FieldFormItem
          name={fieldName}
          label={fieldLabel}
          description={fieldDescription}
          rules={rules}
          initialValue={field.default}
        >
          <RediaccSelect fullWidth {...commonProps} data-testid={`vault-editor-field-${fieldName}`}>
            {field.enum.map((option) => (
              <RediaccOption key={option} value={option}>
                {option}
              </RediaccOption>
            ))}
          </RediaccSelect>
        </FieldFormItem>
      );
    }

    if (field.type === 'number') {
      return (
        <FieldItem
          name={fieldName}
          label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
          rules={rules}
          initialValue={field.default}
        >
          <RediaccInputNumber
            fullWidth
            {...commonProps}
            min={field.minimum}
            max={field.maximum}
            data-testid={`vault-editor-field-${fieldName}`}
          />
        </FieldItem>
      );
    }

    if (field.type === 'object') {
      // Check if this object has specific structure definition
      const hasStructure =
        field.properties ||
        (field.additionalProperties && typeof field.additionalProperties === 'object');

      if (hasStructure) {
        // Use NestedObjectEditor for complex objects with defined structure
        return (
          <FieldItem
            name={fieldName}
            label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
            rules={rules}
          >
            <NestedObjectEditor
              fieldDefinition={field as NestedFieldDefinition}
              title={fieldLabel}
              description={fieldDescription}
              data-testid={`vault-editor-field-${fieldName}`}
            />
          </FieldItem>
        );
      } else {
        // Use JSON editor for generic objects
        const { validator, getValueFromEvent, getValueProps } = getJsonFieldProps(false, t);
        return (
          <FieldItem
            name={fieldName}
            label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
            rules={[...rules, { validator }]}
            getValueFromEvent={getValueFromEvent}
            getValueProps={getValueProps}
          >
            <RediaccTextArea
              fullWidth
              {...commonProps}
              rows={4}
              placeholder={
                field.example
                  ? `${t('vaultEditor.example')} ${JSON.stringify(field.example, null, 2)}`
                  : t('vaultEditor.enterJsonObject')
              }
              data-testid={`vault-editor-field-${fieldName}`}
            />
          </FieldItem>
        );
      }
    }

    if (field.type === 'array') {
      const { validator, getValueFromEvent, getValueProps } = getJsonFieldProps(true, t);
      return (
        <FieldItem
          name={fieldName}
          label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
          rules={[...rules, { validator }]}
          getValueFromEvent={getValueFromEvent}
          getValueProps={getValueProps}
        >
          <RediaccTextArea
            fullWidth
            {...commonProps}
            rows={4}
            placeholder={
              field.example
                ? `${t('vaultEditor.example')} ${JSON.stringify(field.example, null, 2)}`
                : t('vaultEditor.enterJsonArray')
            }
            data-testid={`vault-editor-field-${fieldName}`}
          />
        </FieldItem>
      );
    }

    if (fieldName === 'ssh_password') {
      return (
        <FieldItem
          name={fieldName}
          label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
          rules={rules}
          initialValue={field.default}
        >
          <RediaccPasswordInput
            fullWidth
            {...commonProps}
            autoComplete="new-password"
            data-testid={`vault-editor-field-${fieldName}`}
            placeholder={t('vaultEditor.sshPasswordPlaceholder')}
          />
        </FieldItem>
      );
    }

    if (fieldName === 'host_entry') {
      return (
        <FieldItem
          name={fieldName}
          label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
          rules={rules}
          initialValue={field.default}
          extra={t('vaultEditor.hostEntryHelp')}
        >
          <RediaccInput
            fullWidth
            {...commonProps}
            data-testid={`vault-editor-field-${fieldName}`}
            placeholder={t('vaultEditor.hostEntryPlaceholder')}
          />
        </FieldItem>
      );
    }

    // Special handling for port type
    if (fieldName === 'port' || field.format === 'port') {
      return (
        <FieldFormItem
          name={fieldName}
          label={fieldLabel}
          description={fieldDescription}
          rules={rules}
          initialValue={field.default}
        >
          <RediaccInputNumber
            fullWidth
            {...commonProps}
            min={1}
            max={65535}
            placeholder={t('vaultEditor.portPlaceholder')}
            data-testid={`vault-editor-field-${fieldName}`}
          />
        </FieldFormItem>
      );
    }

    // Check if this field can be generated
    const isGeneratable =
      fieldName === 'SSH_PRIVATE_KEY' ||
      fieldName === 'SSH_PUBLIC_KEY' ||
      (fieldName === 'credential' && entityType === 'REPOSITORY');

    const handleFieldGeneration = (values: Record<string, string>) => {
      // For SSH keys, we need to update both private and public keys
      if (fieldName === 'SSH_PRIVATE_KEY' || fieldName === 'SSH_PUBLIC_KEY') {
        const currentValues = form.getFieldsValue();
        form.setFieldsValue({
          ...currentValues,
          SSH_PRIVATE_KEY: values.SSH_PRIVATE_KEY,
          SSH_PUBLIC_KEY: values.SSH_PUBLIC_KEY,
        });
        // Call handleFormChange immediately (no delay)
        handleFormChange({
          SSH_PRIVATE_KEY: values.SSH_PRIVATE_KEY,
          SSH_PUBLIC_KEY: values.SSH_PUBLIC_KEY,
        });
      } else {
        // For single field generation
        form.setFieldValue(fieldName, values[fieldName]);
        // Call handleFormChange immediately (no delay)
        handleFormChange({ [fieldName]: values[fieldName] });
      }
    };

    // Default to text input
    return (
      <FieldItem
        name={fieldName}
        label={<FieldLabel label={fieldLabel} description={fieldDescription} />}
        rules={rules}
        initialValue={field.default}
      >
        <RediaccInput
          fullWidth
          {...commonProps}
          type={field.sensitive ? 'password' : 'text'}
          autoComplete={field.sensitive ? 'new-password' : 'off'}
          data-testid={`vault-editor-field-${fieldName}`}
          addonAfter={
            isGeneratable ? (
              <FieldGenerator
                fieldType={fieldName === 'credential' ? 'repo_credential' : 'ssh_keys'}
                onGenerate={handleFieldGeneration}
                entityType={entityType}
                data-testid={`vault-editor-generate-${fieldName}`}
              />
            ) : undefined
          }
        />
      </FieldItem>
    );
  };

  if (!entityDef) {
    return (
      <Alert
        message={t('vaultEditor.unknownEntityType')}
        description={t('vaultEditor.unknownEntityDescription', { type: entityType })}
        type="error"
        showIcon
      />
    );
  }

  const requiredFields = entityDef.required || [];
  const optionalFields = entityDef.optional || [];
  const fields = entityDef.fields || {};

  return (
    <EditorContainer>
      {uiMode !== 'simple' && (
        <InfoBanner
          message={t(`vaultEditor.${entityDef.descriptionKey}`)}
          variant="info"
          showIcon
        />
      )}

      {/* Warning for TEAM vault without SSH keys */}
      {entityType === 'TEAM' && (!initialData.SSH_PRIVATE_KEY || !initialData.SSH_PUBLIC_KEY) && (
        <InfoBanner
          message={t('vaultEditor.missingSshKeysWarning')}
          description={t('vaultEditor.missingSshKeysDescription')}
          variant="warning"
          showIcon
        />
      )}

      <EditorForm
        form={form}
        layout="horizontal"
        labelCol={{ xs: { span: 24 }, sm: { span: 8 } }}
        wrapperCol={{ xs: { span: 24 }, sm: { span: 16 } }}
        labelAlign="right"
        colon={true}
        validateTrigger={false}
        preserve={false}
        onValuesChange={(changedValues, _allValues) => {
          handleFormChange(changedValues);
        }}
        autoComplete="off"
        className="vault-editor-form"
        data-testid="vault-editor-form"
      >
        <FormRow gutter={formGutter} wrap data-testid="vault-editor-cards">
          {/* Main Configuration - Merged Required & Optional Fields */}
          {(requiredFields.length > 0 || optionalFields.length > 0) && (
            <>
              {/* Required Fields */}
              {(entityType === 'MACHINE' ? MACHINE_BASIC_FIELD_ORDER : requiredFields).map(
                (fieldName) => {
                  const field = fields[fieldName as keyof typeof fields];
                  if (!field) return null;
                  const isRequired = !(
                    isEditMode &&
                    entityType === 'REPOSITORY' &&
                    fieldName === 'credential'
                  );
                  // credential field should be full width for REPOSITORY
                  const colSpan =
                    entityType === 'REPOSITORY' && fieldName === 'credential' ? 24 : 12;
                  return (
                    <Col key={fieldName} xs={24} md={colSpan}>
                      {renderField(fieldName, field as FieldDefinition, isRequired)}
                    </Col>
                  );
                }
              )}

              {/* Optional Fields (including ssh_password, port, host_entry) */}
              {entityType === 'MACHINE' &&
                optionalFields
                  .filter((fieldName) => fieldName !== 'ssh_key_configured')
                  .map((fieldName) => {
                    const field = fields[fieldName as keyof typeof fields];
                    if (!field) return null;
                    return (
                      <Col key={fieldName} xs={24} md={12}>
                        {renderField(fieldName, field as FieldDefinition, false)}
                      </Col>
                    );
                  })}

              {/* Test Connection Button */}
              {entityType === 'MACHINE' && (
                <Col xs={24}>
                  <FieldItem
                    label={
                      <FieldLabel
                        label={t('vaultEditor.testConnection.label')}
                        description={t('vaultEditor.testConnection.description')}
                      />
                    }
                  >
                    <RediaccStack direction="vertical" gap="sm" fullWidth>
                      {!testConnectionSuccess && (
                        <TestConnectionAlert
                          message={t('vaultEditor.testConnection.required')}
                          variant="info"
                          showIcon
                          icon={<InfoCircleOutlined />}
                          data-testid="vault-editor-connection-required-alert"
                        />
                      )}
                      <TestConnectionButton
                        variant="primary"
                        icon={<WifiOutlined />}
                        loading={isCreatingQueueItem || isTestingConnection}
                        data-testid="vault-editor-test-connection"
                        onClick={async () => {
                          // Validate form before testing connection
                          try {
                            await form.validateFields();
                          } catch {
                            message.error('common:vaultEditor.pleaseFixErrors');
                            return;
                          }

                          const values = form.getFieldsValue();
                          const { ip, user, ssh_password, port, datastore } = values;

                          if (!ip || !user) {
                            message.error('common:vaultEditor.testConnection.missingFields');
                            return;
                          }

                          try {
                            const testMachineVault = JSON.stringify({
                              ip: ip,
                              user: user,
                              ssh_password: ssh_password || '',
                              port: port || 22,
                              datastore: datastore || '',
                            });

                            const teamData = teams?.find((team) => team.teamName === teamName);
                            const teamVaultData = teamData?.vaultContent || '{}';

                            const queueVault = await buildQueueVault({
                              teamName,
                              machineName: '',
                              bridgeName,
                              functionName: 'ssh_test',
                              params: {},
                              priority: 1,
                              addedVia: 'vault-editor',
                              machineVault: testMachineVault,
                              teamVault: teamVaultData,
                            });

                            createQueueItem(
                              {
                                teamName,
                                bridgeName,
                                machineName: '',
                                queueVault,
                                priority: 1,
                              },
                              {
                                onSuccess: (response) => {
                                  if (response && response.taskId) {
                                    setTestTaskId(response.taskId);
                                    setIsTestingConnection(true);
                                    message.info('common:vaultEditor.testConnection.testing');
                                  } else {
                                    message.error('common:vaultEditor.testConnection.failed');
                                  }
                                },
                                onError: () => {
                                  message.error('common:vaultEditor.testConnection.failed');
                                },
                              }
                            );
                          } catch {
                            message.error('common:vaultEditor.testConnection.failed');
                          }
                        }}
                      >
                        {t('vaultEditor.testConnection.button')}
                      </TestConnectionButton>
                    </RediaccStack>
                  </FieldItem>
                </Col>
              )}

              {entityType === 'MACHINE' && form.getFieldValue('kernel_compatibility') && (
                <Col xs={24} lg={12}>
                  <FieldItem
                    label={
                      <RediaccText weight="bold">
                        {t('vaultEditor.systemCompatibility.title')}
                      </RediaccText>
                    }
                    colon={false}
                  >
                    {(() => {
                      const compatibility = form.getFieldValue('kernel_compatibility');
                      const status = compatibility.compatibility_status || 'unknown';
                      const osInfo = compatibility.os_info || {};

                      const statusConfig: Record<
                        string,
                        {
                          type: 'success' | 'warning' | 'error' | 'info';
                          icon: JSX.Element;
                          statusVariant: 'success' | 'warning' | 'error' | 'info';
                        }
                      > = {
                        compatible: {
                          type: 'success',
                          icon: <CheckCircleOutlined />,
                          statusVariant: 'success',
                        },
                        warning: {
                          type: 'warning',
                          icon: <WarningOutlined />,
                          statusVariant: 'warning',
                        },
                        incompatible: {
                          type: 'error',
                          icon: <ExclamationCircleOutlined />,
                          statusVariant: 'error',
                        },
                        unknown: {
                          type: 'info',
                          icon: <QuestionCircleOutlined />,
                          statusVariant: 'info',
                        },
                      };

                      const config = statusConfig[status] || statusConfig.unknown;

                      const sudoStatus = compatibility.sudo_available || 'unknown';
                      const sudoConfig: Record<string, { color: string; text: string }> = {
                        available: {
                          color: 'success',
                          text: t('vaultEditor.systemCompatibility.available'),
                        },
                        password_required: {
                          color: 'warning',
                          text: t('vaultEditor.systemCompatibility.passwordRequired'),
                        },
                        not_installed: {
                          color: 'error',
                          text: t('vaultEditor.systemCompatibility.notInstalled'),
                        },
                      };
                      const sudoConfigValue = sudoConfig[sudoStatus] || {
                        color: 'default',
                        text: t('vaultEditor.systemCompatibility.unknown'),
                      };

                      return (
                        <RediaccStack direction="vertical" gap="sm" fullWidth>
                          <Descriptions bordered size="small" column={1}>
                            <Descriptions.Item
                              label={t('vaultEditor.systemCompatibility.operatingSystem')}
                            >
                              {osInfo.pretty_name || t('vaultEditor.systemCompatibility.unknown')}
                            </Descriptions.Item>
                            <Descriptions.Item
                              label={t('vaultEditor.systemCompatibility.kernelVersion')}
                            >
                              {compatibility.kernel_version ||
                                t('vaultEditor.systemCompatibility.unknown')}
                            </Descriptions.Item>
                            <Descriptions.Item
                              label={t('vaultEditor.systemCompatibility.btrfsAvailable')}
                            >
                              {compatibility.btrfs_available ? (
                                <RediaccTag variant="success">
                                  {t('vaultEditor.systemCompatibility.yes')}
                                </RediaccTag>
                              ) : (
                                <RediaccTag variant="warning">
                                  {t('vaultEditor.systemCompatibility.no')}
                                </RediaccTag>
                              )}
                            </Descriptions.Item>
                            <Descriptions.Item
                              label={t('vaultEditor.systemCompatibility.sudoAvailable')}
                            >
                              <RediaccTag
                                variant={
                                  sudoConfigValue.color as
                                    | 'default'
                                    | 'success'
                                    | 'error'
                                    | 'warning'
                                    | 'primary'
                                }
                              >
                                {sudoConfigValue.text}
                              </RediaccTag>
                            </Descriptions.Item>
                            {osSetupCompleted !== null && (
                              <Descriptions.Item
                                label={t('vaultEditor.systemCompatibility.osSetup')}
                              >
                                <RediaccTag variant={osSetupCompleted ? 'success' : 'warning'}>
                                  {osSetupCompleted
                                    ? t('vaultEditor.systemCompatibility.setupCompleted')
                                    : t('vaultEditor.systemCompatibility.setupRequired')}
                                </RediaccTag>
                              </Descriptions.Item>
                            )}
                          </Descriptions>

                          <Alert
                            type={config.type}
                            icon={config.icon}
                            message={
                              <Space>
                                <RediaccText weight="bold">
                                  {t('vaultEditor.systemCompatibility.compatibilityStatus')}:
                                </RediaccText>
                                <CompatibilityStatusText $variant={config.statusVariant}>
                                  {t(`vaultEditor.systemCompatibility.${status}`)}
                                </CompatibilityStatusText>
                              </Space>
                            }
                            description={
                              <>
                                {compatibility.compatibility_issues &&
                                  compatibility.compatibility_issues.length > 0 && (
                                    <ListSection>
                                      <RediaccText weight="bold">
                                        {t('vaultEditor.systemCompatibility.knownIssues')}:
                                      </RediaccText>
                                      <IssueList>
                                        {compatibility.compatibility_issues.map(
                                          (issue: string, index: number) => (
                                            <li key={index}>{issue}</li>
                                          )
                                        )}
                                      </IssueList>
                                    </ListSection>
                                  )}
                                {compatibility.recommendations &&
                                  compatibility.recommendations.length > 0 && (
                                    <ListSection>
                                      <RediaccText weight="bold">
                                        {t('vaultEditor.systemCompatibility.recommendations')}:
                                      </RediaccText>
                                      <RecommendationList>
                                        {compatibility.recommendations.map(
                                          (rec: string, index: number) => (
                                            <li key={index}>{rec}</li>
                                          )
                                        )}
                                      </RecommendationList>
                                    </ListSection>
                                  )}
                              </>
                            }
                            showIcon
                          />
                        </RediaccStack>
                      );
                    })()}
                  </FieldItem>
                </Col>
              )}

              {entityType !== 'MACHINE' && (
                <>
                  {requiredFields.length > 0 && optionalFields.length > 0 && (
                    <FieldDivider>
                      <Divider />
                    </FieldDivider>
                  )}
                  {optionalFields.length > 0 &&
                    optionalFields.map((fieldName) => {
                      const field = fields[fieldName as keyof typeof fields];
                      if (!field) return null;

                      if (entityType === 'MACHINE' && fieldName === 'ssh_password') {
                        return (
                          <Col key={fieldName} xs={24} lg={12}>
                            <Form.Item
                              noStyle
                              shouldUpdate={(prevValues, currentValues) =>
                                prevValues.ssh_key_configured !== currentValues.ssh_key_configured
                              }
                            >
                              {({ getFieldValue }) => {
                                const sshKeyConfiguredValue = getFieldValue('ssh_key_configured');
                                if (sshKeyConfiguredValue) {
                                  return renderField(fieldName, field as FieldDefinition, false);
                                }
                                return null;
                              }}
                            </Form.Item>
                          </Col>
                        );
                      }

                      return (
                        <Col key={fieldName} xs={24} lg={12}>
                          {renderField(fieldName, field as FieldDefinition, false)}
                        </Col>
                      );
                    })}
                </>
              )}
            </>
          )}

          {/* Provider-specific fields Card for STORAGE entity */}
          {entityType === 'STORAGE' && selectedProvider && providerFields && (
            <Col xs={24} sm={24} md={24} lg={24} xl={24}>
              <Card
                title={t('vaultEditor.providerFields', { provider: providerFields.name })}
                variant="borderless"
                size="default"
                data-testid="vault-editor-panel-provider"
              >
                {/* Provider help text */}
                <RediaccAlert
                  spacing="default"
                  message={providerFields.name}
                  description={t(`storageProviders:storageProviders.${selectedProvider}.helpText`, {
                    defaultValue: providerFields.description,
                  })}
                  variant="info"
                  showIcon
                  icon={<QuestionCircleOutlined />}
                />

                {/* Required provider fields */}
                {providerFields.required && providerFields.required.length > 0 && (
                  <>
                    {providerFields.required.map((fieldName: string) => {
                      if (!providerFields.fields || !(fieldName in providerFields.fields))
                        return null;
                      const field =
                        providerFields.fields[fieldName as keyof typeof providerFields.fields];
                      if (!field) return null;
                      return (
                        <div key={fieldName}>
                          {renderField(fieldName, field as FieldDefinition, true, true)}
                        </div>
                      );
                    })}
                  </>
                )}

                {/* Optional provider fields */}
                {providerFields.optional && providerFields.optional.length > 0 && (
                  <>
                    {providerFields.required && providerFields.required.length > 0 && (
                      <ProviderSectionSpacer />
                    )}
                    {providerFields.optional.map((fieldName: string) => {
                      if (!providerFields.fields || !(fieldName in providerFields.fields))
                        return null;
                      const field =
                        providerFields.fields[fieldName as keyof typeof providerFields.fields];
                      if (!field) return null;
                      return (
                        <div key={fieldName}>
                          {renderField(fieldName, field as FieldDefinition, false, true)}
                        </div>
                      );
                    })}
                  </>
                )}

                {/* Provider-specific tips */}
                <Divider>
                  <Space>
                    <TipsDividerIcon />
                    <RediaccText weight="bold">
                      {t('storageProviders:common.tips', { defaultValue: 'Tips' })}
                    </RediaccText>
                  </Space>
                </Divider>
                <TipsAlert
                  message={
                    <RediaccStack direction="vertical" gap="sm" fullWidth>
                      {[1, 2, 3, 4]
                        .map((index) => {
                          const tip = t(
                            `storageProviders:storageProviders.${selectedProvider}.tips.${index - 1}`,
                            { defaultValue: '' }
                          );
                          return tip ? (
                            <div key={index}>
                              <RediaccText>- {tip}</RediaccText>
                            </div>
                          ) : null;
                        })
                        .filter(Boolean)}
                    </RediaccStack>
                  }
                  variant="info"
                  showIcon
                  icon={<InfoCircleOutlined />}
                />
              </Card>
            </Col>
          )}

          {/* Extra Fields Card - Only show in expert mode */}
          {Object.keys(extraFields).length > 0 && uiMode !== 'simple' && (
            <Col xs={24} sm={24} md={24} lg={24} xl={24}>
              <Card
                title={
                  <Space>
                    {t('vaultEditor.extraFields')}
                    <RediaccTooltip title={t('vaultEditor.extraFieldsTooltip')}>
                      <ExtraFieldsWarningIcon />
                    </RediaccTooltip>
                  </Space>
                }
                variant="borderless"
                size="default"
                data-testid="vault-editor-panel-extra"
              >
                <RediaccAlert
                  spacing="default"
                  message={t('vaultEditor.extraFieldsWarning')}
                  description={t('vaultEditor.extraFieldsWarningDescription')}
                  variant="warning"
                  showIcon
                />
                <Card size="small">
                  <RawJsonPreview>{JSON.stringify(extraFields, null, 2)}</RawJsonPreview>
                </Card>
              </Card>
            </Col>
          )}

          {/* Raw JSON Editor Card - Expert mode only */}
          {featureFlags.isEnabled('advancedVaultEditor') && uiMode !== 'simple' && (
            <Col xs={24} sm={24} md={24} lg={24} xl={24}>
              <Card
                title={
                  <Space>
                    <CodeOutlined />
                    {t('vaultEditor.rawJsonEditor')}
                    <RediaccTooltip title={t('vaultEditor.rawJsonTooltip')}>
                      <DangerAlertIcon />
                    </RediaccTooltip>
                  </Space>
                }
                variant="borderless"
                size="default"
                data-testid="vault-editor-panel-rawjson"
              >
                <RediaccAlert
                  spacing="default"
                  message={t('vaultEditor.expertModeOnly')}
                  description={t('vaultEditor.expertModeDescription')}
                  variant="error"
                  showIcon
                  icon={<DangerAlertIcon />}
                />

                {rawJsonError && (
                  <RediaccAlert
                    spacing="default"
                    message={t('vaultEditor.jsonError')}
                    description={rawJsonError}
                    variant="error"
                    showIcon
                  />
                )}

                <FormatActions>
                  <FormatButton
                    variant="default"
                    onClick={() => formatJsonRef.current?.()}
                    data-testid="vault-editor-format-json"
                  >
                    Format
                  </FormatButton>
                </FormatActions>

                <SimpleJsonEditor
                  value={rawJsonValue}
                  onChange={handleRawJsonChange}
                  height="400px"
                  data-testid="vault-editor-raw-json"
                  onFormatReady={(formatFn) => {
                    formatJsonRef.current = formatFn;
                  }}
                />
              </Card>
            </Col>
          )}
        </FormRow>
      </EditorForm>
    </EditorContainer>
  );
};

export default VaultEditor;
