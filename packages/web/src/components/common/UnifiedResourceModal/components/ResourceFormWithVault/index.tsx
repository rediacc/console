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

const ResourceFormWithVault = forwardRef<ResourceFormWithVaultRef, ResourceFormWithVaultProps>(
  (
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
      uiMode = 'expert',
    },
    ref
  ) => {
    const { t } = useTranslation('common');
    const message = useMessage();
    const { token } = theme.useToken();
    const rowGutter: [number, number] = [token.marginSM, token.marginSM];
    const [vaultData, setVaultData] = useState<Record<string, unknown>>(initialVaultData);
    const [isVaultValid, setIsVaultValid] = useState(false);
    const [showVaultValidationErrors, setShowVaultValidationErrors] = useState(false);
    const importExportHandlers = useRef<ImportExportHandlers | null>(null);

    // Update vault field value when vault data changes
    useEffect(() => {
      form.setFieldValue(vaultFieldName, JSON.stringify(vaultData));
    }, [vaultData, form, vaultFieldName]);

    const handleFormSubmit = async () => {
      // Only skip vault validation in edit mode, not in create mode (including credentials-only)
      const shouldSkipVaultValidation = entityType === 'REPOSITORY' && isEditMode;

      if (!isVaultValid && !shouldSkipVaultValidation) {
        setShowVaultValidationErrors(true);
        message.error('common:vaultEditor.pleaseFixErrors');
        return;
      }

      try {
        // Validate all form fields
        const formData = await form.validateFields();
        const dataWithVault = {
          ...formData,
          [vaultFieldName]: JSON.stringify(vaultData),
        };
        await onSubmit(dataWithVault);
      } catch {
        // Validation errors will be shown on form fields automatically
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
      submit: handleFormSubmit,
    }));

    const formLayout = layout === 'vertical' ? 'horizontal' : layout;
    const labelCol = { span: 6 };
    const wrapperCol = { span: 18 };

    return (
      <Flex vertical>
        <Form
          form={form}
          data-testid="resource-modal-form"
          layout={formLayout}
          labelCol={labelCol}
          wrapperCol={wrapperCol}
          labelAlign="right"
          colon
          className="flex-shrink-0"
        >
          <Row gutter={rowGutter} wrap>
            {fields.map((field) => {
              if (field.hidden) return null;

              return (
                <Col key={field.name} xs={24} lg={12}>
                  <Form.Item
                    name={field.name}
                    label={field.label}
                    required={field.required}
                    rules={field.rules}
                    help={field.helperText}
                    data-testid={`resource-modal-field-${field.name}`}
                  >
                    <FieldRenderer field={field} />
                  </Form.Item>
                </Col>
              );
            })}
          </Row>
        </Form>

        {beforeVaultContent}

        {/* eslint-disable-next-line no-restricted-syntax */}
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

ResourceFormWithVault.displayName = 'ResourceFormWithVault';

export default ResourceFormWithVault;

export type {
  FormFieldConfig,
  ImportExportHandlers,
  ResourceFormWithVaultProps,
  ResourceFormWithVaultRef,
} from './types';
