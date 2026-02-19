import React from 'react';
import { Flex, Typography } from 'antd';

interface BrandMarkProps {
  logoSrc: string;
  iconSrc?: string;
  logoAlt: string;
  onClick?: () => void;
  showText?: boolean;
  logoSize?: number;
  textSize?: number;
  className?: string;
  leading?: React.ReactNode;
  text?: string;
  dataTestId?: string;
}

const BrandMark: React.FC<BrandMarkProps> = ({
  logoSrc,
  iconSrc,
  logoAlt,
  onClick,
  showText = true,
  logoSize = 36,
  textSize = 24,
  className,
  leading,
  text = 'rediacc',
  dataTestId = 'shared-brand-mark',
}) => {
  const imageSrc = iconSrc ?? logoSrc;

  return (
    <Flex align="center" gap={8} className={className}>
      {leading}
      <Flex
        align="center"
        gap={10}
        className={onClick ? 'cursor-pointer select-none brand-mark' : 'select-none brand-mark'}
        onClick={onClick}
        data-testid={dataTestId}
      >
        <img
          src={imageSrc}
          alt={logoAlt}
          style={{ width: logoSize, height: logoSize }}
          className="object-contain"
        />
        {showText ? (
          <Typography.Text
            className="brand-mark-text"
            style={{ fontSize: textSize, lineHeight: 1, marginTop: -1 }}
          >
            {text}
          </Typography.Text>
        ) : null}
      </Flex>
    </Flex>
  );
};

export default BrandMark;
