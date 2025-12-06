import styled from 'styled-components';
import { Collapse } from 'antd';
import { RediaccCheckbox as Checkbox } from '@/components/ui/Form';
import { RediaccText as Text } from '@/components/ui/Text';
import { RediaccTag } from '@/components/ui/Tag';
import { UploadOutlined, DownloadOutlined } from '@/utils/optimizedIcons';
import { StyledIcon, FlexColumn } from '@/styles/primitives';

export const TitleStack = FlexColumn;

export const TitleText = styled(Text).attrs({
  size: 'lg',
  weight: 'semibold',
})`
  && {
    line-height: ${({ theme }) => theme.lineHeight.TIGHT};
  }
`;

export const SubtitleText = styled(Text).attrs({
  size: 'sm',
  color: 'secondary',
})`
  && {
    margin-top: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const SecondaryLabel = styled(Text).attrs({
  color: 'secondary',
})`
  && {
    margin-left: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const FooterLeftActions = styled.div`
  margin-right: auto;
`;

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

export const SelectedTemplateTag = styled(RediaccTag)`
  && {
    margin-left: ${({ theme }) => theme.spacing.SM}px;
  }
`;
