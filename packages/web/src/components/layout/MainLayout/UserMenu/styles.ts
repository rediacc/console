import styled from 'styled-components';
import { Avatar, Badge, Typography, Button, Segmented, Divider } from 'antd';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import { FlexColumn } from '@/styles/primitives';
import { InlineStack, FlexBetween } from '@/components/common/styled';

const { Text } = Typography;

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

export const UserEmail = styled(Text)`
  display: block;
`;

export const CompanyName = styled(Text)`
  font-size: 12px;
  color: var(--color-text-secondary);
  display: block;
`;

export const PlanBadge = styled(Badge)`
  .ant-badge-count {
    background-color: var(--color-primary);
    font-size: ${DESIGN_TOKENS.FONT_SIZE.XS}px;
    font-weight: ${DESIGN_TOKENS.FONT_WEIGHT.SEMIBOLD};
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
    height: ${DESIGN_TOKENS.DIMENSIONS.ICON_MD}px;
    line-height: ${DESIGN_TOKENS.DIMENSIONS.ICON_MD}px;
    border-radius: ${({ theme }) => theme.borderRadius.XL}px;
    margin-top: ${({ theme }) => theme.spacing.XS}px;
    box-shadow: ${DESIGN_TOKENS.SHADOWS.BUTTON_DEFAULT};
  }
`;

export const MenuDivider = styled(Divider)`
  margin: 0;
`;

export const SectionLabel = styled(Text)`
  font-size: 12px;
  color: var(--color-text-secondary);
`;

export const ModeSegmented = styled(Segmented)`
  margin-top: ${({ theme }) => theme.spacing.XS}px;
  background: var(--color-bg-tertiary);
`;

export const AppearanceRow = styled(FlexBetween)``;

export const SectionTitle = styled(Text)`
  display: block;
`;

export const SectionDescription = styled(Text)`
  font-size: 12px;
  color: var(--color-text-secondary);
`;

export const LanguageSection = styled.div``;

export const LanguageTitle = styled(Text)`
  display: block;
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
`;

export const LogoutButton = styled(Button)`
  width: 100%;
  justify-content: flex-start;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const UserAvatar = styled(Avatar)`
  background-color: var(--color-text-tertiary);
`;
