import React from 'react';
import { Card, Col, Empty, Row, Space } from 'antd';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import { RediaccTag, RediaccText } from '@/components/ui';
import type { QueuePositionEntry } from '@rediacc/shared/types';
import { ScrollContainer, ScrollItem, MonospaceText } from '../styles';

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
            <ScrollContainer>
              {tasksBefore.map((item, index) => (
                <ScrollItem key={index}>
                  <Space>
                    <MonospaceText size="xs" code>
                      {item.taskId}
                    </MonospaceText>
                    <RediaccTag
                      compact
                      variant={item.status === 'PROCESSING' ? 'primary' : 'neutral'}
                    >
                      {item.status}
                    </RediaccTag>
                    <RediaccText variant="caption" color="muted">
                      {dayjs(item.createdTime).fromNow()}
                    </RediaccText>
                  </Space>
                </ScrollItem>
              ))}
              {tasksBefore.length === 0 && (
                <Empty description={t('trace.noTasksAhead')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </ScrollContainer>
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title={t('trace.tasksAfter')}>
            <ScrollContainer>
              {tasksAfter.map((item, index) => (
                <ScrollItem key={index}>
                  <Space>
                    <MonospaceText size="xs" code>
                      {item.taskId}
                    </MonospaceText>
                    <RediaccTag
                      compact
                      variant={item.status === 'PROCESSING' ? 'primary' : 'neutral'}
                    >
                      {item.status}
                    </RediaccTag>
                    <RediaccText variant="caption" color="muted">
                      {dayjs(item.createdTime).fromNow()}
                    </RediaccText>
                  </Space>
                </ScrollItem>
              ))}
              {tasksAfter.length === 0 && (
                <Empty description="No tasks behind" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </ScrollContainer>
          </Card>
        </Col>
      </Row>
      <div>
        <RediaccText variant="caption" color="muted">
          Total: {tasksBefore.length} tasks ahead, {tasksAfter.length} tasks behind
        </RediaccText>
      </div>
    </>
  );
};
