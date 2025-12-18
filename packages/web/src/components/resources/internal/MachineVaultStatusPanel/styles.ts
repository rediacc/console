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
`;

export const TagRow = styled(TagGroup)`
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
  }
`;

export const QueueBadge = styled(RediaccBadge)`
  && .ant-badge-count {
  }
`;

export const TimestampWrapper = styled.div`
`;

export { SectionDivider, SectionHeader, SectionTitle };

export const SectionBlock = styled.div`
`;

export const InfoCard = styled(RediaccCard)`
  && {
  }
`;

export const MetricCard = styled(RediaccCard)`
  && {
  }
`;

export const CardHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`;

export const CardTitle = styled(Title)`
  && {
    font-size: ${DESIGN_TOKENS.FONT_SIZE.MD}px;
  }
`;

export const CardTagGroup = styled.div`
  display: flex;
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
  }
`;

export const StyledList = styled(RediaccList)`
  && {
  }
`;

export const ListCard = styled(RediaccCard)`
  && {
  }
`;

export const CardBodyStack = styled.div`
  display: flex;
  flex-direction: column;
`;

export const KeyValueRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`;

export const IndentedBlock = styled.div`
  display: flex;
  flex-direction: column;
`;

export const PartitionRow = styled.div`
  display: flex;
  align-items: center;
  font-size: ${DESIGN_TOKENS.FONT_SIZE.XS}px;
`;

export const LoadingState = styled.div`
  /* No inline styles needed - LoadingWrapper handles all styling */
`;

export const StyledRediaccEmpty = styled.div`
`;
