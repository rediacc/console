import { Typography } from 'antd';
import styled from 'styled-components';
import {
  RediaccAlert,
  RediaccCard,
  RediaccList,
  RediaccTabs,
  RediaccTag,
  RediaccText,
} from '@/components/ui';
import { borderedCard } from '@/styles/mixins';
import { BaseModal, FlexColumn, FlexRow, LoadingContainer } from '@/styles/primitives';

const { Title } = Typography;

export const StyledModal = styled(BaseModal)`
  .ant-modal {
    top: 20px;
  }

  .ant-modal-body {
    /* 180px = modal header(56) + modal footer(56) + modal padding(68) */
    height: calc(90vh - 180px);
  }
`;

export const TemplateAvatar = styled.img`
  width: ${({ theme }) => theme.dimensions.ICON_XXL}px;
  height: ${({ theme }) => theme.dimensions.ICON_XXL}px;
  object-fit: contain;
`;

export const TemplateIconWrapper = styled.span`
  display: inline-flex;
  font-size: ${({ theme }) => theme.dimensions.ICON_XXL}px;
`;

// Use RediaccTag for consistent styling
export const DifficultyTag = styled(RediaccTag).attrs({
  size: 'md',
})`
  && {
  }
`;

export const StyledTabs = styled(RediaccTabs)`
  .ant-tabs-nav {
  }
`;

export const OverviewScroll = styled.div`
  /* 340px = modal chrome(180) + tabs(48) + section header(60) + margins(52) */
  height: calc(90vh - 340px);
  overflow: auto;
`;

export const DescriptionCard = styled(RediaccCard)`
  .ant-card-body {
    /* 420px = modal chrome(180) + tabs(48) + card header(40) + section spacing(152) */
    max-height: calc(90vh - 420px);
    overflow: auto;
  }
`;

export const FeatureCard = DescriptionCard;

// CardTitle removed - use <RediaccText variant="title"> directly

export const MarkdownContent = styled.div`
  line-height: ${({ theme }) => theme.lineHeight.RELAXED};

  p {
  }
`;

export const FeatureText = styled(RediaccText)`
  && {
  }
`;

export const CenteredLoadingContainer = styled(LoadingContainer)`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
`;

export const FilesLayout = styled(FlexRow).attrs({})`
  /* 340px = modal chrome(180) + tabs(48) + section header(60) + margins(52) */
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

export const FileListCard = styled(RediaccCard)`
  && {
    height: 100%;
    display: flex;
    flex-direction: column;

    .ant-card-body {
      height: calc(100% - ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px);
    }
  }
`;

export const FileListItem = styled(RediaccList.Item)<{ $active?: boolean }>`
  cursor: pointer;

  &:hover {
  }
`;

export const FileMeta = styled(FlexColumn).attrs({})``;

export const FileName = styled(RediaccText).attrs({
  weight: 'medium',
})`
  && {
  }
`;

export const FilePreviewCard = styled(RediaccCard)`
  && {
    height: 100%;
    display: flex;
    flex-direction: column;

    .ant-card-body {
      display: flex;
      flex-direction: column;
    }
  }
`;

export const FilePath = styled(RediaccText)`
  && {
    font-family: ${({ theme }) => theme.fontFamily.MONO};
  }
`;

export const FilePreviewBody = styled.div`
  flex: 1 1 auto;
  overflow: auto;
  ${borderedCard()}
`;

export const SecurityScroll = styled.div`
  height: calc(90vh - 340px);
  overflow: auto;
`;

export const SecurityCard = styled(RediaccCard)`
  .ant-card-body {
  }
`;

export const AlertStack = styled(FlexColumn).attrs({})``;

export const RoundedAlert = styled(RediaccAlert)`
  && {
  }
`;

export const Checklist = styled.ul`
`;

export const ChecklistItem = styled.li`
  line-height: ${({ theme }) => theme.lineHeight.RELAXED};
`;

export const BodyParagraph = styled(RediaccText)`
  && {
    display: block;
    line-height: ${({ theme }) => theme.lineHeight.RELAXED};
  }
`;

// BodyText removed - use <RediaccText variant="description"> directly

export const SecurityTitle = styled(Title).attrs({ level: 5 })`
  && {
  }
`;

export const IconLabel = styled(FlexRow).attrs({})`
  display: inline-flex;
`;

export const SuccessIcon = styled(IconLabel)`
`;

export const AlertDescription = styled(RediaccText).attrs({
  color: 'secondary',
})``;

export const FullHeightList = styled.div`
  height: 100%;
`;
