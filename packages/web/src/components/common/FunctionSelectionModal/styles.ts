import styled, { css } from 'styled-components';
import { ContentStack } from '@/components/common/styled';
import { RediaccAlert, RediaccTag, RediaccText } from '@/components/ui';
import {
  RediaccInput,
  RediaccInputNumber,
  RediaccSearchInput,
  RediaccSelect,
} from '@/components/ui/Form';
import { borderedCard, focusRing } from '@/styles/mixins';
import { BaseModal, ContentCard, FlexColumn, FlexRow, scrollbarStyles } from '@/styles/primitives';
import type { StyledTheme } from '@/styles/styledTheme';
import { InfoCircleOutlined, QuestionCircleOutlined } from '@/utils/optimizedIcons';

const resolvePriorityTokens = (priority: number, theme: StyledTheme) => {
  const configs: Record<number, { color: string; bg: string; border: string }> = {
    1: { color: theme.colors.error, bg: theme.colors.bgError, border: theme.colors.error },
    2: { color: theme.colors.warning, bg: theme.colors.bgWarning, border: theme.colors.warning },
    3: { color: theme.colors.info, bg: theme.colors.bgInfo, border: theme.colors.info },
    4: { color: theme.colors.primary, bg: theme.colors.primaryBg, border: theme.colors.primary },
  };
  return (
    configs[priority] || {
      color: theme.colors.success,
      bg: theme.colors.bgSuccess,
      border: theme.colors.success,
    }
  );
};

const resolveLineageTokens = (variant: 'parent' | 'source' | 'destination', theme: StyledTheme) => {
  const configs = {
    parent: { color: theme.colors.info, bg: theme.colors.bgInfo, border: theme.colors.info },
    source: {
      color: theme.colors.success,
      bg: theme.colors.bgSuccess,
      border: theme.colors.success,
    },
    destination: {
      color: theme.colors.primary,
      bg: theme.colors.primaryBg,
      border: theme.colors.primary,
    },
  };
  return configs[variant] || configs.destination;
};

export const StyledModal = styled(BaseModal)`
  .ant-modal-body {
    padding-top: ${({ theme }) => theme.spacing.LG}px;
  }
`;

export const FunctionListCard = ContentCard;
export const ConfigCard = ContentCard;

export const SearchInput = styled(RediaccSearchInput)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const FunctionList = styled.div`
  max-height: 400px;
  overflow: auto;
  padding: ${({ theme }) => theme.spacing.XS}px;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  ${borderedCard()}
  ${scrollbarStyles}
`;

export const CategorySection = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

// CategoryTitle removed - use <RediaccText variant="title"> directly

export const FunctionItemHeader = styled(FlexRow).attrs({ $gap: 'XS' })``;

export const FunctionOption = styled.button.attrs({ type: 'button' })<{
  $selected?: boolean;
}>`
  width: 100%;
  border: ${({ theme, $selected }) =>
    $selected ? `2px solid ${theme.colors.primary}` : `1px solid ${theme.colors.borderSecondary}`};
  background-color: ${({ theme, $selected }) =>
    $selected ? theme.colors.primaryBg : theme.colors.bgPrimary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
  min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
  transition: ${({ theme }) => theme.transitions.HOVER};
  text-align: left;
  font: inherit;
  color: inherit;

  &:hover {
    border-color: ${({ theme }) => theme.colors.primary};
    box-shadow: ${({ theme }) => theme.shadows.SM};
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
    margin-left: ${({ theme }) => theme.spacing.SM}px;
  }
`;

// FunctionDescriptionText removed - use <RediaccText variant="description"> directly

export { ContentStack };

export const PushAlertsRow = styled.div<{ $hasWarning: boolean }>`
  display: grid;
  grid-template-columns: ${({ $hasWarning }) => ($hasWarning ? '1fr 0.8fr' : '1fr')};
  gap: ${({ theme }) => theme.spacing.MD}px;
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;

  @media (max-width: 992px) {
    grid-template-columns: 1fr;
  }
`;

export const PushAlertCard = styled(RediaccAlert)<{ $variant?: string }>`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border-width: 1px;
    height: 100%;
  }

  ${({ theme, $variant }) =>
    $variant === 'info'
      ? css`
          border-color: ${theme.colors.info};
        `
      : css`
          border-color: ${theme.colors.warning};
        `}
`;

// AlertBodyText removed - use <RediaccText variant="description"> directly

export const AlertLinkWrapper = styled.div`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const AlertLink = styled.a`
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  color: ${({ theme }) => theme.colors.primary};

  &:hover {
    color: ${({ theme }) => theme.colors.primaryHover};
  }
`;

export const LineageTag = styled(RediaccTag)<{ $variant: 'parent' | 'source' | 'destination' }>`
  && {
    ${({ theme, $variant }) => {
      const tokens = resolveLineageTokens($variant, theme);
      return css`
        border-color: ${tokens.border};
        color: ${tokens.color};
        background-color: ${tokens.bg};
      `;
    }}
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const LineageSeparator = styled(RediaccText).attrs({
  color: 'secondary',
})``;

export const HelpTooltipIcon = styled(InfoCircleOutlined)`
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  color: ${({ theme }) => theme.colors.textSecondary};
  cursor: help;
`;

export const PriorityHelpIcon = styled(QuestionCircleOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  color: ${({ theme }) => theme.colors.primary};
  cursor: pointer;
`;

export const SizeInputGroup = styled(FlexRow).attrs({ $gap: 'SM' })`
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

export const CheckboxGroupStack = styled(FlexColumn).attrs({ $gap: 'XS' })``;

export const AdditionalOptionsInput = styled(RediaccInput)`
  && {
    margin-top: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const PriorityPopoverContent = styled.div`
  max-width: 400px;
`;

// PriorityPopoverHeader removed - use <RediaccText variant="title"> directly

export const PriorityLegendRow = styled(FlexRow).attrs({ $gap: 'SM' })`
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
`;

export const PriorityLegendTag = styled(RediaccTag)<{ $level: number }>`
  && {
    ${({ theme, $level }) => {
      const tokens = resolvePriorityTokens($level, theme);
      return css`
        background-color: ${tokens.bg};
        color: ${tokens.color};
        border-color: ${tokens.border};
      `;
    }}
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

// PriorityLegendText removed - use <RediaccText variant="description"> directly

export const PriorityTagWrapper = styled.div`
  text-align: center;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const PriorityStatusTag = styled(RediaccTag)<{ $priority: number }>`
  && {
    ${({ theme, $priority }) => {
      const tokens = resolvePriorityTokens($priority, theme);
      return css`
        background-color: ${tokens.bg};
        color: ${tokens.color};
        border-color: ${tokens.border};
      `;
    }}
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

const RoundedAlert = styled(RediaccAlert)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    padding: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const PriorityAlert = styled(RoundedAlert)`
  && {
    margin-top: ${({ theme }) => theme.spacing.LG}px;
  }
`;

export const PriorityAlertNote = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
`;

export const PriorityAlertDetail = styled.div`
  margin-top: ${({ theme }) => theme.spacing.XS}px;
  font-style: italic;
  color: ${({ theme }) => theme.colors.textSecondary};
`;
