import { Upload, Button, Space, Tooltip } from 'antd';
import { ImportExportRow } from '@/components/common/UnifiedResourceModal/components/ResourceFormWithVault/styles';
import { UploadOutlined, DownloadOutlined } from '@/utils/optimizedIcons';
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
  <ImportExportRow>
    <Space>
      <Upload accept=".json" showUploadList={false} beforeUpload={onImport}>
        <Tooltip title={importLabel}>
          <Button size="small" icon={<UploadOutlined />} aria-label={importLabel} />
        </Tooltip>
      </Upload>
      <Tooltip title={exportLabel}>
        <Button
          size="small"
          icon={<DownloadOutlined />}
          onClick={onExport}
          aria-label={exportLabel}
        />
      </Tooltip>
    </Space>
  </ImportExportRow>
);
