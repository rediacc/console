import { Typography } from 'antd';
import styled from 'styled-components';
import { RediaccSelect } from '@/components/ui';
import { FlexRow } from '@/styles/primitives';
import { ApiOutlined, DeleteOutlined, LoadingOutlined } from '@/utils/optimizedIcons';

const { Text: AntText } = Typography;

export const StyledSelect = styled(RediaccSelect)`
  && .ant-select-selector {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    display: flex;
    align-items: center;
  }

  && .ant-select-selection-item {
    display: flex;
    align-items: center;
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
  text-align: center;
`;

export const LoadingText = styled(AntText)`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

// Use FlexRow from primitives
export const OptionWrapper = styled(FlexRow).attrs({ $justify: 'space-between' })`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
`;

// Use FlexRow from primitives
export const OptionLeft = styled(FlexRow)``;

// Use FlexRow from primitives
export const OptionRight = styled(FlexRow)`
`;

export const HealthIndicator = styled.span<{ $isHealthy: boolean; $isChecking?: boolean }>`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
`;

export const EndpointName = styled.span<{ $disabled?: boolean }>`
  color: ${({ $disabled, theme }) => ($disabled ? theme.colors.textTertiary : theme.colors.textPrimary)};
  display: flex;
`;

export const EndpointNameText = styled.p`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-primary);
`;

export const VersionLabel = styled.span`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  color: ${({ theme }) => theme.colors.textTertiary};
`;

export const EmojiIcon = styled.span`
  font-size: ${({ theme }) => theme.fontSize.MD}px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji', sans-serif;
`;

// Use FlexRow from primitives
export const LabelContent = styled(FlexRow)``;

export const DeleteEndpointIcon = styled(DeleteOutlined)`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
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
  display: inline-flex;
  align-items: center;
`;
