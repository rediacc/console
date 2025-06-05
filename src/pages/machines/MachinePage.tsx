import React from 'react';
import { Card } from 'antd';
import { useTranslation } from 'react-i18next';
import { MachineTable } from '@/components/resources/MachineTable';

export const MachinePage: React.FC = () => {
  const { t } = useTranslation('machines');

  return (
    <Card>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0, fontSize: '24px', fontWeight: 600 }}>{t('title')}</h2>
      </div>
      <MachineTable 
        mode="full"
        showFilters={true}
        showActions={true}
      />
    </Card>
  );
};

export default MachinePage;