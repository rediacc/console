import styled from 'styled-components';
import { Tag, Typography } from 'antd';
import { FlexRow } from '@/styles/primitives';
import { InlineStack } from '@/components/common/styled';

const { Text } = Typography;

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

export const VersionLabel = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textMuted};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const VersionValue = styled(Text)`
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

export const EnvironmentTag = styled(Tag)<{ $isProduction: boolean }>`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    margin: 0;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }
`;

export const UptimeText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textMuted};
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;
