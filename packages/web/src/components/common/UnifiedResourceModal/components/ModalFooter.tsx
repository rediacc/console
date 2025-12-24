import React from 'react';
import { Button, Checkbox, Flex, Space, Upload } from 'antd';
import type { ImportExportHandlers } from '@/components/common/UnifiedResourceModal/components/ResourceFormWithVault';
import { DownloadOutlined, UploadOutlined } from '@/utils/optimizedIcons';
import type { ResourceType } from '../types';
import type { TFunction } from 'i18next';

interface ModalFooterProps {
  mode: 'create' | 'edit' | 'vault';
  resourceType: ResourceType;
  uiMode: 'simple' | 'expert';
  isSubmitting: boolean;
  testConnectionSuccess: boolean;
  autoSetupEnabled: boolean;
  setAutoSetupEnabled: (enabled: boolean) => void;
  existingData?: Record<string, unknown>;
  showFunctions: boolean;
  onCancel: () => void;
  onUpdateVault?: (vault: string, version: number) => Promise<void>;
  onVaultOpen: () => void;
  onFunctionOpen: () => void;
  onSubmit: () => void;
  importExportHandlers: React.RefObject<ImportExportHandlers | null>;
  t: TFunction;
}

export const ModalFooter: React.FC<ModalFooterProps> = ({
  mode,
  resourceType,
  uiMode,
  isSubmitting,
  testConnectionSuccess,
  autoSetupEnabled,
  setAutoSetupEnabled,
  existingData,
  showFunctions,
  onCancel,
  onUpdateVault,
  onVaultOpen,
  onFunctionOpen,
  onSubmit,
  importExportHandlers,
  t,
}) => {
  return (
    <Flex align="center" justify="space-between" gap={16} key="footer-container">
      <Flex align="center" gap={8}>
        {mode === 'create' && uiMode === 'expert' && (
          <Space>
            <Upload
              data-testid="resource-modal-upload-json"
              accept=".json"
              showUploadList={false}
              beforeUpload={(file) => {
                if (importExportHandlers.current) {
                  return importExportHandlers.current.handleImport(file);
                }
                return false;
              }}
            >
              <Button data-testid="resource-modal-import-button" icon={<UploadOutlined />}>
                {t('common:vaultEditor.importJson')}
              </Button>
            </Upload>
            <Button
              data-testid="resource-modal-export-button"
              icon={<DownloadOutlined />}
              onClick={() => {
                if (importExportHandlers.current) {
                  importExportHandlers.current.handleExport();
                }
              }}
            >
              {t('common:vaultEditor.exportJson')}
            </Button>
          </Space>
        )}
      </Flex>
      <Flex align="center" gap={8}>
        {mode === 'create' && resourceType === 'machine' && (
          <Checkbox
            data-testid="resource-modal-auto-setup-checkbox"
            checked={autoSetupEnabled}
            onChange={(e) => setAutoSetupEnabled(e.target.checked)}
          >
            {t('machines:autoSetupAfterCreation')}
          </Checkbox>
        )}
        <Button data-testid="resource-modal-cancel-button" onClick={onCancel}>
          {t('general.cancel')}
        </Button>
        {mode === 'create' && existingData && onUpdateVault && (
          <Button data-testid="resource-modal-vault-button" onClick={onVaultOpen}>
            {t('general.vault')}
          </Button>
        )}
        {showFunctions && (
          <Button data-testid="resource-modal-functions-button" onClick={onFunctionOpen}>
            {t(`${resourceType}s.${resourceType}Functions`)}
          </Button>
        )}
        <Button
          data-testid="resource-modal-ok-button"
          loading={isSubmitting}
          disabled={mode === 'create' && resourceType === 'machine' && !testConnectionSuccess}
          onClick={onSubmit}
        >
          {mode === 'create' ? t('general.create') : t('general.save')}
        </Button>
      </Flex>
    </Flex>
  );
};
