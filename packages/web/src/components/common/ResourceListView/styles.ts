import styled, { css } from 'styled-components';
import { ActionGroup } from '@/components/common/styled';
import { RediaccButton, RediaccCard, RediaccStack } from '@/components/ui';
import { RediaccSearchInput } from '@/components/ui/Form';
import { media } from '@/styles/mixins';

export const ContainerCard = styled(RediaccCard)`
  && {
  }
`;

export const HeaderSection = styled.div`
`;

export const HeaderRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;

  ${media.tablet`
    flex-direction: column;
    align-items: stretch;
  `}
`;

export const ControlGroup = styled.div`
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  align-items: center;

  ${media.tablet`
    flex-direction: column;
    align-items: stretch;
    width: 100%;
  `}
`;

export const FiltersSlot = styled.div`
  display: flex;
  align-items: center;
`;

export const ActionsGroup = styled(ActionGroup)`
  ${media.tablet`
    width: 100%;
    justify-content: flex-end;
  `}
`;

export const SearchInput = styled(RediaccSearchInput)`
  && {
    width: ${({ theme }) => theme.dimensions.SEARCH_INPUT_WIDTH}px;
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
  }

  ${media.tablet`
    && {
      width: 100%;
    }
  `}
`;

export const EmptyDescriptionStack = styled(RediaccStack).attrs({
  direction: 'vertical',
  align: 'center',
})`
  text-align: center;
`;

// EmptyTitle removed - use <RediaccText variant="title"> directly

// EmptySubtitle removed - use <RediaccText variant="description"> directly

export const EmptyActions = styled(RediaccStack).attrs({
  direction: 'horizontal',
})`
  display: flex;
  justify-content: center;
`;

const actionButtonStyles = css`
  min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
`;

export const CreateButton = styled(RediaccButton)`
  && {
    ${actionButtonStyles};
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`;

export const RefreshButton = styled(RediaccButton).attrs({
  iconOnly: true,
})`
  && {
    ${actionButtonStyles};
  }
`;
