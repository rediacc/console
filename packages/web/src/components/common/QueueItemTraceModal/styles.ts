import styled from 'styled-components';
import { RediaccButton, RediaccText, RediaccStack, RediaccCard } from '@/components/ui';
import {
  LargeModal,
  ModeSegmented as BaseModeSegmented,
  CenteredContent,
  NoMarginTitle as BaseNoMarginTitle,
  ScrollContainer as BaseScrollContainer,
  SectionMargin as BaseSectionMargin,
  CenteredFooter as BaseCenteredFooter,
  InfoList as BaseInfoList,
  CenteredRow as BaseCenteredRow,
  ModalTitleContainer as BaseModalTitleContainer,
  ModalTitleLeft as BaseModalTitleLeft,
  ModalTitleRight as BaseModalTitleRight,
  LastFetchedText as BaseLastFetchedText,
  ConsoleOutput,
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
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
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
    font-size: ${({ theme, $large }) => ($large ? theme.fontSize.SM : theme.fontSize.CAPTION)}px;
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
