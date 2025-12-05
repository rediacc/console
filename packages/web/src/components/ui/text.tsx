/**
 * Text components
 *
 * Styled text variants:
 * - SecondaryText, LoadingHint, WarningNote
 * - DangerText, CaptionText
 */

import styled from 'styled-components';
import { Typography } from 'antd';

const { Text } = Typography;

export const SecondaryText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const LoadingHint = styled(Text)`
  && {
    display: block;
    margin-top: ${({ theme }) => theme.spacing.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const WarningNote = styled(Text)`
  && {
    display: block;
    margin-top: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const DangerText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.error};
  }
`;

export const CaptionText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;
