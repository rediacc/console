import styled, { css } from 'styled-components';
import { Button, Tag, Typography } from 'antd';
import { InfoCircleOutlined, UploadOutlined, DownloadOutlined } from '@/utils/optimizedIcons';
import {
  ContentStack as BaseContentStack,
  ActionGroup as BaseActionGroup,
} from '@/components/common/styled';

const { Text } = Typography;

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

export const VersionLabel = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`;

export const VersionTag = styled(Tag)`
  && {
    margin: 0;
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }
`;

export const VersionDescription = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    color: ${({ theme }) => theme.colors.textSecondary};
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

export const ValidationTitle = styled(Text)`
  && {
    display: block;
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
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

const baseButtonStyles = css`
  min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT_SM}px;
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

export const FileActionButton = styled(Button)`
  && {
    ${baseButtonStyles}
  }
`;

export const CancelButton = styled(Button)`
  && {
    ${baseButtonStyles}
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`;

export const SaveButton = styled(Button)`
  && {
    ${baseButtonStyles}
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    background-color: ${({ theme }) => theme.colors.primary};
    border-color: ${({ theme }) => theme.colors.primary};

    &:hover,
    &:focus {
      background-color: ${({ theme }) => theme.colors.primaryHover};
      border-color: ${({ theme }) => theme.colors.primaryHover};
    }
  }
`;

export const UnsavedChangesText = styled.span`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
  color: ${({ theme }) => theme.colors.warning};
  font-size: ${({ theme }) => theme.fontSize.XS}px;
`;

export const UnsavedVersionHint = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    color: ${({ theme }) => theme.colors.textSecondary};
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
