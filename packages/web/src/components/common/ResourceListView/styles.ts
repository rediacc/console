import styled, { css } from 'styled-components';
import { ActionGroup } from '@/components/common/styled';
import { RediaccButton, RediaccCard, RediaccStack } from '@/components/ui';
import { RediaccSearchInput } from '@/components/ui/Form';
import { media } from '@/styles/mixins';

export const ContainerCard = styled(RediaccCard)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.XL}px;
    border-color: ${({ theme }) => theme.colors.borderSecondary};
    box-shadow: ${({ theme }) => theme.shadows.CARD};
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }
`;

export const HeaderSection = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const HeaderRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.MD}px;

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
  gap: ${({ theme }) => theme.spacing.MD}px;

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
    min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
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
  gap: 'md',
})`
  text-align: center;
  padding: ${({ theme }) => theme.spacing.LG}px;
`;

// EmptyTitle removed - use <RediaccText variant="title"> directly

// EmptySubtitle removed - use <RediaccText variant="description"> directly

export const EmptyActions = styled(RediaccStack).attrs({
  direction: 'horizontal',
  gap: 'sm',
})`
  display: flex;
  justify-content: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

const actionButtonStyles = css`
  min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
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

export const TableWrapper = styled.div`
  /* Better scroll experience on mobile devices */
  @media (max-width: ${({ theme }) => theme.breakpoints.MOBILE}px) {
    -webkit-overflow-scrolling: touch;

    .ant-table-wrapper {
      overflow-x: auto;
    }

    .ant-table-pagination {
      flex-wrap: wrap;
      justify-content: center;
      gap: ${({ theme }) => theme.spacing.SM}px;

      .ant-pagination-total-text {
        flex-basis: 100%;
        text-align: center;
        margin-bottom: ${({ theme }) => theme.spacing.XS}px;
      }
    }
  }
`;
