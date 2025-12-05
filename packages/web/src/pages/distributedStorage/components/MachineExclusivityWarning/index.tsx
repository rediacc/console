import React from 'react';
import { InfoCircleOutlined } from '@/utils/optimizedIcons';
import { useTranslation } from 'react-i18next';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import {
  WarningAlert,
  InlineWarningAlert,
  MessageText,
  DescriptionWrapper,
  StyledText,
  RuleList,
} from './styles';

interface MachineExclusivityWarningProps {
  type?: 'cluster' | 'image' | 'clone' | 'general';
  machineName?: string;
  currentAssignment?: {
    type: string;
    name: string;
  };
  style?: React.CSSProperties;
}

export const MachineExclusivityWarning: React.FC<MachineExclusivityWarningProps> = ({
  type = 'general',
  machineName,
  currentAssignment,
  style,
}) => {
  const { t } = useTranslation(['distributedStorage', 'machines']);

  const getWarningMessage = () => {
    if (currentAssignment && machineName) {
      return t('machines:validation.alreadyAssigned', {
        resourceType: t(`distributedStorage:${currentAssignment.type}s.${currentAssignment.type}`),
        resourceName: currentAssignment.name,
      });
    }

    switch (type) {
      case 'cluster':
        return t('distributedStorage:warnings.machineClusterExclusivity');
      case 'image':
        return t('distributedStorage:warnings.machineImageExclusivity');
      case 'clone':
        return t('distributedStorage:warnings.machineCloneExclusivity');
      default:
        return t('distributedStorage:warnings.machineExclusivity');
    }
  };

  const getDescription = () => {
    switch (type) {
      case 'cluster':
        return t('distributedStorage:warnings.clusterExclusivityDescription');
      case 'image':
        return t('distributedStorage:warnings.imageExclusivityDescription');
      case 'clone':
        return t('distributedStorage:warnings.cloneExclusivityDescription');
      default:
        return t('distributedStorage:warnings.exclusivityDescription');
    }
  };

  return (
    <WarningAlert
      message={<MessageText>{getWarningMessage()}</MessageText>}
      description={
        <DescriptionWrapper data-testid="exclusivity-warning-description">
          <StyledText data-testid="exclusivity-warning-description-text">
            {getDescription()}
          </StyledText>
          <br />
          <br />
          <StyledText strong data-testid="exclusivity-warning-note">
            {t('distributedStorage:warnings.exclusivityNote')}
          </StyledText>
          <RuleList data-testid="exclusivity-warning-list">
            <li data-testid="exclusivity-warning-cluster-rule">
              <MessageText>{t('distributedStorage:warnings.oneClusterPerMachine')}</MessageText>
            </li>
            <li data-testid="exclusivity-warning-image-rule">
              <MessageText>{t('distributedStorage:warnings.oneImagePerMachine')}</MessageText>
            </li>
            <li data-testid="exclusivity-warning-clone-rule">
              <MessageText>{t('distributedStorage:warnings.multipleClonesPossible')}</MessageText>
            </li>
          </RuleList>
        </DescriptionWrapper>
      }
      type="warning"
      showIcon
      icon={<InfoCircleOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD }} />}
      style={style}
      data-testid={`exclusivity-warning-${type}`}
    />
  );
};

// Simplified inline warning component
export const MachineExclusivityInlineWarning: React.FC<{
  message?: string;
  style?: React.CSSProperties;
}> = ({ message, style }) => {
  const { t } = useTranslation('distributedStorage');

  return (
    <InlineWarningAlert
      message={<MessageText>{message || t('warnings.machineExclusivity')}</MessageText>}
      type="warning"
      showIcon
      banner
      style={style}
      data-testid="exclusivity-warning-inline"
    />
  );
};
