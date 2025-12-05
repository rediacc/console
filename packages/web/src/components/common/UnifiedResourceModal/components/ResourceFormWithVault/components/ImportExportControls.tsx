import { Upload, Button, Space, Tooltip } from 'antd';
import type { UploadFile } from 'antd/es/upload/interface';
import { UploadOutlined, DownloadOutlined } from '@/utils/optimizedIcons';
import { ImportExportRow } from '../styles';

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
