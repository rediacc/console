import styled from 'styled-components';
import { Layout, Space, Button, Avatar, Typography } from 'antd';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

const { Header, Content } = Layout;
const { Text } = Typography;

export const HEADER_HEIGHT = DESIGN_TOKENS.DIMENSIONS.HEADER_HEIGHT;

export const MainLayoutContainer = styled(Layout)`
  min-height: 100vh;
`;

export const StyledHeader = styled(Header)<{ $isDark: boolean }>`
  padding: 0 ${({ theme }) => theme.spacing.LG}px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 2px 8px 0 rgba(0, 0, 0, 0.08);
  border-bottom: 1px solid var(--color-border-secondary);
  background-color: var(--color-bg-primary);
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: ${HEADER_HEIGHT}px;
  width: 100%;
  z-index: ${DESIGN_TOKENS.Z_INDEX.DROPDOWN + 1};
  transition: ${DESIGN_TOKENS.TRANSITIONS.DEFAULT};
  backdrop-filter: blur(8px);
`;

export const HeaderLeft = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.MD}px;
`;

export const HeaderRight = styled(Space)`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const MenuToggleButton = styled(Button)`
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: var(--color-text-primary);
  transition: all 0.2s ease;

  &:hover {
    background-color: var(--color-bg-tertiary);
    color: var(--color-primary);
  }
`;

export const LogoWrapper = styled.div`
  display: flex;
  align-items: center;
  cursor: pointer;
`;

export const Logo = styled.img`
  height: ${DESIGN_TOKENS.DIMENSIONS.ICON_LG}px;
  width: auto;
  object-fit: contain;
  margin-top: -${({ theme }) => theme.spacing.XS}px;
  margin-left: -${({ theme }) => theme.spacing.XS}px;
`;

export const UserMenuButton = styled(Button)`
  display: flex;
  align-items: center;
  justify-content: center;
`;

export const UserAvatar = styled(Avatar)`
  background: var(--color-primary-hover);
`;

export const StyledContent = styled(Content)<{ $marginLeft: number; $paddingTop: number }>`
  padding-top: ${({ $paddingTop }) => $paddingTop}px;
  margin-right: 0;
  margin-bottom: 0;
  margin-left: ${({ $marginLeft }) => $marginLeft}px;
  transition: margin-left 0.2s ease;
  min-height: 280px;
  position: relative;

  /* Remove sidebar margin on mobile */
  @media (max-width: 768px) {
    margin-left: 0 !important;
  }
`;

export const TransitionOverlay = styled.div`
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
`;

export const TransitionIcon = styled.div`
  font-size: ${DESIGN_TOKENS.FONT_SIZE.XXXXXXL}px;
  color: var(--color-primary);
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const TransitionText = styled(Text)`
  font-size: 18px;
  color: var(--color-text-secondary);
`;

export const ContentWrapper = styled.div`
  animation: fadeIn 0.3s ease-in;

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }
`;
