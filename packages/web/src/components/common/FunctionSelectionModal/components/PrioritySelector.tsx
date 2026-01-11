import React from 'react';
import { Alert, Flex, Form, Popover, Slider, Space, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  ExclamationCircleOutlined,
  QuestionCircleOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';

interface PrioritySelectorProps {
  priority: number;
  onPriorityChange: (priority: number) => void;
  priorityLegendItems: {
    level: number;
    label: string;
    description: string;
  }[];
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
              <Flex vertical>
                <Flex>
                  <Typography.Text strong>{t('functions:priorityPopoverLevels')}</Typography.Text>
                </Flex>
                {priorityLegendItems.map((item) => (
                  <Flex key={item.level} align="center" wrap>
                    <Tag>
                      {t('functions:priorityLevelFormat', {
                        level: item.level,
                        label: item.label,
                      })}
                    </Tag>
                    <Typography.Text>{item.description}</Typography.Text>
                  </Flex>
                ))}
              </Flex>
            }
            title={t('functions:priorityPopoverTitle')}
            trigger="click"
          >
            <QuestionCircleOutlined className="cursor-pointer text-base" />
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
      <Flex className="text-center" justify="center">
        <Tag icon={priority === 1 ? <ExclamationCircleOutlined /> : undefined}>
          {t('functions:currentPriority')}: {getPriorityLabel(priority)} ({priority})
        </Tag>
      </Flex>
      {priority && (
        <Alert
          message={(() => {
            if (priority === 1) return t('functions:priorityHighestTimeout');
            if (priority === 2) return t('functions:priorityHighWarning');
            if (priority === 3) return t('functions:priorityNormalWarning');
            if (priority === 4) return t('functions:priorityLowWarning');
            return t('functions:priorityLowestWarning');
          })()}
          description={(() => {
            if (priority === 1) {
              return (
                <Flex vertical>
                  <Typography.Text>{t('functions:priorityHighestTimeoutWarning')}</Typography.Text>
                  <Typography.Text className="italic">
                    {t('functions:priorityHighestDescription')}
                  </Typography.Text>
                </Flex>
              );
            }
            if (priority === 2) return t('functions:priorityHighDescription');
            if (priority === 3) return t('functions:priorityNormalDescription');
            if (priority === 4) return t('functions:priorityLowDescription');
            return t('functions:priorityLowestDescription');
          })()}
          type={(() => {
            if (priority === 1) return 'error';
            if (priority === 2) return 'warning';
            if (priority === 3) return 'info';
            return 'success';
          })()}
          icon={(() => {
            if (priority === 1) return <ExclamationCircleOutlined />;
            if (priority === 2) return <WarningOutlined />;
            return undefined;
          })()}
        />
      )}
    </Form.Item>
  );
};

export default PrioritySelector;
