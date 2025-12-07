import { Typography } from 'antd';
import styled from 'styled-components';
import { RediaccButton, RediaccText, RediaccCard, RediaccDivider } from '@/components/ui';

const { Title } = Typography;

const PANEL_WIDTH = 520;

const BasePanelWrapper = styled.div<{ $splitView?: boolean; $visible?: boolean }>`
  background-color: ${({ theme }) => theme.colors.bgPrimary};
  display: flex;
  flex-direction: column;
  height: 100%;
  ${({ $splitView, $visible = true, theme }) =>
    $splitView
      ? `
          position: relative;
          width: 100%;
        `
      : `
          position: fixed;
          top: 0;
          right: ${$visible ? 0 : -PANEL_WIDTH}px;
          bottom: 0;
          width: ${PANEL_WIDTH}px;
          max-width: 100vw;
          box-shadow: -2px 0 8px rgba(0, 0, 0, 0.15);
          transition: right ${theme.transitions.DEFAULT};
          z-index: ${theme.zIndex.MODAL};
        `}
`;

const BaseStickyHeader = styled.div`
  position: sticky;
  top: 0;
  z-index: 2;
  background-color: ${({ theme }) => theme.colors.bgPrimary};
  border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  padding: ${({ theme }) => `${theme.spacing.SM_LG}px ${theme.spacing.PAGE_CARD_PADDING}px`};
`;

const BaseContent = styled.div`
  padding: ${({ theme }) => theme.spacing.PAGE_CARD_PADDING}px;
`;

const InlineField = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.MD}px;
  width: 100%;
`;

const LabelText = styled(RediaccText).attrs({ size: 'xs', color: 'secondary' })`
  && {
    margin: 0;
    letter-spacing: ${({ theme }) => theme.letterSpacing.NORMAL};
  }
`;

const ValueText = styled(RediaccText).attrs({ size: 'sm' })`
  && {
    margin: 0;
    word-break: break-word;
  }
`;

const StrongValueText = styled(ValueText)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`;

const MonospaceValueText = styled(ValueText)`
  && {
    font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    letter-spacing: ${({ theme }) => theme.letterSpacing.TIGHT};
  }
`;

export const DetailPanelSurface = styled(BasePanelWrapper)`
  .ant-card {
    background-color: ${({ theme }) => theme.colors.bgSecondary};
    border-color: ${({ theme }) => theme.colors.borderSecondary};
  }
`;

export const DetailPanelHeader = styled(BaseStickyHeader)`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const DetailPanelHeaderRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  width: 100%;
`;

export const DetailPanelTitleGroup = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const DetailPanelTitle = styled(Title).attrs({ level: 4 })`
  && {
    margin: 0;
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const DetailPanelCollapseButton = styled(RediaccButton).attrs({ iconOnly: true })`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`;

export const DetailPanelTagGroup = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const DetailPanelBody = styled(BaseContent)`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
`;

export const DetailPanelSectionHeader = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const DetailPanelSectionTitle = styled(Title).attrs({ level: 5 })`
  && {
    margin: 0;
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const DetailPanelSectionCard = styled(RediaccCard).attrs({ size: 'sm' })`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    background-color: ${({ theme }) => theme.colors.bgSecondary};
    border-color: ${({ theme }) => theme.colors.borderSecondary};
  }
`;

export const DetailPanelFieldList = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
  width: 100%;
`;

export const DetailPanelFieldRow = styled(InlineField)`
  gap: ${({ theme }) => theme.spacing.SM}px;
  align-items: baseline;
  width: 100%;
`;

export const DetailPanelFieldLabel = styled(LabelText)<{ $minWidth?: number }>`
  min-width: ${({ $minWidth = 160 }) => `${$minWidth}px`};
  flex-shrink: 0;
`;

export const DetailPanelFieldValue = styled(ValueText)`
  word-break: break-word;
`;

export const DetailPanelFieldStrongValue = styled(StrongValueText)`
  word-break: break-word;
`;

export const DetailPanelFieldMonospaceValue = styled(MonospaceValueText)`
  word-break: break-word;
`;

export const DetailPanelDivider = styled(RediaccDivider)`
  && {
    margin: ${({ theme }) => `${theme.spacing.LG}px 0`};
  }
`;
