import { Alert, Flex, Input, Typography } from 'antd';
import type { TFunction } from 'i18next';

interface Clone {
  repositoryGuid: string;
  repositoryName: string;
}

interface BlockedDeletionContentProps {
  repositoryName: string;
  childClones: Clone[];
  t: TFunction;
}

export const BlockedDeletionContent = ({
  repositoryName,
  childClones,
  t,
}: BlockedDeletionContentProps) => (
  <Flex vertical>
    <Typography.Paragraph>
      {t('resources:repositories.hasActiveClonesMessage', {
        name: repositoryName,
        count: childClones.length,
      })}
    </Typography.Paragraph>
    {/* eslint-disable-next-line no-restricted-syntax */}
    <Typography.Text strong style={{ display: 'block' }}>
      {t('resources:repositories.clonesList')}
    </Typography.Text>
    <ul>
      {childClones.map((clone) => (
        <li key={clone.repositoryGuid}>{clone.repositoryName}</li>
      ))}
    </ul>
    <Typography.Paragraph>{t('resources:repositories.deleteOptionsMessage')}</Typography.Paragraph>
  </Flex>
);

interface ConfirmDeletionContentProps {
  repositoryName: string;
  t: TFunction;
  onInputChange: (value: string) => void;
}

export const ConfirmDeletionContent = ({
  repositoryName,
  t,
  onInputChange,
}: ConfirmDeletionContentProps) => (
  <Flex vertical>
    <Alert
      message={t('resources:repositories.deleteGrandWarning')}
      description={t('resources:repositories.deleteGrandWarningDesc', {
        name: repositoryName,
      })}
      type="warning"
      showIcon
    />
    <Typography.Text strong>
      {t('resources:repositories.deleteGrandConfirmPrompt', { name: repositoryName })}
    </Typography.Text>
    <Input
      type="text"
      placeholder={repositoryName}
      className="w-full"
      onChange={(e) => onInputChange(e.target.value)}
    />
  </Flex>
);
