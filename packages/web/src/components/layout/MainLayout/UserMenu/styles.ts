import { Avatar, Segmented } from 'antd';
import styled from 'styled-components';
import { FlexBetween, InlineStack } from '@/components/common/styled';
import { RediaccButton, RediaccTag } from '@/components/ui';
import { FlexColumn } from '@/styles/primitives';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

export const MenuContainer = styled(FlexColumn).attrs({ $gap: 'MD' })`
  width: 320px;
  background-color: var(--color-bg-primary);
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  box-shadow: ${DESIGN_TOKENS.SHADOWS.XL};
  border: 1px solid var(--color-border-secondary);
  padding: ${({ theme }) => theme.spacing.MD}px;
`;

export const UserInfo = styled(InlineStack)``;

export const UserDetails = styled.div`
  flex: 1;
  min-width: 0;
`;

export const PlanBadge = styled(RediaccTag).attrs({ variant: 'primary', size: 'sm' })`
  && {
    margin-top: ${({ theme }) => theme.spacing.XS}px;
    font-size: ${DESIGN_TOKENS.FONT_SIZE.XS}px;
    font-weight: ${DESIGN_TOKENS.FONT_WEIGHT.SEMIBOLD};
    box-shadow: ${DESIGN_TOKENS.SHADOWS.BUTTON_DEFAULT};
  }
`;

export const ModeSegmented = styled(Segmented)`
  margin-top: ${({ theme }) => theme.spacing.XS}px;
  background: var(--color-bg-tertiary);
`;

export const AppearanceRow = styled(FlexBetween)``;

export const LanguageSection = styled.div``;

export const LogoutButton = styled(RediaccButton)`
  width: 100%;
  justify-content: flex-start;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const UserAvatar = styled(Avatar)`
  background-color: var(--color-text-tertiary);
`;
