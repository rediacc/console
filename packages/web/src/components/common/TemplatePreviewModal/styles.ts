import styled from 'styled-components';
import { Tabs, Space, Tag, Divider, List, Typography } from 'antd';
import {
  BaseModal,
  PrimaryButton,
  SecondaryButton,
  ContentCard,
  LoadingContainer as BaseLoadingContainer,
  LoadingText as BaseLoadingText,
  RoundedAlert as BaseRoundedAlert,
  FlexColumn,
  FlexRow,
  SecondaryText,
  MonoText,
  NoMarginTitle,
} from '@/styles/primitives';

const { Title, Text, Paragraph } = Typography;

export const StyledModal = styled(BaseModal)`
  .ant-modal {
    top: 20px;
  }

  .ant-modal-body {
    height: calc(90vh - 180px);
    padding: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const TitleStack = styled(FlexRow).attrs({ $gap: 'MD' })``;

export const TemplateAvatar = styled.img`
  width: ${({ theme }) => theme.dimensions.ICON_XXL}px;
  height: ${({ theme }) => theme.dimensions.ICON_XXL}px;
  object-fit: contain;
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  box-shadow: ${({ theme }) => theme.shadows.CARD};
`;

export const TemplateIconWrapper = styled.span`
  display: inline-flex;
  font-size: ${({ theme }) => theme.dimensions.ICON_XXL}px;
  color: ${({ theme }) => theme.colors.primary};
`;

export const TemplateHeading = styled(NoMarginTitle)``;

export const DifficultyTag = styled(Tag)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    margin-top: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const StyledTabs = styled(Tabs)`
  .ant-tabs-nav {
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const OverviewScroll = styled.div`
  height: calc(90vh - 340px);
  overflow: auto;
`;

export const DescriptionCard = styled(ContentCard)`
  .ant-card-body {
    max-height: calc(90vh - 420px);
    overflow: auto;
    padding: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const FeatureCard = DescriptionCard;

export const CardTitle = styled(Text)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const MarkdownContent = styled.div`
  color: ${({ theme }) => theme.colors.textPrimary};
  line-height: ${({ theme }) => theme.lineHeight.RELAXED};

  p {
    margin-bottom: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const FeatureList = styled(Space)`
  && {
    width: 100%;
  }
`;

export const FeatureItem = styled(Space)`
  && {
    width: 100%;
    align-items: center;
  }
`;

export const FeatureText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const LoadingContainer = styled(BaseLoadingContainer)`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const LoadingText = BaseLoadingText;

export const FilesLayout = styled(FlexRow).attrs({ $gap: 'MD' })`
  height: calc(90vh - 340px);
`;

export const FileListColumn = styled.div`
  width: 32%;
  height: 100%;
`;

export const FilePreviewColumn = styled.div`
  flex: 1 1 auto;
  height: 100%;
`;

export const FileListCard = styled(ContentCard)`
  && {
    height: 100%;
    display: flex;
    flex-direction: column;

    .ant-card-body {
      padding: 0;
      height: calc(100% - 44px);
    }
  }
`;

export const FileListItem = styled(List.Item)<{ $active?: boolean }>`
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
  cursor: pointer;
  background-color: ${({ theme, $active }) => ($active ? theme.colors.primaryBg : 'transparent')};
  border-left: 3px solid ${({ theme, $active }) => ($active ? theme.colors.primary : 'transparent')};
  transition: ${({ theme }) => theme.transitions.DEFAULT};

  &:hover {
    background-color: ${({ theme }) => theme.colors.bgHover};
  }
`;

export const FileMeta = styled(FlexColumn).attrs({ $gap: 'XS' })``;

export const FileName = styled(Text)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const FilePreviewCard = styled(ContentCard)`
  && {
    height: 100%;
    display: flex;
    flex-direction: column;

    .ant-card-body {
      padding: ${({ theme }) => theme.spacing.MD}px;
      display: flex;
      flex-direction: column;
      gap: ${({ theme }) => theme.spacing.SM}px;
    }
  }
`;

export const FilePreviewHeader = styled(Space)`
  && {
    align-items: center;
    justify-content: space-between;
  }
`;

export const FilePath = styled(MonoText)``;

export const FilePreviewBody = styled.div`
  flex: 1 1 auto;
  overflow: auto;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
`;

export const SecurityScroll = styled.div`
  height: calc(90vh - 340px);
  overflow: auto;
`;

export const SecurityCard = styled(ContentCard)`
  .ant-card-body {
    padding: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const AlertStack = styled(FlexColumn).attrs({ $gap: 'MD' })``;

export const RoundedAlert = BaseRoundedAlert;

export const Checklist = styled.ul`
  margin-left: ${({ theme }) => theme.spacing.MD}px;
  padding-left: ${({ theme }) => theme.spacing.SM}px;
`;

export const ChecklistItem = styled.li`
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  color: ${({ theme }) => theme.colors.textPrimary};
  line-height: ${({ theme }) => theme.lineHeight.RELAXED};
`;

export const BodyParagraph = styled(Paragraph)`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};
    line-height: ${({ theme }) => theme.lineHeight.RELAXED};
  }
`;

export const BodyText = SecondaryText;

export const SectionDivider = styled(Divider)`
  && {
    margin: ${({ theme }) => `${theme.spacing.LG}px 0`};
  }
`;

export const SecurityTitle = styled(Title).attrs({ level: 5 })`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const PrimaryActionButton = styled(PrimaryButton)`
  && {
    min-width: 160px;
  }
`;

export const SecondaryActionButton = styled(SecondaryButton)`
  && {
    margin-right: ${({ theme }) => theme.spacing.SM}px;
    min-width: 120px;
  }
`;

export const IconLabel = styled(FlexRow).attrs({ $gap: 'XS' })`
  display: inline-flex;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const SuccessIcon = styled(IconLabel)`
  color: ${({ theme }) => theme.colors.success};
`;

export const AlertDescription = SecondaryText;
