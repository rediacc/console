import styled from 'styled-components';
import { ActionGroup, ContentStack as BaseContentStack } from '@/components/common/styled';
import { RediaccButton, RediaccTag } from '@/components/ui';
import { DownloadOutlined, InfoCircleOutlined, UploadOutlined } from '@/utils/optimizedIcons';

export const ContentStack = BaseContentStack;

export const VersionBanner = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`;

// VersionLabel removed - use <RediaccText variant="label"> directly

export const VersionTag = styled(RediaccTag).attrs({
  size: 'sm',
})`
  && {
  }
`;

// VersionDescription removed - use <RediaccText variant="helper"> directly

export const ValidationAlert = styled.div`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

// ValidationTitle removed - use <RediaccText variant="title"> directly

export const ValidationList = styled.ul`
  display: flex;
  flex-direction: column;
`;

export const FooterWrapper = styled.div`
`;

export const FooterBar = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
`;

export const FileActions = ActionGroup;

export const FileActionButton = styled(RediaccButton)`
  && {
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
  }
`;

export const UnsavedChangesText = styled.span`
  display: flex;
  align-items: center;
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
`;
