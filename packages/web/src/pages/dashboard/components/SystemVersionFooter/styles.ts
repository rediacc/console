import { ClockCircleOutlined, CloudServerOutlined, DesktopOutlined } from '@ant-design/icons';
import styled from 'styled-components';
import { InlineStack } from '@/components/common/styled';
import { RediaccTag } from '@/components/ui';
import { FlexRow } from '@/styles/primitives';

// Use FlexRow from primitives
export const FooterContainer = styled(FlexRow).attrs({
  $justify: 'center',
  $wrap: true,
})`
`;

// Use InlineStack from common/styled
export const VersionItem = styled(InlineStack).attrs({ $align: 'center' })`
`;

export const Separator = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

export const EnvironmentTag = styled(RediaccTag)<{ $isProduction: boolean }>`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;

export const MutedIcon = styled.span`
  color: ${({ theme }) => theme.colors.textTertiary};
  display: flex;
  align-items: center;
`;

export const ConsoleIcon = styled(DesktopOutlined)`
  color: ${({ theme }) => theme.colors.textTertiary};
`;

export const ApiIcon = styled(CloudServerOutlined)`
  color: ${({ theme }) => theme.colors.textTertiary};
`;

export const UptimeIcon = styled(ClockCircleOutlined)`
  color: ${({ theme }) => theme.colors.textTertiary};
`;
