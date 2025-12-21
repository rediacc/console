import React from 'react';
import { Card, Col, Empty, Flex, Row, Space, Tag, Typography } from 'antd';
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
            <Flex vertical style={{ overflowY: 'auto' }}>
              {tasksBefore.map((item, index) => (
                <Flex key={index}>
                  <Space>
                    <Typography.Text code style={{ fontFamily: 'monospace' }}>
                      {item.taskId}
                    </Typography.Text>
                    <Tag color={item.status === 'PROCESSING' ? 'processing' : 'default'}>
                      {item.status}
                    </Tag>
                    <Typography.Text>
                      {dayjs(item.createdTime).fromNow()}
                    </Typography.Text>
                  </Space>
                </Flex>
              ))}
              {tasksBefore.length === 0 && (
                <Empty description={t('trace.noTasksAhead')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Flex>
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title={t('trace.tasksAfter')}>
            <Flex vertical style={{ overflowY: 'auto' }}>
              {tasksAfter.map((item, index) => (
                <Flex key={index}>
                  <Space>
                    <Typography.Text code style={{ fontFamily: 'monospace' }}>
                      {item.taskId}
                    </Typography.Text>
                    <Tag color={item.status === 'PROCESSING' ? 'processing' : 'default'}>
                      {item.status}
                    </Tag>
                    <Typography.Text>
                      {dayjs(item.createdTime).fromNow()}
                    </Typography.Text>
                  </Space>
                </Flex>
              ))}
              {tasksAfter.length === 0 && (
                <Empty description="No tasks behind" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Flex>
          </Card>
        </Col>
      </Row>
      <Flex>
        <Typography.Text>
          Total: {tasksBefore.length} tasks ahead, {tasksAfter.length} tasks behind
        </Typography.Text>
      </Flex>
    </>
  );
};
