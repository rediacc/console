import styled from 'styled-components';
import { Space, Typography, Form } from 'antd';
import { SafetyCertificateOutlined } from '@/utils/optimizedIcons';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import { StyledIcon, NeutralStack, FlexRow } from '@/styles/primitives';
import { InlineStack } from '@/components/common/styled';
import { RediaccInput } from '@/components/ui/Form/Input';
import { RediaccAlert } from '@/components/ui';

type SpacingKey = keyof typeof DESIGN_TOKENS.SPACING;

export const LoadingContainer = styled.div`
  text-align: center;
  padding: ${({ theme }) => `${theme.spacing.XXXL}px 0`};
`;

export const FullWidthStack = styled(NeutralStack)<{ $gap?: SpacingKey }>`
  && {
    gap: ${({ theme, $gap = 'MD' }) => `${theme.spacing[$gap]}px`};
  }
`;

export const CenteredStack = styled(FullWidthStack)`
  text-align: center;
  align-items: center;
`;

const ICON_TONES = {
  primary: 'var(--color-primary)',
  success: 'var(--color-success)',
  muted: 'var(--color-text-quaternary)',
} as const;

export const StatusIcon = styled(StyledIcon).attrs<{
  $tone?: keyof typeof ICON_TONES;
  $size?: number;
}>(({ $tone = 'primary', $size }) => ({
  as: SafetyCertificateOutlined,
  $size: $size ?? DESIGN_TOKENS.FONT_SIZE.XXXXXXL,
  $color: ICON_TONES[$tone],
}))``;

export const SectionTitle = styled(Typography.Title)`
  && {
    margin-top: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const QRCodeContainer = styled.div`
  background-color: var(--color-bg-primary);
  padding: ${({ theme }) => theme.spacing.MD}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  border: 1px solid var(--color-border-secondary);
  display: inline-flex;
`;

export const ManualSetupAlert = styled(RediaccAlert)`
  width: 100%;
`;

export const SecretInputRow = styled(Space.Compact)`
  width: 100%;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const SecretInput = styled(RediaccInput)`
  && {
    font-family: 'SFMono-Regular', Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
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
    $gap: 'SM',
  })
)<{ $align?: 'space-between' | 'flex-end' }>`
  width: 100%;
`;

export const AlertSpacer = styled(RediaccAlert)`
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`;

export const CardContent = styled(FullWidthStack)`
  gap: ${({ theme }) => theme.spacing.MD}px;
`;

export const FormItemNoMargin = styled(Form.Item)`
  margin-bottom: 0;
`;

export const ModalTitleIcon = styled(StyledIcon).attrs({
  as: SafetyCertificateOutlined,
  $size: 'MD',
  $color: 'var(--color-primary)',
})``;

export const ModalTitleWrapper = styled(InlineStack).attrs({ as: 'span' })``;
