import { Breadcrumb, Typography } from 'antd';
import styled from 'styled-components';
import { ActionsRow } from '@/components/common/styled';
import { RediaccCard } from '@/components/ui';
import { FlexRow, PageContainer, SectionHeaderRow, SectionStack } from '@/styles/primitives';

export const PageWrapper = styled(PageContainer)`
  height: 100%;
`;

export const BreadcrumbWrapper = styled(Breadcrumb)`
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`;

export const HeaderSection = styled(SectionStack)`
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`;

export const HeaderRow = styled(SectionHeaderRow)`
  align-items: flex-start;
`;

export const TitleColumn = styled.div`
  flex: 1 1 auto;
  min-width: 0;
`;

export const TitleRow = styled(FlexRow).attrs({
  $gap: 'MD',
})`
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`;

const { Title } = Typography;

export const HeaderTitleText = styled(Title)`
  && {
    margin: 0;
  }
`;

export { ActionsRow };

export const SplitLayout = styled.div`
  display: flex;
  flex: 1;
  overflow: hidden;
  position: relative;
`;

export const ListPanel = styled.div<{ $detailWidth: number; $showDetail: boolean }>`
  width: ${({ $showDetail, $detailWidth }) => ($showDetail ? `calc(100% - ${$detailWidth}px)` : '100%')};
  height: 100%;
  overflow: auto;
  min-width: ${({ theme }) => theme.dimensions.SPLIT_PANEL_MIN_WIDTH}px;
  transition: width 0.3s ease-in-out;
`;

export const DetailBackdrop = styled.div<{ $right: number; $visible: boolean }>`
  position: fixed;
  top: 0;
  left: 0;
  right: ${({ $right }) => `${$right}px`};
  bottom: 0;
  background-color: ${({ theme }) => theme.overlays.backdrop};
  opacity: ${({ $visible }) => ($visible ? 1 : 0)};
  transition: opacity 250ms ease-in-out, right 0.3s ease-in-out;
  z-index: ${({ theme }) => theme.zIndex.MODAL};
  pointer-events: ${({ $visible }) => ($visible ? 'auto' : 'none')};
`;

export const ErrorWrapper = styled.div`
  max-width: ${({ theme }) => theme.dimensions.ERROR_WRAPPER_WIDTH}px;
  margin: 0 auto;
`;

export const FlexColumnCard = styled(RediaccCard)`
  display: flex;
  flex-direction: column;
`;
