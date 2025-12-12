import styled from 'styled-components';
import { RediaccButton, RediaccCard, RediaccStack, RediaccText } from '@/components/ui';
import {
  CenteredFooter as BaseCenteredFooter,
  CenteredRow as BaseCenteredRow,
  InfoList as BaseInfoList,
  LastFetchedText as BaseLastFetchedText,
  ModalTitleContainer as BaseModalTitleContainer,
  ModalTitleLeft as BaseModalTitleLeft,
  ModalTitleRight as BaseModalTitleRight,
  ModeSegmented as BaseModeSegmented,
  NoMarginTitle as BaseNoMarginTitle,
  ScrollContainer as BaseScrollContainer,
  SectionMargin as BaseSectionMargin,
  CenteredContent,
  ConsoleOutput,
  LargeModal,
  TitleText,
} from '@/styles/primitives';

// Re-export from primitives
export const StyledModal = LargeModal;
export const ModeSegmented = BaseModeSegmented;

// Local styled components
export const CenteredMessage = CenteredContent;
export const NoMarginTitle = BaseNoMarginTitle;
export const SectionMargin = BaseSectionMargin;
export const CenteredFooter = BaseCenteredFooter;
export const SpacedCard = styled(RediaccCard).attrs({ spacing: 'default' })``;
export const InfoList = BaseInfoList;
export const CenteredRow = BaseCenteredRow;
export const ModalTitleContainer = BaseModalTitleContainer;
export const ModalTitleLeft = BaseModalTitleLeft;
export const ModalTitleRight = BaseModalTitleRight;
export const LastFetchedText = BaseLastFetchedText;

// SmallStatusTag removed - use <RediaccTag compact> or <RediaccTag size="sm"> directly

export const NoteWrapper = styled.div`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
`;

export const KeyInfoCard = styled.div`
  padding: ${({ theme }) => theme.spacing.SM}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  background: ${({ theme }) => theme.colors.bgSecondary};
`;

export const KeyInfoValue = styled(TitleText).attrs({ $level: 5 })``;

export const ItalicCaption = styled(RediaccText).attrs({ color: 'secondary' })`
  && {
    font-style: italic;
    display: block;
    text-align: center;
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;

// CodeText removed - use <RediaccText size="xs" code style={{ fontFamily: 'monospace' }}> directly

export const ScrollContainer = styled(BaseScrollContainer).attrs({ $maxHeight: 200 })`
  padding-right: ${({ theme }) => theme.spacing.XS}px;
`;

export const ScrollItem = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`;

export const ActionButton = styled(RediaccButton)<{ $bold?: boolean; $large?: boolean }>`
  && {
    font-weight: ${({ theme, $bold }) => ($bold ? theme.fontWeight.SEMIBOLD : theme.fontWeight.MEDIUM)};
    font-size: ${({ theme, $large }) => ($large ? theme.fontSize.SM : theme.fontSize.XS)}px;
  }
`;

// StatusText removed - use <RediaccText style={{ color, textTransform: 'capitalize' }}> directly

export const ConsoleOutputContainer = styled(ConsoleOutput).attrs({ $height: 400 })<{
  $theme: string;
}>``;

// Stack layout with full width
export const FullWidthSpace = styled(RediaccStack).attrs({
  variant: 'column',
  fullWidth: true,
})``;

// Card with bottom margin for spacing between sections
export const SpacedCardBottom = styled(RediaccCard).attrs({ spacing: 'default' })`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`;

// Compatibility status text with dynamic color based on status
type CompatibilityStatus = 'compatible' | 'warning' | 'incompatible' | 'unknown';

export const CompatibilityStatusText = styled(RediaccText)<{
  $status: CompatibilityStatus;
}>`
  && {
    color: ${({ $status }) => {
      switch ($status) {
        case 'compatible':
          return 'var(--color-success)';
        case 'warning':
          return 'var(--color-warning)';
        case 'incompatible':
          return 'var(--color-error)';
        default:
          return 'var(--color-info)';
      }
    }};
    text-transform: capitalize;
  }
`;

// Issues list with consistent margins
export const IssuesList = styled.ul`
  margin-top: ${({ theme }) => theme.spacing.XS}px;
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`;

// Recommendations list with top margin
export const RecommendationsList = styled.ul`
  margin-top: ${({ theme }) => theme.spacing.XS}px;
`;

// Monospace text for code/task IDs
export const MonospaceText = styled(RediaccText)`
  && {
    font-family: ${({ theme }) => theme.fontFamily.MONO};
  }
`;
