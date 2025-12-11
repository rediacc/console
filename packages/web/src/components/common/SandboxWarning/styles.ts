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
    border-radius: 0;
    border: none;
    border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    background-color: ${({ theme }) => theme.colors.bgWarning};
    color: ${({ theme }) => theme.colors.warning};
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_LG}px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
`;

export const BannerMessage = styled(InlineStack)`
  text-align: center;
  padding: ${({ theme }) => `${theme.spacing.XS}px 0`};
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};

  .anticon {
    font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  }
`;
