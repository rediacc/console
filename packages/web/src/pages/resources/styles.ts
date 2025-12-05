import styled from 'styled-components';
import { Card, Breadcrumb, Typography } from 'antd';
import { PageContainer, SectionStack, SectionHeaderRow } from '@/styles/primitives';

export const PageWrapper = styled(PageContainer)`
  height: 100%;
`;

export const FullHeightCard = styled(Card)`
  height: 100%;
  display: flex;
  flex-direction: column;
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

export const TitleRow = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.MD}px;
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`;

const { Title } = Typography;

export const HeaderTitleText = styled(Title)`
  && {
    margin: 0;
  }
`;

export const TagRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const ActionsRow = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.SM}px;
  flex-wrap: wrap;
  justify-content: flex-end;
`;

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
  min-width: 300px;
  transition: width 0.3s ease-in-out;
`;

export const DetailBackdrop = styled.div<{ $right: number; $visible: boolean }>`
  position: fixed;
  top: 0;
  left: 0;
  right: ${({ $right }) => `${$right}px`};
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.4);
  opacity: ${({ $visible }) => ($visible ? 1 : 0)};
  transition: opacity 250ms ease-in-out, right 0.3s ease-in-out;
  z-index: ${({ theme }) => theme.zIndex.MODAL};
  pointer-events: ${({ $visible }) => ($visible ? 'auto' : 'none')};
`;

export const CenteredState = styled.div`
  text-align: center;
  padding: ${({ theme }) => theme.spacing['6']}px 0;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const ErrorWrapper = styled.div`
  max-width: 480px;
  margin: 0 auto;
`;
