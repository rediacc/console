import React from 'react';
import { Alert, Button, Flex, Form, Modal, Radio, Space, Typography, Upload } from 'antd';
import { ModalSize } from '@/types/modal';
import { UploadOutlined } from '@/utils/optimizedIcons';
import type { FormInstance } from 'antd';
import type { TFunction } from 'i18next';

interface ImportModalProps {
  tSystem: TFunction<'system'>;
  open: boolean;
  onCancel: () => void;
  onSubmit: () => void;
  importForm: FormInstance;
  importFile: File | null;
  setImportFile: (file: File | null) => void;
  importMode: 'skip' | 'override';
  setImportMode: (mode: 'skip' | 'override') => void;
  isSubmitting: boolean;
}

export const ImportModal: React.FC<ImportModalProps> = ({
  tSystem,
  open,
  onCancel,
  onSubmit,
  importForm,
  importFile,
  setImportFile,
  importMode,
  setImportMode,
  isSubmitting,
}) => (
  <Modal
    title={tSystem('dangerZone.importData.modal.title')}
    open={open}
    onCancel={onCancel}
    footer={null}
    className={ModalSize.Medium}
    centered
  >
    <Form form={importForm} layout="vertical" onFinish={onSubmit}>
      <Alert
        message={tSystem('dangerZone.importData.modal.warning')}
        description={tSystem('dangerZone.importData.modal.warningText')}
        type="warning"
        showIcon
      />

      <Form.Item label={tSystem('dangerZone.importData.modal.selectFile')} required>
        <Upload
          beforeUpload={(file) => {
            setImportFile(file);
            return false;
          }}
          onRemove={() => setImportFile(null)}
          maxCount={1}
          accept=".json"
        >
          <Button icon={<UploadOutlined />}>
            {importFile ? importFile.name : tSystem('dangerZone.importData.modal.selectFile')}
          </Button>
        </Upload>
      </Form.Item>

      <Form.Item label={tSystem('dangerZone.importData.modal.importMode')}>
        <Radio.Group value={importMode} onChange={(e) => setImportMode(e.target.value)}>
          <Space direction="vertical">
            <Radio value="skip">
              <Space direction="vertical" size={4}>
                <Typography.Text strong>
                  {tSystem('dangerZone.importData.modal.modeSkip')}
                </Typography.Text>
                <Typography.Text>
                  {tSystem('dangerZone.importData.modal.modeSkipDesc')}
                </Typography.Text>
              </Space>
            </Radio>
            <Radio value="override">
              <Space direction="vertical" size={4}>
                <Typography.Text strong>
                  {tSystem('dangerZone.importData.modal.modeOverride')}
                </Typography.Text>
                <Typography.Text>
                  {tSystem('dangerZone.importData.modal.modeOverrideDesc')}
                </Typography.Text>
              </Space>
            </Radio>
          </Space>
        </Radio.Group>
      </Form.Item>

      <Form.Item>
        <Flex justify="flex-end" gap={8}>
          <Button onClick={onCancel}>{tSystem('dangerZone.importData.modal.cancel')}</Button>
          <Button htmlType="submit" loading={isSubmitting} disabled={!importFile}>
            {tSystem('dangerZone.importData.modal.import')}
          </Button>
        </Flex>
      </Form.Item>
    </Form>
  </Modal>
);
