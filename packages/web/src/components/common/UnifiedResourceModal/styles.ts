import { Collapse } from 'antd';
import styled from 'styled-components';
import { RediaccTag } from '@/components/ui';
import { RediaccCheckbox } from '@/components/ui/Form';
import { StyledIcon } from '@/styles/primitives';
import { DownloadOutlined, UploadOutlined } from '@/utils/optimizedIcons';

export const FooterLeftActions = styled.div`
`;

export const FooterRightActions = styled.div`
  display: flex;
  align-items: center;
`;

export const UploadIcon = styled(StyledIcon).attrs({
  as: UploadOutlined,
  $size: 'SM',
})``;

export const DownloadIcon = styled(StyledIcon).attrs({
  as: DownloadOutlined,
  $size: 'SM',
})``;

export const AutoSetupCheckbox = styled(RediaccCheckbox)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    display: flex;
    align-items: center;
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
  }
`;

export const TemplateCollapse = styled(Collapse)`
`;

export const SelectedTemplateTag = styled(RediaccTag)`
  && {
  }
`;
