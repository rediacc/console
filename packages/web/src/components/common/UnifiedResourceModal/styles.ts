import styled from 'styled-components';
import { Checkbox, Collapse, Tag, Typography } from 'antd';
import { UploadOutlined, DownloadOutlined } from '@/utils/optimizedIcons';
import { StyledIcon, FlexColumn } from '@/styles/primitives';

const { Text } = Typography;

export const TitleStack = FlexColumn;

export const TitleText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.LG}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    line-height: ${({ theme }) => theme.lineHeight.TIGHT};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const SubtitleText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    margin-top: ${({ theme }) => theme.spacing.XS}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const SecondaryLabel = styled(Text)`
  && {
    margin-left: ${({ theme }) => theme.spacing.MD}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const FooterLeftActions = styled.div`
  margin-right: auto;
`;

export { ActionButton } from '@/styles/primitives';
export { PrimaryButton as PrimaryActionButton } from '@/styles/primitives';

export const UploadIcon = styled(StyledIcon).attrs({
  as: UploadOutlined,
  $size: 'SM',
})``;

export const DownloadIcon = styled(StyledIcon).attrs({
  as: DownloadOutlined,
  $size: 'SM',
})``;

export const AutoSetupCheckbox = styled(Checkbox)`
  && {
    margin-right: auto;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    display: flex;
    align-items: center;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
  }
`;

export const TemplateCollapse = styled(Collapse)`
  margin: ${({ theme }) => `${theme.spacing.MD}px 0`};
`;

export const SelectedTemplateTag = styled(Tag)`
  && {
    margin-left: ${({ theme }) => theme.spacing.SM}px;
  }
`;
