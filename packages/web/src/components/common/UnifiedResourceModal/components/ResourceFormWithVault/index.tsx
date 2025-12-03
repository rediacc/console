import {
  useState,
  useEffect,
  useRef,
  useImperativeHandle,
  forwardRef,
} from 'react'
import { message, Form, Row, Col } from 'antd'
import type { FieldValues } from 'react-hook-form'
import type { UploadFile } from 'antd/es/upload/interface'
import { useTranslation } from 'react-i18next'
import { useTheme as useStyledTheme } from 'styled-components'
import VaultEditor from '@/components/common/VaultEditor'
import {
  FormWrapper,
  StyledForm,
  SectionDivider,
  VaultSection,
} from './styles'
import type {
  ResourceFormWithVaultRef,
  ResourceFormWithVaultProps,
  ImportExportHandlers,
} from './types'
import { ImportExportControls } from './components/ImportExportControls'
import { DefaultsBanner } from './components/DefaultsBanner'
import { FieldRenderer } from './components/FieldRenderer'

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
    ref,
  ) {
    const { t } = useTranslation('common')
    const theme = useStyledTheme()
    const rowGutter: [number, number] = [theme.spacing.SM, theme.spacing.SM]
    const [vaultData, setVaultData] = useState<Record<string, unknown>>(initialVaultData)
    const [isVaultValid, setIsVaultValid] = useState(true)
    const [showVaultValidationErrors, setShowVaultValidationErrors] = useState(false)
    const importExportHandlers = useRef<ImportExportHandlers | null>(null)

    const {
      control,
      handleSubmit,
      formState: { errors, touchedFields, submitCount, isSubmitted },
      setValue,
    } = form

    useEffect(() => {
      setValue(vaultFieldName, JSON.stringify(vaultData))
    }, [vaultData, setValue, vaultFieldName])

    const handleFormSubmit = async (formData: FieldValues) => {
      const shouldSkipVaultValidation =
        entityType === 'REPOSITORY' && (creationContext === 'credentials-only' || isEditMode)

      if (!isVaultValid && !shouldSkipVaultValidation) {
        setShowVaultValidationErrors(true)
        message.error(t('vaultEditor.pleaseFixErrors'))
        return
      }

      try {
        const dataWithVault = {
          ...formData,
          [vaultFieldName]: JSON.stringify(vaultData),
        }
        await onSubmit(dataWithVault)
      } catch {
        // handled upstream
      }
    }

    const handleVaultChange = (data: Record<string, unknown>) => {
      setVaultData(data)
    }

    const handleVaultValidate = (valid: boolean) => {
      setIsVaultValid(valid)
    }

    const handleImport = (file: UploadFile) => {
      if (importExportHandlers.current) {
        return importExportHandlers.current.handleImport(file)
      }
      return false
    }

    const handleExport = () => {
      importExportHandlers.current?.handleExport()
    }

    useImperativeHandle(ref, () => ({
      submit: async () => {
        await handleSubmit(handleFormSubmit)()
      },
    }))

    const formLayout = layout === 'vertical' ? 'horizontal' : layout
    const labelCol = { span: 6 }
    const wrapperCol = { span: 18 }

    return (
      <FormWrapper>
        <StyledForm
          data-testid="resource-modal-form"
          layout={formLayout}
          labelCol={labelCol}
          wrapperCol={wrapperCol}
          labelAlign="right"
          colon
        >
          <Row gutter={rowGutter} wrap>
            {fields.map((field) => {
              if (field.hidden) return null

              const fieldName = field.name
              const fieldError = errors?.[fieldName]
              const isTouched = touchedFields?.[fieldName]

              const showError = Boolean(fieldError && (isTouched || submitCount > 0 || isSubmitted))
              const errorMessage = showError ? (fieldError?.message as string) : undefined

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
              )
            })}
          </Row>
        </StyledForm>

        {beforeVaultContent}

        <SectionDivider>{t('vaultEditor.vaultConfiguration')}</SectionDivider>

        <VaultSection data-testid="resource-modal-vault-editor-section">
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
              importExportHandlers.current = handlers
              onImportExportRef?.(handlers)
            }}
          />
        </VaultSection>

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
      </FormWrapper>
    )
  },
)

export default ResourceFormWithVault

export type {
  ResourceFormWithVaultRef,
  ResourceFormWithVaultProps,
  FormFieldConfig,
  ImportExportHandlers,
} from './types'
