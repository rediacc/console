import styled from 'styled-components';
import { ContentStack, ActionsRow } from '@/components/common/styled';
import {
  RediaccButton,
  RediaccText,
  RediaccCard,
  RediaccAlert,
  RediaccDivider,
} from '@/components/ui';

export { ContentStack, ActionsRow };

export const SectionDivider = styled(RediaccDivider)`
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

export const SectionCard = styled(RediaccCard)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }
`;

export const AssignmentLabel = styled(RediaccText).attrs({
  size: 'sm',
  weight: 'medium',
  color: 'secondary',
})`
  && {
    display: block;
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const AlertWrapper = styled(RediaccAlert)`
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

export const ActionButton = styled(RediaccButton).attrs({
  size: 'sm',
})`
  && {
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const ButtonLabel = styled(RediaccText).attrs({
  size: 'xs',
  weight: 'medium',
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;

export { LoadingState } from '@/styles/primitives';
