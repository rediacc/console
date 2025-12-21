import React, { useEffect, useRef, useState } from 'react';
import { Button, Flex, Modal, Space, Tag, Tooltip, Typography, Upload } from 'antd';
import { useTranslation } from 'react-i18next';
import VaultEditor from '@/components/common/VaultEditor';
import { useMessage } from '@/hooks';
import type { BaseModalProps } from '@/types';
import { ModalSize } from '@/types/modal';
import {
  CloseOutlined,
  DownloadOutlined,
  InfoCircleOutlined,
  SaveOutlined,
  UploadOutlined,
} from '@/utils/optimizedIcons';
import type { RcFile } from 'antd/es/upload';

interface VaultEditorModalProps extends BaseModalProps {
  onSave: (vault: string, version: number) => Promise<void>;
  entityType: string;
  title?: string;
  initialVault?: string;
  initialVersion?: number;
  loading?: boolean;
}

const VERSION_HINT_BULLET = '•';

const VaultEditorModal: React.FC<VaultEditorModalProps> = ({
  open,
  onCancel,
  onSave,
  entityType,
  title = 'Configure Vault',
  initialVault = '{}',
  initialVersion = 1,
  loading = false,
}) => {
  const { t } = useTranslation('common');
  const message = useMessage();
  const [vaultData, setVaultData] = useState<Record<string, unknown>>({});
  const [vaultVersion, setVaultVersion] = useState(initialVersion);
  const [isValid, setIsValid] = useState(true);
  const [hasChanges, setHasChanges] = useState(false);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [showValidationErrors, setShowValidationErrors] = useState(false);
  const importExportHandlers = useRef<{
    handleImport: (file: RcFile) => boolean;
    handleExport: () => void;
  } | null>(null);
  const validationErrorsRef = useRef<HTMLDivElement>(null);

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    try {
      const parsed = JSON.parse(initialVault);
      setVaultData(parsed);
    } catch {
      setVaultData({});
    }
    setVaultVersion(initialVersion);
    setHasChanges(false);
    setValidationErrors([]);
    setShowValidationErrors(false);
  }, [initialVault, initialVersion]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const handleVaultChange = (data: Record<string, unknown>, changed: boolean) => {
    setVaultData(data);
    setHasChanges(changed);
  };

  const handleValidate = (valid: boolean, errors?: string[]) => {
    setIsValid(valid);
    setValidationErrors(errors || []);
  };

  const handleSave = async () => {
    if (!isValid) {
      setShowValidationErrors(true);
      message.error('common:vaultEditor.pleaseFixErrors');
      return;
    }

    try {
      const vaultJson = JSON.stringify(vaultData);
      await onSave(vaultJson, vaultVersion);
      onCancel();
    } catch {
      // Parent handles notification
    }
  };

  useEffect(() => {
    if (showValidationErrors && validationErrorsRef.current) {
      validationErrorsRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      });
    }
  }, [showValidationErrors]);

  return (
    <Modal
      title={`${title} - ${entityType}`}
      open={open}
      onCancel={onCancel}
      className={ModalSize.Fullscreen}
      footer={null}
      data-testid="vault-modal"
      destroyOnClose
    >
      <Flex vertical gap={24} style={{ width: '100%' }}>
        <Flex align="center" justify="space-between">
          <Space size="small">
            <Typography.Text strong>{t('vaultEditor.vaultVersion')}</Typography.Text>
            <Tag color="processing">{vaultVersion}</Tag>
          </Space>
          <Typography.Text>{t('vaultEditor.versionAutoIncrement')}</Typography.Text>
        </Flex>

        {showValidationErrors && validationErrors.length > 0 && (
          <Flex vertical ref={validationErrorsRef} style={{ fontSize: 14 }}>
            <Flex style={{ display: 'block' }}>
              <Typography.Text strong>{t('vaultEditor.validationErrors')}</Typography.Text>
            </Flex>
            <ul style={{ display: 'flex', flexDirection: 'column' }}>
              {validationErrors.map((error, index) => (
                <li key={index}>{error}</li>
              ))}
            </ul>
          </Flex>
        )}

        <VaultEditor
          entityType={entityType}
          initialData={vaultData}
          onChange={handleVaultChange}
          onValidate={handleValidate}
          onImportExport={(handlers) => {
            importExportHandlers.current = handlers;
          }}
          onFieldMovement={(_movedToExtra, _movedFromExtra) => {
            // Parent can track movements if needed
          }}
          data-testid="vault-modal-editor"
        />
      </Flex>

      <Flex vertical>
        <Flex
          style={{
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
          }}
        >
          <Flex align="center" wrap>
            <Upload
              accept=".json"
              showUploadList={false}
              beforeUpload={(file) => {
                if (importExportHandlers.current) {
                  return importExportHandlers.current.handleImport(file);
                }
                return false;
              }}
              data-testid="vault-modal-file-upload"
            >
              <Button
                icon={<UploadOutlined style={{ fontSize: 12 }} />}
                data-testid="vault-modal-import-button"
              >
                {t('vaultEditor.importJson')}
              </Button>
            </Upload>
            <Button
              icon={<DownloadOutlined style={{ fontSize: 12 }} />}
              onClick={() => {
                if (importExportHandlers.current) {
                  importExportHandlers.current.handleExport();
                }
              }}
              data-testid="vault-modal-export-button"
            >
              {t('vaultEditor.exportJson')}
            </Button>
          </Flex>

          <Flex align="center" wrap>
            {hasChanges && (
              <>
                <Typography.Text style={{ display: 'flex', alignItems: 'center', fontSize: 12 }}>
                  <InfoCircleOutlined style={{ fontSize: 12 }} />
                  {t('vaultEditor.unsavedChanges')}
                </Typography.Text>
                <Typography.Text>
                  {VERSION_HINT_BULLET}{' '}
                  {t('vaultEditor.versionWillIncrement', { version: vaultVersion + 1 })}
                </Typography.Text>
              </>
            )}
            <Tooltip title={t('actions.cancel')}>
              <Button
                type="text"
                icon={<CloseOutlined />}
                onClick={onCancel}
                data-testid="vault-modal-cancel-button"
                aria-label={t('actions.cancel')}
              />
            </Tooltip>
            <Tooltip title={t('vaultEditor.saveVaultConfiguration')}>
              <Button
                type="text"
                icon={<SaveOutlined />}
                onClick={handleSave}
                loading={loading}
                disabled={!isValid}
                data-testid="vault-modal-save-button"
                aria-label={t('vaultEditor.saveVaultConfiguration')}
              />
            </Tooltip>
          </Flex>
        </Flex>
      </Flex>
    </Modal>
  );
};

export default VaultEditorModal;
