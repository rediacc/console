import { Typography } from 'antd';
import styled from 'styled-components';
import { RediaccSelect } from '@/components/ui';
import { FlexRow } from '@/styles/primitives';
import { ApiOutlined, DeleteOutlined, LoadingOutlined } from '@/utils/optimizedIcons';

const { Text: AntText } = Typography;

export const StyledSelect = styled(RediaccSelect)`
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
    line-height: ${({ theme }) => theme.lineHeight.NORMAL};
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

// Use FlexRow from primitives
export const OptionWrapper = styled(FlexRow).attrs({ $justify: 'space-between', $gap: 'SM' })`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  margin-right: ${({ theme }) => theme.spacing.LG}px;
`;

// Use FlexRow from primitives
export const OptionLeft = styled(FlexRow).attrs({ $gap: 'SM' })``;

// Use FlexRow from primitives
export const OptionRight = styled(FlexRow).attrs({ $gap: 'SM' })`
  margin-left: auto;
`;

export const HealthIndicator = styled.span<{ $isHealthy: boolean; $isChecking?: boolean }>`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  color: ${({ $isHealthy, $isChecking }) =>
    $isChecking
      ? 'var(--color-warning)'
      : $isHealthy
        ? 'var(--color-success)'
        : 'var(--color-error)'};
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
  font-size: ${({ theme }) => theme.fontSize.MD}px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji', sans-serif;
  margin-right: ${({ theme }) => theme.spacing.XS}px;
`;

// Use FlexRow from primitives
export const LabelContent = styled(FlexRow).attrs({ $gap: 'SM' })``;

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
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  color: var(--color-warning);
`;

export const SpinnerWrapper = styled.span`
  margin-left: ${({ theme }) => theme.spacing.SM}px;
  display: inline-flex;
  align-items: center;
`;
