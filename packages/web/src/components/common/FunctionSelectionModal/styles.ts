import styled from 'styled-components';
import { ContentStack } from '@/components/common/styled';
import { RediaccAlert, RediaccTag, RediaccText } from '@/components/ui';
import { RediaccCard } from '@/components/ui';
import {
  RediaccInput,
  RediaccInputNumber,
  RediaccSearchInput,
  RediaccSelect,
} from '@/components/ui/Form';
import { focusRing, media } from '@/styles/mixins';
import { BaseModal, FlexColumn, FlexRow, scrollbarStyles } from '@/styles/primitives';
import { InfoCircleOutlined, QuestionCircleOutlined } from '@/utils/optimizedIcons';

export const StyledModal = styled(BaseModal)`
  .ant-modal-body {
  }
`;

export const FunctionListCard = RediaccCard;
export const ConfigCard = RediaccCard;

export const SearchInput = styled(RediaccSearchInput)`
  && {
  }
`;

export const FunctionList = styled.div`
  max-height: ${({ theme }) => theme.dimensions.LIST_MAX_HEIGHT}px;
  overflow: auto;
  ${scrollbarStyles}
`;

export const CategorySection = styled.div`
`;

// CategoryTitle removed - use <RediaccText variant="title"> directly

export const FunctionItemHeader = styled(FlexRow).attrs({})``;

export const FunctionOption = styled.button.attrs({ type: 'button' })<{
  $selected?: boolean;
}>`
  width: 100%;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
  text-align: left;
  font: inherit;

  &:hover {
  }

  &:focus-visible {
    ${focusRing('outline')}
  }
`;

export const QuickTaskTag = styled(RediaccTag).attrs({
  variant: 'warning',
  size: 'sm',
})`
  && {
  }
`;

// FunctionDescriptionText removed - use <RediaccText variant="description"> directly

export { ContentStack };

export const PushAlertsRow = styled.div<{ $hasWarning: boolean }>`
  display: grid;
  grid-template-columns: ${({ $hasWarning }) => ($hasWarning ? '1fr 0.8fr' : '1fr')};

  ${media.desktop`
    grid-template-columns: 1fr;
  `}
`;

export const PushAlertCard = styled(RediaccAlert)<{ $variant?: string }>`
  && {
    height: 100%;
  }
`;

// AlertBodyText removed - use <RediaccText variant="description"> directly

export const AlertLinkWrapper = styled.div`
`;

export const AlertLink = styled.a`
  font-size: ${({ theme }) => theme.fontSize.XS}px;

  &:hover {
  }
`;

export const LineageTag = styled(RediaccTag)<{ $variant: 'parent' | 'source' | 'destination' }>`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const LineageSeparator = styled(RediaccText).attrs({
  color: 'secondary',
})``;

export const HelpTooltipIcon = styled(InfoCircleOutlined)`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  cursor: help;
`;

export const PriorityHelpIcon = styled(QuestionCircleOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  cursor: pointer;
`;

export const SizeInputGroup = styled(FlexRow).attrs({})`
  width: 100%;
`;

export const SizeValueInput = styled(RediaccInputNumber)`
  && {
    flex: 1 1 65%;
  }
`;

export const SizeUnitSelect = styled(RediaccSelect)`
  && {
    flex: 0 0 35%;
  }
`;

export const CheckboxGroupStack = styled(FlexColumn).attrs({})``;

export const AdditionalOptionsInput = styled(RediaccInput)`
  && {
  }
`;

export const PriorityPopoverContent = styled.div`
  max-width: ${({ theme }) => theme.dimensions.POPOVER_WIDTH}px;
`;

// PriorityPopoverHeader removed - use <RediaccText variant="title"> directly

export const PriorityLegendRow = styled(FlexRow).attrs({})`
`;

export const PriorityLegendTag = styled(RediaccTag)<{ $level: number }>`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

// PriorityLegendText removed - use <RediaccText variant="description"> directly

export const PriorityTagWrapper = styled.div`
  text-align: center;
`;

export const PriorityStatusTag = styled(RediaccTag)<{ $priority: number }>`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

const RoundedAlert = styled(RediaccAlert)`
  && {
  }
`;

export const PriorityAlert = styled(RoundedAlert)`
  && {
  }
`;

export const PriorityAlertNote = styled.div`
`;

export const PriorityAlertDetail = styled.div`
  font-style: italic;
`;

export const CategoryTitleBlock = styled.div`
  display: block;
`;

export const PriorityLabelBlock = styled.div`
  display: block;
`;
