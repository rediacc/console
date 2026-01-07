import React, { useEffect } from 'react';
import { Alert, Button, Flex, Form, Modal, Radio, Space, Typography, Upload } from 'antd';
import { ModalSize } from '@/types/modal';
import { UploadOutlined } from '@/utils/optimizedIcons';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';

interface ImportModalProps {
  t: TypedTFunction;
  open: boolean;
  onCancel: () => void;
  onSubmit: () => void;
  importFile: File | null;
  setImportFile: (file: File | null) => void;
  importMode: 'skip' | 'override';
  setImportMode: (mode: 'skip' | 'override') => void;
  isSubmitting: boolean;
}

export const ImportModal: React.FC<ImportModalProps> = ({
  t,
  open,
  onCancel,
  onSubmit,
  importFile,
  setImportFile,
  importMode,
  setImportMode,
  isSubmitting,
}) => {
  const [form] = Form.useForm();

  // Reset form when modal closes
  useEffect(() => {
    if (!open) {
      form.resetFields();
    }
  }, [open, form]);

  return (
    <Modal
      title={t('system:dangerZone.importData.modal.title')}
      open={open}
      onCancel={onCancel}
      footer={null}
      className={ModalSize.Medium}
      centered
      data-testid="system-import-data-modal"
    >
      <Form form={form} layout="vertical" onFinish={onSubmit}>
        <Alert
          message={t('system:dangerZone.importData.modal.warning')}
          description={t('system:dangerZone.importData.modal.warningText')}
          type="warning"
        />

        <Form.Item label={t('system:dangerZone.importData.modal.selectFile')} required>
          <Upload
            beforeUpload={(file) => {
              setImportFile(file);
              return false;
            }}
            onRemove={() => setImportFile(null)}
            maxCount={1}
            accept=".json"
            data-testid="system-import-file-upload"
          >
            <Button icon={<UploadOutlined />} data-testid="system-import-upload-button">
              {importFile ? importFile.name : t('system:dangerZone.importData.modal.selectFile')}
            </Button>
          </Upload>
        </Form.Item>

        <Form.Item label={t('system:dangerZone.importData.modal.importMode')}>
          <Radio.Group
            value={importMode}
            onChange={(e) => setImportMode(e.target.value)}
            data-testid="system-import-mode-radio-group"
          >
            <Space direction="vertical">
              <Radio value="skip" data-testid="system-import-mode-skip">
                <Space direction="vertical" size={4}>
                  <Typography.Text strong>
                    {t('system:dangerZone.importData.modal.modeSkip')}
                  </Typography.Text>
                  <Typography.Text>
                    {t('system:dangerZone.importData.modal.modeSkipDesc')}
                  </Typography.Text>
                </Space>
              </Radio>
              <Radio value="override" data-testid="system-import-mode-override">
                <Space direction="vertical" size={4}>
                  <Typography.Text strong>
                    {t('system:dangerZone.importData.modal.modeOverride')}
                  </Typography.Text>
                  <Typography.Text>
                    {t('system:dangerZone.importData.modal.modeOverrideDesc')}
                  </Typography.Text>
                </Space>
              </Radio>
            </Space>
          </Radio.Group>
        </Form.Item>

        <Form.Item>
          <Flex justify="flex-end">
            <Button onClick={onCancel} data-testid="system-import-cancel-button">
              {t('system:dangerZone.importData.modal.cancel')}
            </Button>
            <Button
              htmlType="submit"
              loading={isSubmitting}
              disabled={!importFile}
              data-testid="system-import-submit-button"
            >
              {t('system:dangerZone.importData.modal.import')}
            </Button>
          </Flex>
        </Form.Item>
      </Form>
    </Modal>
  );
};
