import styled from 'styled-components';
import { RediaccTag } from '@/components/ui';
import { FlexRow } from '@/styles/primitives';
import { InlineStack } from '@/components/common/styled';
import { RediaccText } from '@/components/ui';

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

export const VersionLabel = styled(RediaccText)`
  && {
    color: ${({ theme }) => theme.colors.textMuted};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const VersionValue = styled(RediaccText)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
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

export const UptimeText = styled(RediaccText)`
  && {
    color: ${({ theme }) => theme.colors.textMuted};
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;
