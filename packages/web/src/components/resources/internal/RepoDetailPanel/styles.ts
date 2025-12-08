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
  font-size: ${({ theme }) => theme.fontSize.XXXXXXL}px;
  color: var(--color-success);
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
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const SectionDivider = styled(BaseSectionDivider)`
  && {
    margin: ${({ theme }) => `${theme.spacing.XL}px 0`};
  }
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const Section = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`;

type StackGap = 'XS' | 'SM' | 'MD' | 'LG' | 'XL';

export const Stack = styled.div<{ $gap?: StackGap }>`
  display: flex;
  flex-direction: column;
  width: 100%;
  gap: ${({ theme, $gap = 'SM' }) => theme.spacing[$gap]}px;
`;

export const SectionHeader = styled(BaseSectionHeader)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
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
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }
`;

export const VolumeDescription = styled.div`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const VolumeList = styled.ul`
  margin: ${({ theme }) => `${theme.spacing.SM}px 0`};
  padding-left: ${({ theme }) => theme.spacing.LG}px;
`;

export const ServicesList = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
  width: 100%;
`;

export const ServiceCard = styled(RediaccCard)<{ $state: 'active' | 'failed' | 'other' }>`
  && {
    border-left: 4px solid
      ${({ $state }) => {
        switch ($state) {
          case 'active':
            return 'var(--color-success)';
          case 'failed':
            return 'var(--color-error)';
          default:
            return 'var(--color-border-secondary)';
        }
      }};
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
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
  gap: ${({ theme }) => theme.spacing.MD}px;
`;

export const ServiceMetaItem = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export { SectionCard as PathsCard };

export { SectionCard as ActivityCard };

export const ActivityMetrics = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;
