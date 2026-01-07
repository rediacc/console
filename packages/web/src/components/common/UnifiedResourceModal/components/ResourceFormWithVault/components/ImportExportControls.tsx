import { Button, Flex, Space, Tooltip, Upload } from 'antd';
import { DownloadOutlined, UploadOutlined } from '@/utils/optimizedIcons';
import type { UploadFile } from 'antd/es/upload/interface';

interface ImportExportControlsProps {
  importLabel: string;
  exportLabel: string;
  onImport: (file: UploadFile) => boolean;
  onExport: () => void;
}

export const ImportExportControls: React.FC<ImportExportControlsProps> = ({
  importLabel,
  exportLabel,
  onImport,
  onExport,
}) => (
  <Flex>
    <Space>
      <Upload
        accept=".json"
        showUploadList={false}
        beforeUpload={onImport}
        data-testid="resource-modal-upload-json"
      >
        <Tooltip title={importLabel}>
          <Button
            icon={<UploadOutlined />}
            aria-label={importLabel}
            data-testid="resource-modal-import-button"
          />
        </Tooltip>
      </Upload>
      <Tooltip title={exportLabel}>
        <Button
          icon={<DownloadOutlined />}
          onClick={onExport}
          aria-label={exportLabel}
          data-testid="resource-modal-export-button"
        />
      </Tooltip>
    </Space>
  </Flex>
);
