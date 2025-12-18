import { Avatar, Layout } from 'antd';
import styled from 'styled-components';
import { InlineStack } from '@/components/common/styled';
import { RediaccButton, RediaccText } from '@/components/ui';
import { media } from '@/styles/mixins';
import { FlexRow } from '@/styles/primitives';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

const { Header, Content } = Layout;

export const HEADER_HEIGHT = DESIGN_TOKENS.DIMENSIONS.HEADER_HEIGHT;

export const MainLayoutContainer = styled(Layout)`
  min-height: 100vh;
`;

export const StyledHeader = styled(Header)<{ $isDark: boolean }>`
  padding: 0 ${({ theme }) => theme.spacing.LG}px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: ${HEADER_HEIGHT}px;
  width: 100%;
  z-index: ${DESIGN_TOKENS.Z_INDEX.DROPDOWN + 1};
`;

export const HeaderLeft = styled(FlexRow).attrs({})``;

export const HeaderRight = styled(InlineStack)``;

export const MenuToggleButton = styled(RediaccButton)`
  && {
    width: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    font-size: ${({ theme }) => theme.fontSize.LG}px;
  }
`;

export const UserMenuButton = styled(RediaccButton)`
  && {
    width: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
  }
`;

export const LogoWrapper = styled(InlineStack)`
  cursor: pointer;
`;

export const Logo = styled.img`
  height: ${DESIGN_TOKENS.DIMENSIONS.ICON_LG}px;
  width: auto;
  object-fit: contain;
`;

export const UserAvatar = styled(Avatar)``;

export const StyledContent = styled(Content)<{
  $marginLeft: number;
  $paddingTop: number;
}>`
  padding-top: ${({ $paddingTop }) => $paddingTop}px;
  margin-left: ${({ $marginLeft }) => $marginLeft}px;
  min-height: ${({ theme }) => theme.dimensions.SIDEBAR_WIDTH}px;
  position: relative;

  /* Remove sidebar margin on mobile */
  ${media.mobile`
    margin-left: 0 !important;
  `}
`;

export const TransitionOverlay = styled.div`
  position: absolute;
  top: 50%;
  left: 50%;
  text-align: center;
`;

export const TransitionIcon = styled.div`
  font-size: ${DESIGN_TOKENS.FONT_SIZE.DISPLAY}px;
`;

export const TransitionText = styled(RediaccText)`
  font-size: ${({ theme }) => theme.fontSize.LG}px;
`;

export const ContentWrapper = styled.div`
`;
