import styled from 'styled-components';
import { RediaccTag, RediaccText } from '@/components/ui';

export const SmallText = styled(RediaccText)`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
`;

export const GrandTag = styled(RediaccTag)`
  margin-left: ${({ theme }) => theme.spacing.XS}px;
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  border: none;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const InlineTag = styled(RediaccTag)`
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  border: none;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const MachineTag = styled(InlineTag)`
  margin-left: ${({ theme }) => theme.spacing.XS}px;
`;

export const InfoTag = styled(InlineTag)`
  margin-right: ${({ theme }) => theme.spacing.XS}px;
`;

export const ModalContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
`;

export const ConfirmationInput = styled.input`
  width: 100%;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
  padding: ${({ theme }) => theme.spacing.SM}px;
  border: 1px solid ${({ theme }) => theme.colors.borderPrimary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  background-color: ${({ theme }) => theme.colors.inputBg};
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const TableStateContainer = styled.div`
  padding: ${({ theme }) => theme.spacing.LG}px;
`;
