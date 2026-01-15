import { Alert, Flex, Typography, Upload } from 'antd';
import type { UploadFile } from 'antd/es/upload';
import React from 'react';
import { InfoCircleOutlined, UploadOutlined } from '@/utils/optimizedIcons';
import type { WizardTranslator } from './types';

const { Text, Paragraph } = Typography;

interface StepConfigFormProps {
  t: WizardTranslator;
  fileList: UploadFile[];
  parsingError: string | null;
  onBeforeUpload: (file: File) => Promise<boolean>;
  onFileListChange: (files: UploadFile[]) => void;
}

export const StepConfigForm: React.FC<StepConfigFormProps> = ({
  t,
  fileList,
  parsingError,
  onBeforeUpload,
  onFileListChange,
}) => (
  <Flex vertical>
    <Alert
      message={t('resources:storage.import.instructions')}
      description={
        <Flex vertical>
          <Paragraph>{t('resources:storage.import.instructionsDetail')}</Paragraph>
          <Paragraph>
            <Text code>{t('resources:storage.import.instructionsCommand')}</Text>
          </Paragraph>
          <Paragraph>{t('resources:storage.import.uploadPrompt')}</Paragraph>
        </Flex>
      }
      type="info"
      icon={<InfoCircleOutlined />}
    />

    <Upload.Dragger
      accept=".conf"
      fileList={fileList}
      beforeUpload={onBeforeUpload}
      onChange={({ fileList }) => onFileListChange(fileList)}
      maxCount={1}
      data-testid="rclone-wizard-upload-dragger"
    >
      <p className="ant-upload-drag-icon">
        <UploadOutlined />
      </p>
      <p className="ant-upload-text">{t('resources:storage.import.dragDropText')}</p>
      <p className="ant-upload-hint">{t('resources:storage.import.supportedFormats')}</p>
    </Upload.Dragger>

    {parsingError && <Alert message={parsingError} type="error" />}
  </Flex>
);
