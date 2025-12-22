import React from 'react';
import { Col, Row, Statistic } from 'antd';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import { ClockCircleOutlined, HourglassOutlined, SyncOutlined } from '@/utils/optimizedIcons';
import type { StatsPanelProps } from '../types';

export const StatsPanel: React.FC<StatsPanelProps> = ({
  queueDetails,
  totalDurationSeconds,
  processingDurationSeconds,
}) => {
  const { t } = useTranslation(['queue', 'common']);

  return (
    <Row gutter={[16, 16]}>
      <Col span={8}>
        <Statistic
          title={t('queue:statistics.totalDuration')}
          value={
            totalDurationSeconds < 60 ? totalDurationSeconds : Math.floor(totalDurationSeconds / 60)
          }
          suffix={totalDurationSeconds < 60 ? 'sec' : 'min'}
          prefix={<ClockCircleOutlined />}
        />
      </Col>
      <Col span={8}>
        <Statistic
          title={t('queue:statistics.processing')}
          value={
            processingDurationSeconds
              ? processingDurationSeconds < 60
                ? processingDurationSeconds
                : Math.floor(processingDurationSeconds / 60)
              : 0
          }
          suffix={processingDurationSeconds && processingDurationSeconds < 60 ? 'sec' : 'min'}
          prefix={<SyncOutlined />}
        />
      </Col>
      <Col span={8}>
        <Statistic
          title={t('queue:statistics.timeSinceAssigned')}
          value={
            queueDetails.assignedTime
              ? dayjs().diff(dayjs(queueDetails.assignedTime), 'minute')
              : 'N/A'
          }
          suffix={queueDetails.assignedTime ? 'min' : ''}
          prefix={<HourglassOutlined />}
        />
      </Col>
    </Row>
  );
};
