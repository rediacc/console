import styled from 'styled-components';
import { Select, Typography, Space } from 'antd';
import { LoadingOutlined, ApiOutlined, DeleteOutlined } from '@/utils/optimizedIcons';

const { Text: AntText } = Typography;

export const StyledSelect = styled(Select)`
  && .ant-select-selector {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    padding: ${({ theme }) => `${theme.spacing.XS}px ${theme.spacing.SM}px`};
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
    display: flex;
    align-items: center;
  }

  && .ant-select-selection-item {
    display: flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    line-height: 1.5;
  }
  
  && .ant-select-arrow {
    display: flex;
    align-items: center;
    height: 100%;
  }

  && .ant-select-item-option-content {
    display: flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const SelectorWrapper = styled.div`
  display: inline-block;
  width: 100%;
`;

export const EndpointSuffixIcon = styled(ApiOutlined)`
  font-size: ${({ theme }) => theme.fontSize.XL}px;
  align-self: flex-end;
`;

export const EndpointUrlText = styled.div`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  color: var(--color-text-tertiary);
  margin-top: 0.5rem;
  text-align: center;
`;

export const LoadingText = styled(AntText)`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  opacity: 0.6;
`;

export const OptionWrapper = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  gap: 8px;
  margin-right: 20px;
`;

export const OptionLeft = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
`;

export const OptionRight = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
`;

export const HealthIndicator = styled.span<{ $isHealthy: boolean; $isChecking?: boolean }>`
  font-size: 10px;
  color: ${({ $isHealthy, $isChecking }) =>
    $isChecking ? 'var(--color-warning)' : $isHealthy ? 'var(--color-success)' : 'var(--color-error)'};
`;

export const EndpointName = styled.span<{ $disabled?: boolean }>`
  opacity: ${({ $disabled }) => ($disabled ? 0.5 : 1)};
  display: flex;
`;

export const EndpointNameText = styled.p`
  margin-top: 0;
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  max-width: 120px;
  margin-bottom: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-primary);
`;

export const VersionLabel = styled.span`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  color: var(--color-text-quaternary);
  opacity: 0.7;
`;

export const EmojiIcon = styled.span`
  font-size: 16px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji', sans-serif;
  margin-right: 4px;
`;

export const LabelContent = styled.span`
  display: flex;
  align-items: center;
  gap: 6px;
`;

export const DeleteEndpointIcon = styled(DeleteOutlined)`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  color: ${({ theme }) => theme.colors.error};
  cursor: pointer;
`;

export const AddCustomOption = styled.span`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  color: var(--color-primary);
`;

export const CheckingSpinner = styled(LoadingOutlined)`
  font-size: 10px;
  color: var(--color-warning);
`;

export const SpinnerWrapper = styled.span`
  margin-left: ${({ theme }) => theme.spacing.SM}px;
  display: inline-flex;
  align-items: center;
`;

export const FormActions = styled(Space)`
  && {
    width: 100%;
    justify-content: flex-end;
  }
`;
