import styled from 'styled-components';
import { Button } from 'antd';

export const TriggerButton = styled(Button)`
  && {
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const MenuLabel = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`;
