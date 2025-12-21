import React from 'react';
import { Alert, Form, Flex, Popover, Slider, Space, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  ExclamationCircleOutlined,
  QuestionCircleOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';

interface PrioritySelectorProps {
  priority: number;
  onPriorityChange: (priority: number) => void;
  priorityLegendItems: Array<{
    level: number;
    label: string;
    description: string;
  }>;
  getPriorityLabel: (priority: number) => string;
}

const PrioritySelector: React.FC<PrioritySelectorProps> = ({
  priority,
  onPriorityChange,
  priorityLegendItems,
  getPriorityLabel,
}) => {
  const { t } = useTranslation(['functions']);

  return (
    <Form.Item
      label={
        <Space size={4}>
          {t('functions:priority')}
          <Popover
            content={
              <div style={{ maxWidth: 320 }}>
                <div style={{ display: 'block' }}>
                  <Typography.Text strong>{t('functions:priorityPopoverLevels')}</Typography.Text>
                </div>
                {priorityLegendItems.map((item) => (
                  <Flex key={item.level} align="center" gap={8} wrap>
                    <Tag>
                      P{item.level} ({item.label})
                    </Tag>
                    <Typography.Text type="secondary">{item.description}</Typography.Text>
                  </Flex>
                ))}
              </div>
            }
            title={t('functions:priorityPopoverTitle')}
            trigger="click"
          >
            <QuestionCircleOutlined style={{ fontSize: 16, cursor: 'pointer' }} />
          </Popover>
        </Space>
      }
      help={t('functions:priorityHelp')}
    >
      <Slider
        min={1}
        max={5}
        value={priority}
        onChange={onPriorityChange}
        marks={{
          1: t('functions:priorityHigh'),
          3: t('functions:priorityNormal'),
          5: t('functions:priorityLow'),
        }}
        tooltip={{
          formatter: (value?: number) => {
            const labels = {
              1: t('functions:priorityHighest'),
              2: t('functions:priorityHigh'),
              3: t('functions:priorityNormal'),
              4: t('functions:priorityBelowNormal'),
              5: t('functions:priorityLow'),
            };
            return value ? `${labels[value as keyof typeof labels]} (${value})` : '';
          },
        }}
        data-testid="function-modal-priority-slider"
      />
      <div style={{ textAlign: 'center' }}>
        <Tag icon={priority === 1 ? <ExclamationCircleOutlined /> : undefined}>
          {t('functions:currentPriority')}: {getPriorityLabel(priority)} ({priority})
        </Tag>
      </div>
      {priority && (
        <Alert
          message={
            priority === 1
              ? t('functions:priorityHighestTimeout')
              : priority === 2
                ? t('functions:priorityHighWarning')
                : priority === 3
                  ? t('functions:priorityNormalWarning')
                  : priority === 4
                    ? t('functions:priorityLowWarning')
                    : t('functions:priorityLowestWarning')
          }
          description={
            priority === 1 ? (
              <>
                <div>{t('functions:priorityHighestTimeoutWarning')}</div>
                <div style={{ fontStyle: 'italic' }}>
                  {t('functions:priorityHighestDescription')}
                </div>
              </>
            ) : priority === 2 ? (
              t('functions:priorityHighDescription')
            ) : priority === 3 ? (
              t('functions:priorityNormalDescription')
            ) : priority === 4 ? (
              t('functions:priorityLowDescription')
            ) : (
              t('functions:priorityLowestDescription')
            )
          }
          type={
            priority === 1
              ? 'error'
              : priority === 2
                ? 'warning'
                : priority === 3
                  ? 'info'
                  : 'success'
          }
          showIcon
          icon={
            priority === 1 ? (
              <ExclamationCircleOutlined />
            ) : priority === 2 ? (
              <WarningOutlined />
            ) : undefined
          }
        />
      )}
    </Form.Item>
  );
};

export default PrioritySelector;
