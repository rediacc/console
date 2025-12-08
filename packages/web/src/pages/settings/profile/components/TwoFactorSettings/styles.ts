import { Space, Typography, Form } from 'antd';
import styled from 'styled-components';
import { InlineStack } from '@/components/common/styled';
import { RediaccInput, RediaccAlert } from '@/components/ui';
import { StyledIcon, NeutralStack, FlexRow } from '@/styles/primitives';
import { SafetyCertificateOutlined } from '@/utils/optimizedIcons';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

type SpacingKey = keyof typeof DESIGN_TOKENS.SPACING;

export const CenteredStack = styled(NeutralStack)<{ $gap?: SpacingKey }>`
  && {
    gap: ${({ theme, $gap = 'MD' }) => `${theme.spacing[$gap]}px`};
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
  $size: $size ?? DESIGN_TOKENS.FONT_SIZE.XXXXXXL,
  $color: ICON_TONES[$tone],
}))``;

export const SectionTitle = styled(Typography.Title)`
  && {
    margin-top: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const QRCodeContainer = styled.div`
  background-color: ${({ theme }) => theme.colors.bgPrimary};
  padding: ${({ theme }) => theme.spacing.MD}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
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

export const CardContent = styled(NeutralStack)`
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
