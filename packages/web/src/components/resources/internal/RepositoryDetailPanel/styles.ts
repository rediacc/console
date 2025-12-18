import styled from 'styled-components';
import {
  SectionDivider as BaseSectionDivider,
  SectionHeader as BaseSectionHeader,
  SectionTitle as BaseSectionTitle,
  CollapseButton,
  ContentWrapper,
  FieldLabel,
  FieldRow,
  FieldValue,
  FieldValueMonospace,
  Header,
  HeaderRow,
  PanelTitle,
  PanelWrapper,
  SectionCard,
  TagGroup,
  TitleGroup,
} from '@/components/resources/internal/sharedDetailPanelAliases';
import { RediaccCard, RediaccTag } from '@/components/ui';
import type { TagPreset, TagVariant } from '@/components/ui/Tag';
import { FolderOutlined } from '@/utils/optimizedIcons';

export { PanelWrapper, PanelTitle, CollapseButton, ContentWrapper };

type TagVariantKey = 'team' | 'machine' | 'version';
type StatusToneKey = 'success' | 'warning' | 'error' | 'info' | 'neutral';

export {
  Header,
  HeaderRow,
  TitleGroup,
  TagGroup,
  FieldRow,
  FieldLabel,
  FieldValue,
  FieldValueMonospace,
  SectionCard,
};

export const HeaderIcon = styled(FolderOutlined)`
  font-size: ${({ theme }) => theme.fontSize.DISPLAY}px;
`;

export const StyledTag = styled(RediaccTag).attrs<{ $variant: TagVariantKey }>(({ $variant }) => {
  const presetMap: Record<TagVariantKey, TagPreset | 'neutral'> = {
    team: 'team',
    machine: 'machine',
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

export const SectionDivider = styled(BaseSectionDivider)`
  && {
  }
  display: inline-flex;
  align-items: center;
`;

export const Section = styled.div`
`;

export const Stack = styled.div`
  display: flex;
  flex-direction: column;
  width: 100%;
`;

export const SectionHeader = styled(BaseSectionHeader)`
`;

export const SectionTitle = styled(BaseSectionTitle)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`;

export const StatusTag = styled(RediaccTag).attrs<{ $tone?: StatusToneKey }>(
  ({ $tone = 'neutral' }) => ({
    variant: $tone as TagVariant,
    borderless: true,
  })
)<{ $tone?: StatusToneKey }>`
  && {
  }
`;

export const VolumeDescription = styled.div`
  display: flex;
  flex-direction: column;
`;

export const VolumeList = styled.ul`
`;

export const ServicesList = styled.div`
  display: flex;
  flex-direction: column;
  width: 100%;
`;

export const ServiceCard = styled(RediaccCard)<{ $state: 'active' | 'failed' | 'other' }>`
  && {
  }
`;

export const ServiceHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`;

export const ServiceMetaGrid = styled.div`
  display: flex;
  flex-wrap: wrap;
`;

export const ServiceMetaItem = styled.div`
  display: flex;
  flex-direction: column;
`;

export { SectionCard as PathsCard };

export { SectionCard as ActivityCard };

export const ActivityMetrics = styled.div`
  display: flex;
  flex-direction: column;
`;

export const StyledRediaccEmpty = styled.div`
`;
