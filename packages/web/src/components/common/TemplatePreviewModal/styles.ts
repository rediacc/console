import { Typography } from 'antd';
import styled from 'styled-components';
import {
  RediaccText,
  RediaccAlert,
  RediaccList,
  RediaccTabs,
  RediaccTag,
} from '@/components/ui';
import {
  BaseModal,
  ContentCard,
  LoadingContainer,
  FlexColumn,
  FlexRow,
} from '@/styles/primitives';
import { borderedCard } from '@/styles/mixins';

const { Title } = Typography;

export const StyledModal = styled(BaseModal)`
  .ant-modal {
    top: 20px;
  }

  .ant-modal-body {
    height: calc(90vh - 180px);
    padding: ${({ theme }) => theme.spacing.MD}px;
  }
`;

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

// Use RediaccTag for consistent styling
export const DifficultyTag = styled(RediaccTag).attrs({
  size: 'md',
})`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    margin-top: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const StyledTabs = styled(RediaccTabs)`
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

// CardTitle removed - use <RediaccText variant="title"> directly

export const MarkdownContent = styled.div`
  color: ${({ theme }) => theme.colors.textPrimary};
  line-height: ${({ theme }) => theme.lineHeight.RELAXED};

  p {
    margin-bottom: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const FeatureText = styled(RediaccText)`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const CenteredLoadingContainer = styled(LoadingContainer)`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

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

export const FileListItem = styled(RediaccList.Item)<{ $active?: boolean }>`
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

export const FileName = styled(RediaccText).attrs({
  weight: 'medium',
})`
  && {
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

export const FilePath = styled(RediaccText)`
  && {
    font-family: monospace;
  }
`;

export const FilePreviewBody = styled.div`
  flex: 1 1 auto;
  overflow: auto;
  ${borderedCard('borderSecondary', 'MD')}
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

export const RoundedAlert = styled(RediaccAlert)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    padding: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const Checklist = styled.ul`
  margin-left: ${({ theme }) => theme.spacing.MD}px;
  padding-left: ${({ theme }) => theme.spacing.SM}px;
`;

export const ChecklistItem = styled.li`
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  color: ${({ theme }) => theme.colors.textPrimary};
  line-height: ${({ theme }) => theme.lineHeight.RELAXED};
`;

export const BodyParagraph = styled(RediaccText)`
  && {
    display: block;
    color: ${({ theme }) => theme.colors.textPrimary};
    line-height: ${({ theme }) => theme.lineHeight.RELAXED};
  }
`;

// BodyText removed - use <RediaccText variant="description"> directly

export const SecurityTitle = styled(Title).attrs({ level: 5 })`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const IconLabel = styled(FlexRow).attrs({ $gap: 'XS' })`
  display: inline-flex;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const SuccessIcon = styled(IconLabel)`
  color: ${({ theme }) => theme.colors.success};
`;

export const AlertDescription = styled(RediaccText).attrs({
  color: 'secondary',
})``;
