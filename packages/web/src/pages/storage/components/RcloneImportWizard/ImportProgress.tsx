import React from 'react';
import { Alert, Flex, Table } from 'antd';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import type { ImportStatus, WizardTranslator } from './types';
import type { ColumnsType } from 'antd/es/table';

interface ImportProgressProps {
  t: WizardTranslator;
  importStatuses: ImportStatus[];
  columns: ColumnsType<ImportStatus>;
  isImporting: boolean;
}

export const ImportProgress: React.FC<ImportProgressProps> = ({
  t,
  importStatuses,
  columns,
  isImporting,
}) => (
  <Flex vertical>
    {isImporting ? (
      <Flex align="center" justify="center">
        <LoadingWrapper
          loading
          centered
          minHeight={160}
          tip={t('resources:storage.import.importing')}
        >
          <Flex />
        </LoadingWrapper>
      </Flex>
    ) : (
      <>
        <Alert
          message={t('resources:storage.import.complete')}
          description={t('resources:storage.import.completeDescription')}
          type="success"
          showIcon
        />

        <Table<ImportStatus>
          dataSource={importStatuses}
          columns={columns}
          rowKey="name"
          pagination={false}
          size="small"
          data-testid="rclone-wizard-results-table"
        />
      </>
    )}
  </Flex>
);
