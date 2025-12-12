import { Typography } from 'antd';
import styled from 'styled-components';
import {
  CollapseButton,
  ContentWrapper,
  FieldLabel,
  FieldRow,
  FieldValue,
  FieldValueMonospace,
  FieldValueStrong,
  Header,
  HeaderRow,
  PanelTitle,
  PanelWrapper,
  SectionDivider,
  SectionHeader,
  SectionTitle,
  TagGroup,
  TitleGroup,
} from '@/components/resources/internal/sharedDetailPanelAliases';
import { RediaccBadge, RediaccCard, RediaccList, RediaccTag } from '@/components/ui';
import type { TagPreset, TagVariant } from '@/components/ui/Tag';
import { CloudServerOutlined } from '@/utils/optimizedIcons';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

const { Title } = Typography;

export { PanelWrapper, Header, HeaderRow, TitleGroup, PanelTitle, CollapseButton, ContentWrapper };

export { IconWrapper } from '@/components/ui';

type TagVariantKey = 'team' | 'bridge' | 'region' | 'queue' | 'version';

export { TagGroup, FieldRow, FieldLabel, FieldValue, FieldValueStrong, FieldValueMonospace };

export const HeaderIcon = styled(CloudServerOutlined)`
  font-size: ${DESIGN_TOKENS.DIMENSIONS.ICON_XL}px;
  color: var(--color-primary);
`;

export const TagRow = styled(TagGroup)`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const StyledTag = styled(RediaccTag).attrs<{ $variant: TagVariantKey }>(({ $variant }) => {
  const presetMap: Record<TagVariantKey, TagPreset | 'neutral'> = {
    team: 'team',
    bridge: 'bridge',
    region: 'region',
    queue: 'team',
    version: 'neutral',
  };
  return {
    preset: presetMap[$variant] as TagPreset,
    borderless: true,
  };
})<{ $variant: TagVariantKey }>`
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

export { SectionDivider, SectionHeader, SectionTitle };

export const SectionBlock = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.XL}px;
`;

export const InfoCard = styled(RediaccCard)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    margin-bottom: ${({ theme }) => theme.spacing.LG}px;
  }
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
    font-size: ${DESIGN_TOKENS.FONT_SIZE.MD}px;
  }
`;

export const CardTagGroup = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

type StatusToneKey = 'success' | 'info' | 'warning' | 'default';

export const StatusTag = styled(RediaccTag).attrs<{ $tone?: StatusToneKey }>(
  ({ $tone = 'default' }) => {
    const variantMap: Record<StatusToneKey, TagVariant> = {
      success: 'success',
      info: 'info',
      warning: 'warning',
      default: 'neutral',
    };
    return {
      variant: variantMap[$tone],
      borderless: true,
    };
  }
)<{ $tone?: StatusToneKey }>``;

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
  font-size: ${DESIGN_TOKENS.FONT_SIZE.XS}px;
  color: var(--color-text-secondary);
`;

export const LoadingState = styled.div`
  /* No inline styles needed - LoadingWrapper handles all styling */
`;

export const StyledRediaccEmpty = styled.div`
  margin-top: ${({ theme }) => theme.spacing.XXL * 3.75}px;
`;
