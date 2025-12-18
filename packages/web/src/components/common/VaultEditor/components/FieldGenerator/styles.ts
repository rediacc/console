import styled from 'styled-components';
import {
  RediaccButton,
  RediaccRadioButton,
  RediaccRadioGroup,
  RediaccStack,
} from '@/components/ui';
import { media } from '@/styles/mixins';

export const PopoverContainer = styled.div`
  width: ${({ theme }) => theme.dimensions.POPOVER_WIDTH}px;
  max-width: 100%;

  ${media.mobile`
    width: calc(100vw - 32px);
  `}
`;

export const OptionLabel = styled.label`
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  display: block;
`;

export const OptionGroup = styled(RediaccRadioGroup)`
  && {
    display: block;
  }
`;

export const OptionRadio = styled(RediaccRadioButton)`
  && {
    display: block;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const GeneratedValueCard = styled.div`
  display: flex;
  flex-direction: column;
`;

export const ValueHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`;

export const ValueContent = styled.div`
  word-break: break-all;
  max-height: ${({ theme }) => theme.dimensions.COMPACT_MAX_HEIGHT}px;
  overflow: auto;
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  line-height: ${({ theme }) => theme.lineHeight.NORMAL};
`;

export const ControlButton = styled(RediaccButton)`
  && {
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
  }
`;

export const GeneratorButton = styled(RediaccButton).attrs({
  iconOnly: true,
})`
  && {
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
    min-width: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
  }
`;

export const CopyButton = styled(RediaccButton)`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;

// Wrapper for icons with small dimensions
export const SmallIcon = styled.span`
  font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
  display: inline-flex;
  align-items: center;
`;

// Action stack with top margin
export const ActionStack = styled(RediaccStack)`
`;
