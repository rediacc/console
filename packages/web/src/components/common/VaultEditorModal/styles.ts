import styled from 'styled-components';
import { InfoCircleOutlined, UploadOutlined, DownloadOutlined } from '@/utils/optimizedIcons';
import {
  ContentStack as BaseContentStack,
  ActionGroup as BaseActionGroup,
} from '@/components/common/styled';
import { RediaccButton } from '@/components/ui/Button';
import { RediaccTag } from '@/components/ui/Tag';
import { RediaccText } from '@/components/ui/Text';

export const ContentStack = BaseContentStack;

export const VersionBanner = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: ${({ theme }) => theme.spacing.SM}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  background-color: ${({ theme }) => theme.colors.bgSecondary};
`;

export const VersionLabel = styled(RediaccText).attrs({
  size: 'sm',
  weight: 'semibold',
})``;

export const VersionTag = styled(RediaccTag).attrs({
  size: 'sm',
})`
  && {
    margin: 0;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }
`;

export const VersionDescription = styled(RediaccText).attrs({
  size: 'xs',
  color: 'secondary',
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;

export const ValidationAlert = styled.div`
  padding: ${({ theme }) => theme.spacing.MD}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  border: 1px solid ${({ theme }) => theme.colors.error};
  background-color: ${({ theme }) => theme.colors.bgError};
  color: ${({ theme }) => theme.colors.error};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

export const ValidationTitle = styled(RediaccText).attrs({
  weight: 'semibold',
})`
  && {
    display: block;
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const ValidationList = styled.ul`
  margin: 0;
  padding-left: ${({ theme }) => theme.spacing.LG}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const FooterWrapper = styled.div`
  margin-top: ${({ theme }) => theme.spacing.MD}px;
`;

export const FooterBar = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.MD}px;
  flex-wrap: wrap;
`;

export const FileActions = BaseActionGroup;
export const ActionGroup = BaseActionGroup;

export const FileActionButton = styled(RediaccButton).attrs({
  size: 'sm',
})`
  && {
    min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT_SM}px;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  }
`;

export const UnsavedChangesText = styled.span`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
  color: ${({ theme }) => theme.colors.warning};
  font-size: ${({ theme }) => theme.fontSize.XS}px;
`;

export const UnsavedVersionHint = styled(RediaccText).attrs({
  size: 'xs',
  color: 'secondary',
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;

export const WarningIcon = styled(InfoCircleOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
`;

export const UploadIcon = styled(UploadOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
`;

export const DownloadIcon = styled(DownloadOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
`;
