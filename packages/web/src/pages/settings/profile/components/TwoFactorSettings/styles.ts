import { Form, Space, Typography } from 'antd';
import styled from 'styled-components';
import { InlineStack } from '@/components/common/styled';
import { RediaccAlert, RediaccInput } from '@/components/ui';
import { FlexColumn, FlexRow, StyledIcon } from '@/styles/primitives';
import { SafetyCertificateOutlined } from '@/utils/optimizedIcons';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

export const CenteredStack = styled(FlexColumn)`
  && {
  }
  text-align: center;
  align-items: center;
`;

const ICON_TONES = {
  primary: 'var(--color-primary)',
  success: 'var(--color-success)',
  muted: 'var(--color-text-muted)',
} as const;

export const StatusIcon = styled(StyledIcon).attrs<{
  $tone?: keyof typeof ICON_TONES;
  $size?: number;
}>(({ $tone = 'primary', $size }) => ({
  as: SafetyCertificateOutlined,
  $size: $size ?? DESIGN_TOKENS.FONT_SIZE.DISPLAY,
  $color: ICON_TONES[$tone],
}))``;

export const SectionTitle = styled(Typography.Title)`
  && {
  }
`;

export const QRCodeContainer = styled.div`
  display: inline-flex;
`;

export const ManualSetupAlert = styled(RediaccAlert)`
  width: 100%;
`;

export const SecretInputRow = styled(Space.Compact)`
  width: 100%;
`;

export const SecretInput = styled(RediaccInput)`
  && {
    font-family: ${({ theme }) => theme.fontFamily.MONO};
  }
`;

export const CenteredCodeInput = styled(RediaccInput).attrs({
  centered: true,
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XL}px;
    letter-spacing: ${DESIGN_TOKENS.LETTER_SPACING.WIDE};
  }
`;

export const FormActionRow = styled(FlexRow).attrs<{ $align?: 'space-between' | 'flex-end' }>(
  ({ $align = 'flex-end' }) => ({
    $justify: $align,
  })
)<{ $align?: 'space-between' | 'flex-end' }>`
  width: 100%;
`;

export const CardContent = FlexColumn;

export const FormItemNoMargin = styled(Form.Item)`
`;

export const ModalTitleIcon = styled(StyledIcon).attrs({
  as: SafetyCertificateOutlined,
  $size: 'MD',
  $color: 'var(--color-primary)',
})``;

export const ModalTitleWrapper = styled(InlineStack).attrs({ as: 'span' })``;
