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
    if (priority === 1) {
      return t('functions:priorityHighest');
    } else if (priority === 2) {
      return t('functions:priorityHigh');
    } else if (priority === 3) {
      return t('functions:priorityNormal');
    } else if (priority === 4) {
      return t('functions:priorityBelowNormal');
    }
    return t('functions:priorityLow');
  };

  return {
    priorityLegendItems,
    getPriorityLabel,
  };
};
