import styled from 'styled-components';
import { Alert } from 'antd';

export const WarningAlert = styled(Alert)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border: 2px solid ${({ theme }) => theme.colors.error};
    background-color: ${({ theme }) => theme.colors.bgError};
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;

    .ant-alert-icon {
      color: ${({ theme }) => theme.colors.error};
      font-size: ${({ theme }) => theme.dimensions.ICON_LG}px;
    }

    .ant-alert-close-icon {
      color: ${({ theme }) => theme.colors.error};
    }
  }
`;

export const WarningTitle = styled.span`
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.error};
`;

export const WarningDescription = styled.div`
  color: ${({ theme }) => theme.colors.textSecondary};
  font-size: ${({ theme }) => theme.fontSize.SM}px;

  p {
    margin: 0 0 ${({ theme }) => theme.spacing.XS}px 0;
  }
`;

export const ResolutionText = styled.p`
  && {
    margin: ${({ theme }) => theme.spacing.XS}px 0 0 0;
    padding: ${({ theme }) => theme.spacing.XS}px;
    background-color: ${({ theme }) => theme.colors.bgSecondary};
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;
