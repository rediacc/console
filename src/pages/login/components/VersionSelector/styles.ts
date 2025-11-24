import styled from 'styled-components';
import { Select, Typography } from 'antd';

const { Text: AntText } = Typography;

export const StyledSelect = styled(Select)`
  .ant-select-selector {
    font-size: ${({ theme }) => theme.fontSize.XS}px !important;
  }

  .ant-select-selection-item {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  
  .ant-select-item-option-content {
    display: flex;
    align-items: center;
  }
`;

export const VersionText = styled(AntText)`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  opacity: 0.6;
`;

export const OptionContent = styled.span`
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: ${({ theme }) => theme.fontSize.XS}px;
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
