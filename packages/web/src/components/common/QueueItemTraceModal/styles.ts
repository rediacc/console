import styled from 'styled-components';
import {
  LargeModal,
  ModeSegmented as BaseModeSegmented,
  FullWidthSpace as BaseFullWidthSpace,
  CenteredContent,
  NoMarginTitle as BaseNoMarginTitle,
  ScrollContainer as BaseScrollContainer,
  SectionMargin as BaseSectionMargin,
  CenteredFooter as BaseCenteredFooter,
  SpacedCard as BaseSpacedCard,
  InfoList as BaseInfoList,
  CenteredRow as BaseCenteredRow,
  ModalTitleContainer as BaseModalTitleContainer,
  ModalTitleLeft as BaseModalTitleLeft,
  ModalTitleRight as BaseModalTitleRight,
  LastFetchedText as BaseLastFetchedText,
  ConsoleOutput,
  ItalicText,
  TitleText,
} from '@/styles/primitives';
import { RediaccText as Text, RediaccTag, RediaccAlert } from '@/components/ui';
import { RediaccButton } from '@/components/ui/Button';

// Re-export from primitives
export const StyledModal = LargeModal;
export const ModeSegmented = BaseModeSegmented;

// Local styled components
export const SpacedAlert = styled(RediaccAlert)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`;
export const FullWidthSpace = BaseFullWidthSpace;
export const CenteredMessage = CenteredContent;
export const NoMarginTitle = BaseNoMarginTitle;
export const SectionMargin = BaseSectionMargin;
export const CenteredFooter = BaseCenteredFooter;
export const SpacedCard = BaseSpacedCard;
export const InfoList = BaseInfoList;
export const CenteredRow = BaseCenteredRow;
export const ModalTitleContainer = BaseModalTitleContainer;
export const ModalTitleLeft = BaseModalTitleLeft;
export const ModalTitleRight = BaseModalTitleRight;
export const LastFetchedText = BaseLastFetchedText;
export const SmallStatusTag = styled(RediaccTag).attrs({
  size: 'sm',
})``;
export const CaptionText = styled(Text).attrs({
  variant: 'caption',
  color: 'muted',
})``;

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

export const ItalicCaption = styled(ItalicText)`
  && {
    display: block;
    text-align: center;
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  }
`;

export const CodeText = styled(Text).attrs({
  size: 'xs',
})`
  && {
    font-family: monospace;
  }
`;

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

export const StatusText = styled(Text)<{ $color?: string }>`
  && {
    color: ${({ $color, theme }) => $color || theme.colors.textPrimary};
    text-transform: capitalize;
  }
`;

export const ConsoleOutputContainer = styled(ConsoleOutput).attrs({ $height: 400 })<{
  $theme: string;
}>``;
