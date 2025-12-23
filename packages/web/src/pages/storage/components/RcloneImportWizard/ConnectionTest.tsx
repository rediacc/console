import React from 'react';
import { Alert, Flex, Table } from 'antd';
import type { ImportStatus, WizardTranslator } from './types';
import type { ColumnsType } from 'antd/es/table';

interface ConnectionTestProps {
  t: WizardTranslator;
  importStatuses: ImportStatus[];
  columns: ColumnsType<ImportStatus>;
}

export const ConnectionTest: React.FC<ConnectionTestProps> = ({
  t,
  importStatuses,
  columns,
}) => (
  <Flex vertical>
    <Alert
      message={t('resources:storage.import.selectStorages')}
      description={t('resources:storage.import.selectDescription')}
      type="info"
      showIcon
    />

    <Table<ImportStatus>
      dataSource={importStatuses}
      columns={columns}
      rowKey="name"
      pagination={false}
      size="small"
      data-testid="rclone-wizard-config-table"
    />
  </Flex>
);
