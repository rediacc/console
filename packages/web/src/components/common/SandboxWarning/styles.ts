import styled from 'styled-components';
import { InlineStack } from '@/components/common/styled';
import { RediaccAlert } from '@/components/ui';

export const SandboxBanner = styled(RediaccAlert)`
  && {
    position: fixed;
    top: 0;
    left: ${({ theme }) => theme.dimensions.SIDEBAR_WIDTH}px;
    right: 0;
    z-index: ${({ theme }) => theme.zIndex.NOTIFICATION};
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
`;

export const BannerMessage = styled(InlineStack)`
  text-align: center;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};

  .anticon {
    font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  }
`;
