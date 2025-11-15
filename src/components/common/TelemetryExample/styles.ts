import styled from 'styled-components'
import { BaseModal } from '@/styles/primitives'

export const PageContainer = styled.div`
  padding: ${({ theme }) => theme.spacing.XL}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
`

export const PageHeader = styled.header`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;

  h1 {
    margin: 0;
    color: ${({ theme }) => theme.colors.textPrimary};
  }

  p {
    margin: 0;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const ActionRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const TelemetryModal = styled(BaseModal)`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({ theme }) => theme.spacing.MD}px;
  }
`

export const ModalActions = styled.div`
  display: flex;
  justify-content: flex-end;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const UsageCard = styled.section`
  margin-top: ${({ theme }) => theme.spacing.XL}px;
  padding: ${({ theme }) => theme.spacing.LG}px;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};

  h3 {
    margin-top: 0;
    color: ${({ theme }) => theme.colors.textPrimary};
  }

  p {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const UsageList = styled.ul`
  padding-left: ${({ theme }) => theme.spacing.XL}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const UsageListItem = styled.li`
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;

  strong {
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`
