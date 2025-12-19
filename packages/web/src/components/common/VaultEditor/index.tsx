import React, { useCallback } from 'react';
import { Alert } from 'antd';
import { useMessage } from '@/hooks';
import { useVaultEditorState } from './hooks/useVaultEditorState';
import {
  VaultEditorRequiredFields,
  VaultEditorOptionalFields,
  VaultEditorProviderFields,
  VaultEditorExtraFields,
  VaultEditorRawJson,
  VaultEditorTestConnection,
  VaultEditorSystemCompatibility,
} from './sections';
import { EditorContainer, EditorForm, FormRow, InfoBanner } from './styles';
import { handleImport, handleExport, handleRawJsonChange } from './utilities';
import type { VaultEditorProps, VaultFormValues } from './types';
import type { UploadFile } from 'antd/es/upload/interface';

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

  const onRawJsonChange = useCallback(
    (value: string | undefined) => {
      handleRawJsonChange(
        value,
        form,
        entityDef,
        extraFields,
        initialData,
        {
          setRawJsonValue,
          setRawJsonError,
          setExtraFields,
          setImportedData,
          directOnChange,
          onValidate,
          showFieldMovements: (movements) => {
            if (movements.movedToExtra.length > 0) {
              message.info('common:vaultEditor.fieldsMovedToExtra', {
                count: movements.movedToExtra.length,
                fields: movements.movedToExtra.join(', '),
              });
            }
            if (movements.movedFromExtra.length > 0) {
              message.success('common:vaultEditor.fieldsMovedFromExtra', {
                count: movements.movedFromExtra.length,
                fields: movements.movedFromExtra.join(', '),
              });
            }
          },
        },
        t
      );
    },
    [
      form,
      entityDef,
      extraFields,
      initialData,
      setRawJsonValue,
      setRawJsonError,
      setExtraFields,
      setImportedData,
      directOnChange,
      onValidate,
      message,
      t,
    ]
  );

  const onImport = useCallback(
    (file: UploadFile) => {
      return handleImport(file, entityDef, form, {
        setExtraFields,
        setImportedData,
        handleFormChange,
      });
    },
    [entityDef, form, setExtraFields, setImportedData, handleFormChange]
  );

  const onExport = useCallback(() => {
    handleExport(form, entityDef, extraFields, entityType);
  }, [form, entityDef, extraFields, entityType]);

  // Pass import/export handlers to parent
  React.useEffect(() => {
    if (onImportExport) {
      onImportExport({
        handleImport: onImport,
        handleExport: onExport,
      });
    }
  }, [onImportExport, onImport, onExport]);

  const handleTestConnection = useCallback(async () => {
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
        ip,
        user,
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
  }, [
    form,
    message,
    teams,
    teamName,
    bridgeName,
    buildQueueVault,
    createQueueItem,
    setTestTaskId,
    setIsTestingConnection,
  ]);

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
          {(requiredFields.length > 0 || optionalFields.length > 0) && (
            <>
              <VaultEditorRequiredFields
                entityType={entityType}
                requiredFields={requiredFields}
                fields={fields}
                isEditMode={isEditMode}
                selectedProvider={selectedProvider || undefined}
                form={form}
                handleFormChange={handleFormChange}
                t={t}
              />

              <VaultEditorOptionalFields
                entityType={entityType}
                requiredFields={requiredFields}
                optionalFields={optionalFields}
                fields={fields}
                selectedProvider={selectedProvider || undefined}
                form={form}
                handleFormChange={handleFormChange}
                t={t}
              />

              {entityType === 'MACHINE' && (
                <VaultEditorTestConnection
                  form={form}
                  testConnectionSuccess={testConnectionSuccess}
                  isCreatingQueueItem={isCreatingQueueItem}
                  isTestingConnection={isTestingConnection}
                  teamName={teamName}
                  bridgeName={bridgeName}
                  onTestConnection={handleTestConnection}
                  t={t}
                />
              )}

              {entityType === 'MACHINE' && (
                <VaultEditorSystemCompatibility form={form} osSetupCompleted={osSetupCompleted} t={t} />
              )}
            </>
          )}

          <VaultEditorProviderFields
            selectedProvider={selectedProvider || undefined}
            providerFields={providerFields || undefined}
            form={form}
            handleFormChange={handleFormChange}
            t={t}
          />

          <VaultEditorExtraFields extraFields={extraFields} uiMode={uiMode} t={t} />

          <VaultEditorRawJson
            rawJsonValue={rawJsonValue}
            rawJsonError={rawJsonError || undefined}
            uiMode={uiMode}
            onChange={onRawJsonChange}
            t={t}
          />
        </FormRow>
      </EditorForm>
    </EditorContainer>
  );
};

export default VaultEditor;
