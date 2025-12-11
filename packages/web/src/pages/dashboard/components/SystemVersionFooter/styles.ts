import styled from 'styled-components';
import {
  ClockCircleOutlined,
  CloudServerOutlined,
  DesktopOutlined,
} from '@ant-design/icons';
import { InlineStack } from '@/components/common/styled';
import { RediaccTag } from '@/components/ui';
import { FlexRow } from '@/styles/primitives';

// Use FlexRow from primitives
export const FooterContainer = styled(FlexRow).attrs({
  $gap: 'MD',
  $justify: 'center',
  $wrap: true,
})`
  padding: ${({ theme }) => theme.spacing.MD}px 0;
  margin-top: ${({ theme }) => theme.spacing.LG}px;
  border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
`;

// Use InlineStack from common/styled
export const VersionItem = styled(InlineStack).attrs({ $align: 'center' })`
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const Separator = styled.span`
  color: ${({ theme }) => theme.colors.borderSecondary};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

export const EnvironmentTag = styled(RediaccTag)<{ $isProduction: boolean }>`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    margin: 0;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }
`;

export const MutedIcon = styled.span`
  opacity: 0.5;
  display: flex;
  align-items: center;
`;

export const ConsoleIcon = styled(DesktopOutlined)`
  opacity: 0.5;
`;

export const ApiIcon = styled(CloudServerOutlined)`
  opacity: 0.5;
`;

export const UptimeIcon = styled(ClockCircleOutlined)`
  opacity: 0.5;
`;
