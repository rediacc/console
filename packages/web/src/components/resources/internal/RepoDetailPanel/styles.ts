import styled from 'styled-components';
import { FolderOutlined } from '@/utils/optimizedIcons';
import { RediaccTag } from '@/components/ui/Tag';
import { RediaccText } from '@/components/ui/Text';
import { RediaccCard, RediaccAlert, RediaccEmpty } from '@/components/ui';
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
  FieldValueMonospace,
  SectionCard,
  SectionDivider as BaseSectionDivider,
  SectionHeader as BaseSectionHeader,
  SectionTitle as BaseSectionTitle,
} from '../sharedDetailPanelAliases';

export { PanelWrapper, PanelTitle, CollapseButton, ContentWrapper };

const TAG_VARIANTS = {
  team: {
    background: 'var(--color-success)',
    color: 'var(--color-text-inverse)',
  },
  machine: {
    background: 'var(--color-primary)',
    color: 'var(--color-text-inverse)',
  },
  version: {
    background: 'var(--color-bg-tertiary)',
    color: 'var(--color-text-primary)',
  },
} as const;

const STATUS_TONES = {
  success: 'var(--color-success)',
  warning: 'var(--color-warning)',
  error: 'var(--color-error)',
  info: 'var(--color-info)',
  neutral: 'var(--color-border-secondary)',
} as const;

export { Header, HeaderRow, TitleGroup, TagGroup, FieldRow, FieldLabel, FieldValue, FieldValueMonospace, SectionCard };

export const HeaderIcon = styled(FolderOutlined)`
  font-size: ${({ theme }) => theme.fontSize.XXXXXXL}px;
  color: var(--color-success);
`;

export const StyledTag = styled(RediaccTag).attrs<{ $variant: keyof typeof TAG_VARIANTS }>(
  ({ $variant }) => {
    const presetMap: Record<keyof typeof TAG_VARIANTS, string> = {
      team: 'team',
      machine: 'machine',
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

export const EmptyState = styled(RediaccEmpty)`
  margin-top: ${({ theme }) => theme.spacing.XXXL}px;
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

export const StatusTag = styled(RediaccTag).attrs<{ $tone?: keyof typeof STATUS_TONES }>(
  ({ $tone = 'neutral' }) => ({
    variant: $tone as any,
    borderless: true,
  })
)<{ $tone?: keyof typeof STATUS_TONES }>`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }
`;

export const AlertWrapper = styled(RediaccAlert)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
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

export const ServiceMetaLabel = styled(RediaccText).attrs({
  size: 'xs',
  color: 'secondary',
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  }
`;

export const ServiceMetaValue = styled(RediaccText).attrs({
  size: 'xs',
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  }
`;

export const DiskUsageMeta = styled(RediaccText).attrs({
  size: 'xs',
  color: 'secondary',
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  }
`;

export { SectionCard as PathsCard };

export { SectionCard as ActivityCard };

export const ActivityMetrics = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;
