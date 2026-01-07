import React, { useCallback } from 'react';
import { Alert, Flex, Form, Row } from 'antd';
import { FORM_LAYOUTS } from '@/config/formLayouts';
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
import {
  handleImport,
  handleExport,
  handleRawJsonChange,
  type FieldMovements,
} from './utils/index';
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
    teamName = 'Private Team',
    bridgeName = 'Global Bridges',
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
          showFieldMovements: (movements: FieldMovements) => {
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
        ssh_password: ssh_password ?? '',
        port: port ?? 22,
        datastore: datastore ?? '',
      });

      const teamData = teams?.find((team) => team.teamName === teamName);
      const teamVaultData = teamData?.vaultContent ?? '{}';

      const queueVault = await buildQueueVault({
        teamName,
        machineName: '',
        bridgeName,
        functionName: 'machine_ssh_test',
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
            if (response.taskId) {
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

  const requiredFields = entityDef.required ?? [];
  const optionalFields = entityDef.optional ?? [];
  const fields = entityDef.fields ?? {};

  return (
    <Flex vertical>
      {uiMode !== 'simple' && (
        <Alert message={t(`vaultEditor.${entityDef.descriptionKey}`)} type="info" />
      )}

      {/* Warning for TEAM vault without SSH keys */}
      {entityType === 'TEAM' && (!initialData.SSH_PRIVATE_KEY || !initialData.SSH_PUBLIC_KEY) && (
        <Alert
          message={t('vaultEditor.missingSshKeysWarning')}
          description={t('vaultEditor.missingSshKeysDescription')}
          type="warning"
        />
      )}

      <Form
        form={form}
        {...FORM_LAYOUTS.responsiveHorizontal}
        labelAlign="right"
        colon
        validateTrigger={false}
        preserve={false}
        onValuesChange={(changedValues, _allValues) => {
          handleFormChange(changedValues);
        }}
        autoComplete="off"
        className="vault-editor-form"
        data-testid="vault-editor-form"
      >
        <Row gutter={formGutter} wrap data-testid="vault-editor-cards">
          {(requiredFields.length > 0 || optionalFields.length > 0) && (
            <>
              <VaultEditorRequiredFields
                entityType={entityType}
                requiredFields={requiredFields}
                fields={fields}
                isEditMode={isEditMode}
                selectedProvider={selectedProvider ?? undefined}
                form={form}
                handleFormChange={handleFormChange}
                t={t}
              />

              <VaultEditorOptionalFields
                entityType={entityType}
                requiredFields={requiredFields}
                optionalFields={optionalFields}
                fields={fields}
                selectedProvider={selectedProvider ?? undefined}
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
                <VaultEditorSystemCompatibility
                  form={form}
                  osSetupCompleted={osSetupCompleted}
                  t={t}
                />
              )}
            </>
          )}

          <VaultEditorProviderFields
            selectedProvider={selectedProvider ?? undefined}
            providerFields={providerFields ?? undefined}
            form={form}
            handleFormChange={handleFormChange}
            t={t}
          />

          <VaultEditorExtraFields extraFields={extraFields} uiMode={uiMode} t={t} />

          <VaultEditorRawJson
            rawJsonValue={rawJsonValue}
            rawJsonError={rawJsonError ?? undefined}
            onChange={onRawJsonChange}
            t={t}
          />
        </Row>
      </Form>
    </Flex>
  );
};

export default VaultEditor;
