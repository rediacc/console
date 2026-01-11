import { forwardRef, useCallback, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { Col, Divider, Flex, Form, Row, theme } from 'antd';
import { useTranslation } from 'react-i18next';
import VaultEditor from '@/components/common/VaultEditor';
import { FORM_LAYOUTS } from '@/config/formLayouts';
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
    const rowGutter = useMemo(
      (): [number, number] => [token.marginSM, token.marginSM],
      [token.marginSM]
    );
    const vaultDataRef = useRef<Record<string, unknown>>(initialVaultData);
    const [isVaultValid, setIsVaultValid] = useState(false);
    const [showVaultValidationErrors, setShowVaultValidationErrors] = useState(false);
    const importExportHandlers = useRef<ImportExportHandlers | null>(null);

    const handleFormSubmit = useCallback(async () => {
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
          vaultContent: JSON.stringify(vaultDataRef.current),
        };
        await onSubmit(dataWithVault);
      } catch {
        // Validation errors will be shown on form fields automatically
      }
    }, [entityType, form, isEditMode, isVaultValid, message, onSubmit]);

    const handleVaultChange = useCallback((data: Record<string, unknown>) => {
      vaultDataRef.current = data;
    }, []);

    const handleVaultValidate = useCallback((valid: boolean) => {
      setIsVaultValid(valid);
    }, []);

    const handleImport = useCallback((file: UploadFile) => {
      if (importExportHandlers.current) {
        return importExportHandlers.current.handleImport(file);
      }
      return false;
    }, []);

    const handleExport = useCallback(() => {
      importExportHandlers.current?.handleExport();
    }, []);

    const handleImportExport = useCallback(
      (handlers: ImportExportHandlers) => {
        importExportHandlers.current = handlers;
        onImportExportRef?.(handlers);
      },
      [onImportExportRef]
    );

    useImperativeHandle(
      ref,
      () => ({
        submit: handleFormSubmit,
      }),
      [handleFormSubmit]
    );

    return (
      <Flex vertical>
        <Form
          form={form}
          data-testid="resource-modal-form"
          {...FORM_LAYOUTS.horizontal}
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
          {beforeVaultContent}
        </Form>

        <Divider className="my-4">{t('vaultEditor.vaultConfiguration')}</Divider>

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
            onImportExport={handleImportExport}
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
