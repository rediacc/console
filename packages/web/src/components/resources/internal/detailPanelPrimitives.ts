import { Typography } from 'antd';
import styled from 'styled-components';
import { RediaccButton, RediaccCard, RediaccDivider, RediaccText } from '@/components/ui';

const { Title } = Typography;

const PANEL_WIDTH = 520;

const BasePanelWrapper = styled.div<{ $splitView?: boolean; $visible?: boolean }>`
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
          z-index: ${theme.zIndex.MODAL};
        `}
`;

const BaseStickyHeader = styled.div`
  position: sticky;
  top: 0;
  z-index: ${({ theme }) => theme.zIndex.STICKY};
`;

const BaseContent = styled.div`
`;

const InlineField = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
`;

export const DetailPanelSurface = styled(BasePanelWrapper)`
  .ant-card {
  }
`;

export const DetailPanelHeader = styled(BaseStickyHeader)`
  display: flex;
  flex-direction: column;
`;

export const DetailPanelHeaderRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
`;

export const DetailPanelTitleGroup = styled.div`
  display: flex;
  align-items: center;
`;

export const DetailPanelTitle = styled(Title).attrs({ level: 4 })`
  && {
  }
`;

export const DetailPanelCollapseButton = styled(RediaccButton).attrs({ iconOnly: true })`
  && {
  }
`;

export const DetailPanelTagGroup = styled.div`
  display: flex;
  flex-wrap: wrap;
`;

export const DetailPanelBody = styled(BaseContent)`
  display: flex;
  flex-direction: column;
`;

export const DetailPanelSectionHeader = styled.div`
  display: flex;
  align-items: center;
`;

export const DetailPanelSectionTitle = styled(Title).attrs({ level: 5 })`
  && {
  }
`;

export const DetailPanelSectionCard = styled(RediaccCard).attrs({ size: 'sm' })`
  && {
  }
`;

export const DetailPanelFieldList = styled.div`
  display: flex;
  flex-direction: column;
  width: 100%;
`;

export const DetailPanelFieldRow = styled(InlineField)`
  align-items: baseline;
  width: 100%;
`;

export const DetailPanelFieldLabel = styled(RediaccText).attrs({ variant: 'label' })<{
  $minWidth?: number;
}>`
  && {
    min-width: ${({ $minWidth = 160 }) => `${$minWidth}px`};
    flex-shrink: 0;
    letter-spacing: ${({ theme }) => theme.letterSpacing.NORMAL};
  }
`;

export const DetailPanelFieldValue = styled(RediaccText).attrs({ variant: 'value' })`
  && {
    word-break: break-word;
  }
`;

export const DetailPanelFieldStrongValue = styled(RediaccText).attrs({
  variant: 'value',
  weight: 'semibold',
})`
  && {
    word-break: break-word;
  }
`;

export const DetailPanelFieldMonospaceValue = styled(RediaccText).attrs({
  variant: 'value',
  code: true,
})`
  && {
    word-break: break-word;
  }
`;

export const DetailPanelDivider = styled(RediaccDivider).attrs({ spacing: 'lg' })``;
