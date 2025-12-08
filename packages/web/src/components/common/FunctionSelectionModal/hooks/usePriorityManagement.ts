import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

export const usePriorityManagement = () => {
  const { t } = useTranslation(['functions']);

  const priorityLegendItems = useMemo(
    () => [
      {
        level: 1,
        label: t('functions:priorityHighest'),
        description: t('functions:priorityPopoverP1'),
      },
      {
        level: 2,
        label: t('functions:priorityHigh'),
        description: t('functions:priorityPopoverP2'),
      },
      {
        level: 3,
        label: t('functions:priorityNormal'),
        description: t('functions:priorityPopoverP3'),
      },
      {
        level: 4,
        label: t('functions:priorityBelowNormal'),
        description: t('functions:priorityPopoverP4'),
      },
      {
        level: 5,
        label: t('functions:priorityLow'),
        description: t('functions:priorityPopoverP5'),
      },
    ],
    [t]
  );

  const getPriorityLabel = (priority: number): string => {
    return priority === 1
      ? t('functions:priorityHighest')
      : priority === 2
        ? t('functions:priorityHigh')
        : priority === 3
          ? t('functions:priorityNormal')
          : priority === 4
            ? t('functions:priorityBelowNormal')
            : t('functions:priorityLow');
  };

  return {
    priorityLegendItems,
    getPriorityLabel,
  };
};
