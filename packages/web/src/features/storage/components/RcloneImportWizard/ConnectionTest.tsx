import { Alert, Flex, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import React from 'react';
import type { ImportStatus, WizardTranslator } from './types';

interface ConnectionTestProps {
  t: WizardTranslator;
  importStatuses: ImportStatus[];
  columns: ColumnsType<ImportStatus>;
}

export const ConnectionTest: React.FC<ConnectionTestProps> = ({ t, importStatuses, columns }) => (
  <Flex vertical>
    <Alert
      message={t('resources:storage.import.selectStorages')}
      description={t('resources:storage.import.selectDescription')}
      type="info"
    />

    <Table<ImportStatus>
      dataSource={importStatuses}
      columns={columns}
      rowKey="name"
      pagination={false}
      scroll={{ x: 'max-content' }}
      data-testid="rclone-wizard-config-table"
    />
  </Flex>
);
