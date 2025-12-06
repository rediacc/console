import styled from 'styled-components';
import { Typography } from 'antd';
import { CloudServerOutlined } from '@/utils/optimizedIcons';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import { RediaccTag } from '@/components/ui/Tag';
import { RediaccText } from '@/components/ui/Text';
import { RediaccCard, RediaccBadge, RediaccEmpty, RediaccList } from '@/components/ui';
import {
  PanelWrapper,
  Header,
  HeaderRow,
  TitleGroup,
  PanelTitle,
  CollapseButton,
  TagGroup,
  ContentWrapper,
  FieldRow,
  FieldLabel,
  FieldValue,
  FieldValueStrong,
  FieldValueMonospace,
  SectionDivider,
  SectionHeader,
  SectionTitle,
  SubduedText,
} from '../sharedDetailPanelAliases';

const { Title } = Typography;

export { PanelWrapper, Header, HeaderRow, TitleGroup, PanelTitle, CollapseButton, ContentWrapper };

export { IconWrapper } from '@/components/ui';

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

export { TagGroup, FieldRow, FieldLabel, FieldValue, FieldValueStrong, FieldValueMonospace };

export const HeaderIcon = styled(CloudServerOutlined)`
  font-size: ${DESIGN_TOKENS.DIMENSIONS.ICON_XL}px;
  color: var(--color-primary);
`;

export const TagRow = styled(TagGroup)`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const StyledTag = styled(RediaccTag).attrs<{ $variant: keyof typeof TAG_VARIANTS }>(
  ({ $variant }) => {
    const presetMap: Record<keyof typeof TAG_VARIANTS, string> = {
      team: 'team',
      bridge: 'bridge',
      region: 'region',
      queue: 'team',
      version: 'neutral',
    };
    return {
      preset: presetMap[$variant] as any,
      borderless: true,
    };
  }
)<{ $variant: keyof typeof TAG_VARIANTS }>`
  && {
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const QueueBadge = styled(RediaccBadge)`
  && .ant-badge-count {
    background-color: var(--color-success);
    color: var(--color-text-inverse);
  }
`;

export const TimestampWrapper = styled.div`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const Timestamp = styled(RediaccText).attrs({
  size: 'xs',
  color: 'secondary',
})`
  && {
    font-size: ${DESIGN_TOKENS.FONT_SIZE.CAPTION}px;
  }
`;

export const EmptyState = styled(RediaccEmpty)`
  margin-top: ${({ theme }) => theme.spacing.XXXL}px;
`;

export { SectionDivider, SectionHeader, SectionTitle, SubduedText };

export const SectionBlock = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.XL}px;
`;

export const InfoCard = styled(RediaccCard)`
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

export const MetricCard = styled(RediaccCard)`
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

export const StatusTag = styled(RediaccTag).attrs<{ $tone?: keyof typeof STATUS_TONES }>(
  ({ $tone = 'default' }) => {
    const variantMap: Record<keyof typeof STATUS_TONES, string> = {
      success: 'success',
      info: 'info',
      warning: 'warning',
      default: 'neutral',
    };
    return {
      variant: variantMap[$tone] as any,
      borderless: true,
    };
  }
)<{ $tone?: keyof typeof STATUS_TONES }>``;

export const AddressTag = styled(RediaccTag).attrs({
  variant: 'info',
  borderless: true,
})`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }
`;

export const StyledList = styled(RediaccList)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.LG}px;
  }
`;

export const ListCard = styled(RediaccCard)`
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
