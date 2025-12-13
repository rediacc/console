import styled from 'styled-components';
import { ActionGroup, ContentStack as BaseContentStack } from '@/components/common/styled';
import { RediaccButton, RediaccTag } from '@/components/ui';
import { borderedCard } from '@/styles/mixins';
import { DownloadOutlined, InfoCircleOutlined, UploadOutlined } from '@/utils/optimizedIcons';

export const ContentStack = BaseContentStack;

export const VersionBanner = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: ${({ theme }) => theme.spacing.SM}px;
  ${borderedCard()}
  background-color: ${({ theme }) => theme.colors.bgSecondary};
`;

// VersionLabel removed - use <RediaccText variant="label"> directly

export const VersionTag = styled(RediaccTag).attrs({
  size: 'sm',
})`
  && {
    margin: 0;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }
`;

// VersionDescription removed - use <RediaccText variant="helper"> directly

export const ValidationAlert = styled.div`
  padding: ${({ theme }) => theme.spacing.MD}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  border: 1px solid ${({ theme }) => theme.colors.error};
  background-color: ${({ theme }) => theme.colors.bgError};
  color: ${({ theme }) => theme.colors.error};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

// ValidationTitle removed - use <RediaccText variant="title"> directly

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

export const FileActions = ActionGroup;

export const FileActionButton = styled(RediaccButton)`
  && {
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
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

// UnsavedVersionHint removed - use <RediaccText variant="helper"> directly

export const WarningIcon = styled(InfoCircleOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
`;

export const UploadIcon = styled(UploadOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
`;

export const DownloadIcon = styled(DownloadOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
`;

export const ValidationTitle = styled.div`
  display: block;
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
`;
