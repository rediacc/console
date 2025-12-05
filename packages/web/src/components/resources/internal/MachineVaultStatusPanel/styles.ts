import styled from 'styled-components';
import { Typography, Tag, Badge, Card, Empty, List } from 'antd';
import { CloudServerOutlined } from '@/utils/optimizedIcons';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import {
  DetailPanelSecondaryTextBlock,
  DetailPanelSurface,
  DetailPanelHeader,
  DetailPanelHeaderRow,
  DetailPanelTitleGroup,
  DetailPanelTitle,
  DetailPanelCollapseButton,
  DetailPanelTagGroup,
  DetailPanelBody,
  DetailPanelFieldRow,
  DetailPanelFieldLabel,
  DetailPanelFieldValue,
  DetailPanelFieldStrongValue,
  DetailPanelFieldMonospaceValue,
  DetailPanelDivider,
  DetailPanelSectionHeader,
  DetailPanelSectionTitle,
} from '../detailPanelPrimitives';

const { Title, Text } = Typography;

const TAG_VARIANTS = {
  team: {
    background: 'var(--color-success)',
    color: 'var(--color-text-inverse)',
  },
  bridge: {
    background: 'var(--color-primary)',
    color: 'var(--color-text-inverse)',
  },
  region: {
    background: 'var(--color-info)',
    color: 'var(--color-text-inverse)',
  },
  queue: {
    background: 'var(--color-success)',
    color: 'var(--color-text-inverse)',
  },
  version: {
    background: 'var(--color-bg-tertiary)',
    color: 'var(--color-text-primary)',
  },
} as const;

export {
  DetailPanelSurface as PanelWrapper,
  DetailPanelHeader as StickyHeader,
  DetailPanelHeaderRow as HeaderRow,
  DetailPanelTitleGroup as HeaderTitleGroup,
  DetailPanelTitle as MachineName,
  DetailPanelCollapseButton as CollapseButton,
  DetailPanelBody as ContentWrapper,
  DetailPanelFieldRow as InlineField,
  DetailPanelFieldLabel as FieldLabel,
  DetailPanelFieldValue as FieldValue,
  DetailPanelFieldStrongValue as FieldValueStrong,
  DetailPanelFieldMonospaceValue as FieldValueMonospace,
};

export const HeaderIcon = styled(CloudServerOutlined)`
  font-size: ${DESIGN_TOKENS.DIMENSIONS.ICON_XL}px;
  color: var(--color-primary);
`;

export const TagRow = styled(DetailPanelTagGroup)`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const StyledTag = styled(Tag)<{ $variant: keyof typeof TAG_VARIANTS }>`
  && {
    border: none;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    background-color: ${({ $variant }) => TAG_VARIANTS[$variant].background};
    color: ${({ $variant }) => TAG_VARIANTS[$variant].color};
  }
`;

export const QueueBadge = styled(Badge)`
  && .ant-badge-count {
    background-color: var(--color-success);
    color: var(--color-text-inverse);
  }
`;

export const TimestampWrapper = styled.div`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const Timestamp = styled(Text)`
  && {
    font-size: ${DESIGN_TOKENS.FONT_SIZE.CAPTION}px;
    color: var(--color-text-secondary);
  }
`;

export const EmptyState = styled(Empty)`
  margin-top: ${({ theme }) => theme.spacing.XXXL}px;
`;

export const SectionDivider = styled(DetailPanelDivider).attrs({
  orientation: 'left',
})`
  && {
    margin: ${({ theme }) => `${theme.spacing.XL}px 0`};
  }
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const SectionHeader = styled(DetailPanelSectionHeader)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const SectionTitle = styled(DetailPanelSectionTitle)``;

export const SectionBlock = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.XL}px;
`;

export const InfoCard = styled(Card)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    margin-bottom: ${({ theme }) => theme.spacing.LG}px;
  }
`;

export const FullWidthStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
  width: 100%;
`;

export const SecondaryText = styled(DetailPanelSecondaryTextBlock)``;

export const MetricCard = styled(Card)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    margin-bottom: ${({ theme }) => theme.spacing.LG}px;
  }
`;

export const CardHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`;

export const CardTitle = styled(Title)`
  && {
    margin: 0;
    font-size: ${DESIGN_TOKENS.FONT_SIZE.BASE}px;
  }
`;

export const CardTagGroup = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

const STATUS_TONES = {
  success: {
    background: 'var(--color-success)',
    color: 'var(--color-text-inverse)',
  },
  info: {
    background: 'var(--color-info)',
    color: 'var(--color-text-inverse)',
  },
  warning: {
    background: 'var(--color-warning)',
    color: 'var(--color-text-inverse)',
  },
  default: {
    background: 'var(--color-bg-tertiary)',
    color: 'var(--color-text-primary)',
  },
} as const;

export const StatusTag = styled(Tag)<{ $tone?: keyof typeof STATUS_TONES }>`
  && {
    border: none;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
    font-weight: 500;
    background-color: ${({ $tone = 'default' }) => STATUS_TONES[$tone].background};
    color: ${({ $tone = 'default' }) => STATUS_TONES[$tone].color};
  }
`;

export const AddressTag = styled(Tag)`
  && {
    border: none;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    background-color: var(--color-info);
    color: var(--color-text-inverse);
  }
`;

export const StyledList = styled(List)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.LG}px;
  }
`;

export const ListCard = styled(Card)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`;

export const CardBodyStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const KeyValueRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const IndentedBlock = styled.div`
  margin-left: ${({ theme }) => theme.spacing.MD}px;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const PartitionRow = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
  font-size: ${DESIGN_TOKENS.FONT_SIZE.CAPTION}px;
  color: var(--color-text-secondary);
`;

export { IconWrapper } from '@/components/ui';
