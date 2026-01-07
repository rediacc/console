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
        <Col xs={24} lg={12}>
          <Card size="small" title={t('trace.tasksBefore')}>
            <Flex vertical className="overflow-auto">
              {tasksBefore.map((item, index) => (
                <Flex key={index} wrap>
                  <Space wrap>
                    <Typography.Text code className="break-all">
                      {item.taskId}
                    </Typography.Text>
                    <Tag>{item.status}</Tag>
                    <Typography.Text>{dayjs(item.createdTime).fromNow()}</Typography.Text>
                  </Space>
                </Flex>
              ))}
              {tasksBefore.length === 0 && (
                <Empty description={t('trace.noTasksAhead')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Flex>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card size="small" title={t('trace.tasksAfter')}>
            <Flex vertical className="overflow-auto">
              {tasksAfter.map((item, index) => (
                <Flex key={index} wrap>
                  <Space wrap>
                    <Typography.Text code className="break-all">
                      {item.taskId}
                    </Typography.Text>
                    <Tag>{item.status}</Tag>
                    <Typography.Text>{dayjs(item.createdTime).fromNow()}</Typography.Text>
                  </Space>
                </Flex>
              ))}
              {tasksAfter.length === 0 && (
                <Empty
                  description={t('trace.noTasksBehind')}
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              )}
            </Flex>
          </Card>
        </Col>
      </Row>
      <Flex>
        <Typography.Text>
          {t('trace.totalTasksSummary', { ahead: tasksBefore.length, behind: tasksAfter.length })}
        </Typography.Text>
      </Flex>
    </>
  );
};
