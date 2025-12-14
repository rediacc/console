import { Space, Upload } from 'antd';
import { ImportExportRow } from '@/components/common/UnifiedResourceModal/components/ResourceFormWithVault/styles';
import { RediaccButton, RediaccTooltip } from '@/components/ui';
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
  <ImportExportRow>
    <Space>
      <Upload accept=".json" showUploadList={false} beforeUpload={onImport}>
        <RediaccTooltip title={importLabel}>
          <RediaccButton icon={<UploadOutlined />} aria-label={importLabel} />
        </RediaccTooltip>
      </Upload>
      <RediaccTooltip title={exportLabel}>
        <RediaccButton icon={<DownloadOutlined />} onClick={onExport} aria-label={exportLabel} />
      </RediaccTooltip>
    </Space>
  </ImportExportRow>
);
