import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { Col, Divider, Flex, Form, Row, theme } from 'antd';
import { useTranslation } from 'react-i18next';
import VaultEditor from '@/components/common/VaultEditor';
import { useMessage } from '@/hooks';
import { DefaultsBanner } from './components/DefaultsBanner';
import { FieldRenderer } from './components/FieldRenderer';
import { ImportExportControls } from './components/ImportExportControls';
import type {
  ImportExportHandlers,
  ResourceFormWithVaultProps,
  ResourceFormWithVaultRef,
} from './types';
import type { UploadFile } from 'antd/es/upload/interface';
import type { FieldValues } from 'react-hook-form';

const ResourceFormWithVault = forwardRef<ResourceFormWithVaultRef, ResourceFormWithVaultProps>(
  function ResourceFormWithVault(
    {
      form,
      fields,
      onSubmit,
      entityType,
      vaultFieldName,
      layout = 'vertical',
      showDefaultsAlert = false,
      defaultsContent,
      hideImportExport = false,
      onImportExportRef,
      initialVaultData = {},
      teamName,
      bridgeName,
      onTestConnectionStateChange,
      beforeVaultContent,
      afterVaultContent,
      isModalOpen,
      isEditMode = false,
      creationContext,
      uiMode = 'expert',
    },
    ref
  ) {
    const { t } = useTranslation('common');
    const message = useMessage();
    const { token } = theme.useToken();
    const rowGutter: [number, number] = [token.marginSM ?? 12, token.marginSM ?? 12];
    const [vaultData, setVaultData] = useState<Record<string, unknown>>(initialVaultData);
    const [isVaultValid, setIsVaultValid] = useState(true);
    const [showVaultValidationErrors, setShowVaultValidationErrors] = useState(false);
    const importExportHandlers = useRef<ImportExportHandlers | null>(null);

    const {
      control,
      handleSubmit,
      formState: { errors, touchedFields, submitCount, isSubmitted },
      setValue,
    } = form;

    useEffect(() => {
      setValue(vaultFieldName, JSON.stringify(vaultData));
    }, [vaultData, setValue, vaultFieldName]);

    const handleFormSubmit = async (formData: FieldValues) => {
      const shouldSkipVaultValidation =
        entityType === 'REPOSITORY' && (creationContext === 'credentials-only' || isEditMode);

      if (!isVaultValid && !shouldSkipVaultValidation) {
        setShowVaultValidationErrors(true);
        message.error('common:vaultEditor.pleaseFixErrors');
        return;
      }

      try {
        const dataWithVault = {
          ...formData,
          [vaultFieldName]: JSON.stringify(vaultData),
        };
        await onSubmit(dataWithVault);
      } catch {
        // handled upstream
      }
    };

    const handleVaultChange = (data: Record<string, unknown>) => {
      setVaultData(data);
    };

    const handleVaultValidate = (valid: boolean) => {
      setIsVaultValid(valid);
    };

    const handleImport = (file: UploadFile) => {
      if (importExportHandlers.current) {
        return importExportHandlers.current.handleImport(file);
      }
      return false;
    };

    const handleExport = () => {
      importExportHandlers.current?.handleExport();
    };

    useImperativeHandle(ref, () => ({
      submit: async () => {
        await handleSubmit(handleFormSubmit)();
      },
    }));

    const formLayout = layout === 'vertical' ? 'horizontal' : layout;
    const labelCol = { span: 6 };
    const wrapperCol = { span: 18 };

    return (
      <Flex vertical>
        <Form
          data-testid="resource-modal-form"
          layout={formLayout}
          labelCol={labelCol}
          wrapperCol={wrapperCol}
          labelAlign="right"
          colon
          style={{ flexShrink: 0 }}
        >
          <Row gutter={rowGutter} wrap>
            {fields.map((field) => {
              if (field.hidden) return null;

              const fieldName = field.name;
              const fieldError = errors?.[fieldName];
              const isTouched = touchedFields?.[fieldName];

              const showError = Boolean(
                fieldError && (isTouched || submitCount > 0 || isSubmitted)
              );
              const errorMessage = showError ? (fieldError?.message as string) : undefined;

              return (
                <Col key={field.name} xs={24} lg={12}>
                  <Form.Item
                    label={field.label}
                    required={field.required}
                    validateStatus={showError ? 'error' : undefined}
                    help={errorMessage || field.helperText}
                    data-testid={`resource-modal-field-${field.name}`}
                  >
                    <FieldRenderer field={field} control={control} />
                  </Form.Item>
                </Col>
              );
            })}
          </Row>
        </Form>

        {beforeVaultContent}

        <Divider style={{ margin: '16px 0' }}>{t('vaultEditor.vaultConfiguration')}</Divider>

        <Flex data-testid="resource-modal-vault-editor-section">
          <VaultEditor
            entityType={entityType}
            initialData={initialVaultData}
            onChange={handleVaultChange}
            onValidate={handleVaultValidate}
            showValidationErrors={showVaultValidationErrors}
            teamName={teamName}
            bridgeName={bridgeName}
            onTestConnectionStateChange={onTestConnectionStateChange}
            isModalOpen={isModalOpen}
            isEditMode={isEditMode}
            uiMode={uiMode}
            onImportExport={(handlers) => {
              importExportHandlers.current = handlers;
              onImportExportRef?.(handlers);
            }}
          />
        </Flex>

        {afterVaultContent}

        {!hideImportExport && (
          <ImportExportControls
            importLabel={t('vaultEditor.importJson')}
            exportLabel={t('vaultEditor.exportJson')}
            onImport={handleImport}
            onExport={handleExport}
          />
        )}

        {showDefaultsAlert && defaultsContent && (
          <DefaultsBanner title={t('general.defaultsApplied')} content={defaultsContent} />
        )}
      </Flex>
    );
  }
);

export default ResourceFormWithVault;

export type {
  FormFieldConfig,
  ImportExportHandlers,
  ResourceFormWithVaultProps,
  ResourceFormWithVaultRef,
} from './types';
