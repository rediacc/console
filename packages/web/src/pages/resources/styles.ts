import { Breadcrumb, Typography } from 'antd';
import styled from 'styled-components';
import { ActionsRow } from '@/components/common/styled';
import { RediaccCard } from '@/components/ui';
import { FlexRow, PageContainer, SectionHeaderRow, SectionStack } from '@/styles/primitives';

export const PageWrapper = styled(PageContainer)`
  height: 100%;
`;

export const BreadcrumbWrapper = styled(Breadcrumb)`
`;

export const HeaderSection = styled(SectionStack)`
`;

export const HeaderRow = styled(SectionHeaderRow)`
  align-items: flex-start;
`;

export const TitleColumn = styled.div`
  flex: 1 1 auto;
  min-width: 0;
`;

export const TitleRow = styled(FlexRow).attrs({})`
`;

const { Title } = Typography;

export const HeaderTitleText = styled(Title)`
  && {
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
`;

export const DetailBackdrop = styled.div<{ $right: number; $visible: boolean }>`
  position: fixed;
  top: 0;
  left: 0;
  right: ${({ $right }) => `${$right}px`};
  bottom: 0;
  background-color: #404040;
  display: ${({ $visible }) => ($visible ? 'block' : 'none')};
  z-index: ${({ theme }) => theme.zIndex.MODAL};
  pointer-events: ${({ $visible }) => ($visible ? 'auto' : 'none')};
`;

export const ErrorWrapper = styled.div`
  max-width: ${({ theme }) => theme.dimensions.ERROR_WRAPPER_WIDTH}px;
`;

export const FlexColumnCard = styled(RediaccCard)`
  display: flex;
  flex-direction: column;
`;
