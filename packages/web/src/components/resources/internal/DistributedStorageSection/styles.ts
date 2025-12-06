import styled, { css } from 'styled-components';
import { Alert, Button, Card, Divider, Typography } from 'antd';
import { ContentStack, ActionsRow } from '@/components/common/styled';

const { Text } = Typography;

export { ContentStack, ActionsRow };

export const SectionDivider = styled(Divider)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.LG}px;
    border-color: ${({ theme }) => theme.colors.borderSecondary};
  }
`;

export const DividerContent = styled.div`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const SectionTitle = styled.span`
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const SectionCard = styled(Card)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }
`;

export const AssignmentLabel = styled(Text)`
  && {
    display: block;
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const AlertWrapper = styled(Alert)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    padding: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const AlertMessage = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`;

const actionButtonStyles = css`
  && {
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

export const ActionButton = styled(Button).attrs({
  size: 'small',
})`
  ${actionButtonStyles}
`;

export const ButtonLabel = styled.span`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`;

export { LoadingState } from '@/styles/primitives';
