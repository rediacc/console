import React from 'react';
import { Card, Col, Empty, Row, Space, Tag, Typography } from 'antd';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import type { QueuePositionEntry } from '@rediacc/shared/types';

interface RelatedQueueItemsProps {
  queuePosition: QueuePositionEntry[];
}

export const RelatedQueueItems: React.FC<RelatedQueueItemsProps> = ({ queuePosition }) => {
  const { t } = useTranslation(['queue', 'common']);

  const tasksBefore = queuePosition.filter((pos) => pos.relativePosition === 'Before');
  const tasksAfter = queuePosition.filter((pos) => pos.relativePosition === 'After');

  return (
    <>
      <Row gutter={[16, 16]}>
        <Col span={12}>
          <Card size="small" title={t('trace.tasksBefore')}>
            <div style={{ overflowY: 'auto' }}>
              {tasksBefore.map((item, index) => (
                <div key={index}>
                  <Space>
                    <Typography.Text code style={{ fontFamily: 'monospace' }}>
                      {item.taskId}
                    </Typography.Text>
                    <Tag color={item.status === 'PROCESSING' ? 'processing' : 'default'}>
                      {item.status}
                    </Tag>
                    <Typography.Text type="secondary">
                      {dayjs(item.createdTime).fromNow()}
                    </Typography.Text>
                  </Space>
                </div>
              ))}
              {tasksBefore.length === 0 && (
                <Empty description={t('trace.noTasksAhead')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </div>
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title={t('trace.tasksAfter')}>
            <div style={{ overflowY: 'auto' }}>
              {tasksAfter.map((item, index) => (
                <div key={index}>
                  <Space>
                    <Typography.Text code style={{ fontFamily: 'monospace' }}>
                      {item.taskId}
                    </Typography.Text>
                    <Tag color={item.status === 'PROCESSING' ? 'processing' : 'default'}>
                      {item.status}
                    </Tag>
                    <Typography.Text type="secondary">
                      {dayjs(item.createdTime).fromNow()}
                    </Typography.Text>
                  </Space>
                </div>
              ))}
              {tasksAfter.length === 0 && (
                <Empty description="No tasks behind" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </div>
          </Card>
        </Col>
      </Row>
      <div>
        <Typography.Text type="secondary">
          Total: {tasksBefore.length} tasks ahead, {tasksAfter.length} tasks behind
        </Typography.Text>
      </div>
    </>
  );
};
