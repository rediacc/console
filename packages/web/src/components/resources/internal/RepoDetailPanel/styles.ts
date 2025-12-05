import styled from 'styled-components';
import { Tag, Empty, Card, Alert, Typography } from 'antd';
import { FolderOutlined } from '@/utils/optimizedIcons';
import {
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
  DetailPanelFieldMonospaceValue,
  DetailPanelSectionCard,
  DetailPanelDivider,
  DetailPanelSectionHeader,
  DetailPanelSectionTitle,
} from '../detailPanelPrimitives';

const { Text } = Typography;

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

export const PanelWrapper = DetailPanelSurface;
export const StickyHeader = DetailPanelHeader;
export const HeaderRow = DetailPanelHeaderRow;
export const HeaderTitleGroup = DetailPanelTitleGroup;
export const PanelTitle = DetailPanelTitle;
export const CollapseButton = DetailPanelCollapseButton;
export const TagRow = DetailPanelTagGroup;
export const ContentWrapper = DetailPanelBody;
export const InlineField = DetailPanelFieldRow;
export const LabelText = DetailPanelFieldLabel;
export const ValueText = DetailPanelFieldValue;
export const MonospaceValue = DetailPanelFieldMonospaceValue;
export const SectionCard = DetailPanelSectionCard;

export const HeaderIcon = styled(FolderOutlined)`
  font-size: ${({ theme }) => theme.fontSize.XXXXXXL}px;
  color: var(--color-success);
`;

export const StyledTag = styled(Tag)<{ $variant: keyof typeof TAG_VARIANTS }>`
  && {
    border: none;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
    font-weight: 500;
    background-color: ${({ $variant }) => TAG_VARIANTS[$variant].background};
    color: ${({ $variant }) => TAG_VARIANTS[$variant].color};
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const EmptyState = styled(Empty)`
  margin-top: ${({ theme }) => theme.spacing.XXXL}px;
`;

export const SectionDivider = styled(DetailPanelDivider)`
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

export const SectionHeader = styled(DetailPanelSectionHeader)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const SectionTitle = styled(DetailPanelSectionTitle)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`;

export const StatusTag = styled(Tag)<{ $tone?: keyof typeof STATUS_TONES }>`
  && {
    border: none;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    font-weight: 500;
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
    background-color: ${({ $tone = 'neutral' }) => STATUS_TONES[$tone]};
    color: ${({ $tone = 'neutral' }) => ($tone === 'neutral' ? 'var(--color-text-primary)' : 'var(--color-text-inverse)')};
  }
`;

export const AlertWrapper = styled(Alert)`
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

export const ServiceCard = styled(Card)<{ $state: 'active' | 'failed' | 'other' }>`
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

export const ServiceMetaLabel = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: var(--color-text-secondary);
  }
`;

export const ServiceMetaValue = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  }
`;

export const DiskUsageMeta = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: var(--color-text-secondary);
  }
`;

export const PathsCard = styled(SectionCard)``;

export const ActivityCard = styled(SectionCard)``;

export const ActivityMetrics = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;
