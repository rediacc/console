import { Avatar, Segmented } from 'antd';
import styled from 'styled-components';
import { FlexBetween, InlineStack } from '@/components/common/styled';
import { RediaccButton, RediaccTag, RediaccText } from '@/components/ui';
import { FlexColumn } from '@/styles/primitives';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

export const MenuContainer = styled(FlexColumn).attrs({})`
  width: ${({ theme }) => theme.dimensions.DROPDOWN_WIDTH_MD}px;
  padding: ${({ theme }) => theme.spacing.MD}px;
`;

export const UserInfo = styled(InlineStack)``;

export const UserDetails = styled.div`
  flex: 1;
  min-width: 0;
`;

export const PlanBadge = styled(RediaccTag).attrs({ variant: 'primary', size: 'sm' })`
  && {
    font-size: ${DESIGN_TOKENS.FONT_SIZE.XS}px;
    font-weight: ${DESIGN_TOKENS.FONT_WEIGHT.SEMIBOLD};
  }
`;

export const ModeSegmented = styled(Segmented)``;

export const AppearanceRow = styled(FlexBetween)``;

export const LanguageSection = styled.div``;

export const LogoutButton = styled(RediaccButton)`
  width: 100%;
  justify-content: flex-start;
`;

export const UserAvatar = styled(Avatar)``;

export const BlockText = styled(RediaccText)`
  display: block;
`;

export const LanguageLabel = styled(RediaccText)`
  display: block;
`;
