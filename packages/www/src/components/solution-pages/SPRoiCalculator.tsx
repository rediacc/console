import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ADVANCED_SLIDERS,
  type CompanySize,
  computeRoi,
  formatCurrency,
  formatSliderValue,
  HERO_SLIDERS,
  ROI_DEFAULTS,
  type RoiInputs,
} from './roi-compute';
import { useLanguage } from '../../hooks/useLanguage';
import { useTranslation } from '../../i18n/react';
import '../../styles/newsletter.css';

interface RoiCalculatorContent {
  overline: string;
  title: string;
  description: string;
  sizeSelect: {
    label: string;
    smb: string;
    smbDesc: string;
    mid: string;
    midDesc: string;
    enterprise: string;
    enterpriseDesc: string;
    large: string;
    largeDesc: string;
  };
  sliders: Record<string, string>;
  advancedLabel: string;
  advancedSliders: Record<string, string>;
  summary: {
    annualSavings: string;
    paybackPeriod: string;
    paybackUnit: string;
    threeYearRoi: string;
  };
  categories: {
    tco: { title: string; currentTco: string; rediaccTco: string; savings: string };
    devProductivity: {
      title: string;
      hoursSaved: string;
      dollarValue: string;
      provisioningReduction: string;
    };
    drAvailability: {
      title: string;
      currentRisk: string;
      rediaccRisk: string;
      savings: string;
      rtoImprovement: string;
    };
    compliance: {
      title: string;
      storageSavings: string;
      bandwidthSavings: string;
      complianceSavings: string;
      insuranceSavings: string;
      auditTimeSaved: string;
    };
  };
  footnote: string;
}

interface Props {
  content: RoiCalculatorContent;
}

const SIZE_KEYS: CompanySize[] = ['smb', 'mid', 'enterprise', 'large'] as const;

const SPRoiCalculator: React.FC<Props> = ({ content }) => {
  const [activeSize, setActiveSize] = useState<CompanySize | null>('mid');
  const [values, setValues] = useState<RoiInputs>({ ...ROI_DEFAULTS.mid });
  const [detailsUnlocked, setDetailsUnlocked] = useState(false);
  const [gateEmail, setGateEmail] = useState('');
  const [gateLoading, setGateLoading] = useState(false);
  const [gateError, setGateError] = useState('');
  const gateInputRef = useRef<HTMLInputElement>(null);
  const gateViewedRef = useRef(false);
  const currentLang = useLanguage();
  const { t } = useTranslation(currentLang);

  const handleSizeSelect = useCallback((size: CompanySize) => {
    setActiveSize(size);
    setValues({ ...ROI_DEFAULTS[size] });
  }, []);

  const handleSliderChange = useCallback((id: string, val: number) => {
    setActiveSize(null);
    setValues((prev) => ({ ...prev, [id]: val }));
  }, []);

  const handleGateSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    const email = gateInputRef.current?.value.trim() || gateEmail.trim();
    if (!email) return;

    setGateLoading(true);
    setGateError('');
    try {
      const res = await fetch(
        `${window.location.origin}/account/api/v1/newsletter/lead-magnet`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, magnetName: 'roi-report', source: 'roi-calculator' }),
        }
      );
      if (!res.ok) throw new Error(t('newsletter.errorGeneric'));
      setDetailsUnlocked(true);
      const utm = (window as unknown as { __pa_get_utm?: () => Record<string, string> }).__pa_get_utm?.() ?? {};
      const lastSolution = sessionStorage.getItem('__pa_last_solution') ?? undefined;
      window.plausible?.('calculator_email_submit', { props: { source: 'roi-calculator', ...utm, ...(lastSolution && { last_solution: lastSolution }) } });
    } catch {
      setGateError(t('newsletter.errorGeneric'));
    } finally {
      setGateLoading(false);
    }
  }, [gateEmail, t]);

  useEffect(() => {
    if (!detailsUnlocked && !gateViewedRef.current) {
      gateViewedRef.current = true;
      window.plausible?.('roi_gate_viewed', { props: { source: 'roi-calculator' } });
    }
  }, [detailsUnlocked]);

  const output = useMemo(() => computeRoi(values), [values]);

  const sizeLabels: Record<CompanySize, { label: string; desc: string }> = {
    smb: { label: content.sizeSelect.smb, desc: content.sizeSelect.smbDesc },
    mid: { label: content.sizeSelect.mid, desc: content.sizeSelect.midDesc },
    enterprise: { label: content.sizeSelect.enterprise, desc: content.sizeSelect.enterpriseDesc },
    large: { label: content.sizeSelect.large, desc: content.sizeSelect.largeDesc },
  };

  const renderSlider = (
    slider: { id: string; min: number; max: number; step: number; format?: string },
    label: string
  ) => {
    const val = values[slider.id as keyof RoiInputs];
    return (
      <div className="sp-roi-slider" key={slider.id}>
        <label>
          {label}
          <span className="sp-roi-slider-value">{formatSliderValue(val, slider.format)}</span>
        </label>
        <input
          type="range"
          min={slider.min}
          max={slider.max}
          step={slider.step}
          value={val}
          onChange={(e) => handleSliderChange(slider.id, Number.parseFloat(e.target.value))}
        />
      </div>
    );
  };

  return (
    <section className="sp-roi-section">
      <div className="sp-roi-inner">
        <div className="sp-overline">{content.overline}</div>
        <h2>{content.title}</h2>
        <p className="sp-roi-desc">{content.description}</p>

        <div className="sp-roi-calculator">
          {/* Company size quick-select */}
          <div className="sp-roi-size-select">
            <span className="sp-roi-size-label">{content.sizeSelect.label}</span>
            <div className="sp-roi-size-buttons">
              {SIZE_KEYS.map((size) => (
                <button
                  key={size}
                  type="button"
                  className={`sp-roi-size-btn${activeSize === size ? ' active' : ''}`}
                  onClick={() => handleSizeSelect(size)}
                  data-track="cta_click"
                  data-track-label="roi-size-select"
                >
                  <span className="sp-roi-size-btn-label">{sizeLabels[size].label}</span>
                  <span className="sp-roi-size-btn-desc">{sizeLabels[size].desc}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Hero sliders */}
          <div className="sp-roi-inputs">
            {HERO_SLIDERS.map((s) => renderSlider(s, content.sliders[s.id]))}
          </div>

          {/* Advanced accordion */}
          <details className="sp-roi-advanced" onToggle={(e) => {
            if ((e.target as HTMLDetailsElement).open) {
              window.plausible?.('calculator_advanced_open', { props: { source: 'roi-calculator' } });
            }
          }}>
            <summary>{content.advancedLabel}</summary>
            <div className="sp-roi-inputs">
              {ADVANCED_SLIDERS.map((s) => renderSlider(s, content.advancedSliders[s.id]))}
            </div>
          </details>

          {/* Summary banner */}
          <div className="sp-roi-summary">
            <div className="sp-roi-summary-item">
              <span className="sp-roi-summary-label">{content.summary.annualSavings}</span>
              <span className="sp-roi-summary-value sp-roi-green">
                {formatCurrency(output.annualSavings)}
              </span>
            </div>
            <div className="sp-roi-summary-item">
              <span className="sp-roi-summary-label">{content.summary.paybackPeriod}</span>
              <span className="sp-roi-summary-value">
                {output.paybackMonths > 0
                  ? `${output.paybackMonths} ${output.paybackMonths === 1 ? content.summary.paybackUnit.replace(/s$/, '') : content.summary.paybackUnit}`
                  : '—'}
              </span>
            </div>
            <div className="sp-roi-summary-item">
              <span className="sp-roi-summary-label">{content.summary.threeYearRoi}</span>
              <span className="sp-roi-summary-value sp-roi-green">
                {output.threeYearRoiPct > 0 ? `${output.threeYearRoiPct}%` : '—'}
              </span>
            </div>
          </div>

          {/* Detail cards — gated behind email */}
          <div className={`sp-roi-details-wrapper${detailsUnlocked ? '' : ' sp-roi-gated'}`}>
            {!detailsUnlocked && (
              <div className="sp-roi-gate-overlay">
                <div className="sp-roi-gate-content">
                  <h4>{t('newsletter.roiGate.title')}</h4>
                  <p>{t('newsletter.roiGate.description')}</p>
                  <form className="sp-roi-gate-form" onSubmit={handleGateSubmit}>
                    <input
                      ref={gateInputRef}
                      type="email"
                      className="newsletter-input"
                      placeholder={t('newsletter.placeholder')}
                      value={gateEmail}
                      onChange={(e) => setGateEmail(e.target.value)}
                      required
                    />
                    <button
                      type="submit"
                      className="newsletter-button"
                      disabled={gateLoading}
                    >
                      {gateLoading ? t('newsletter.subscribe') : t('newsletter.roiGate.unlock')}
                    </button>
                  </form>
                  {gateError && <p className="newsletter-error">{gateError}</p>}
                  <p className="newsletter-privacy">{t('newsletter.privacyNote')}</p>
                </div>
              </div>
            )}
            <div className="sp-roi-details">
              {/* TCO Savings */}
              <div className="sp-roi-card">
                <h4>{content.categories.tco.title}</h4>
                <div className="sp-roi-card-row">
                  <span>{content.categories.tco.currentTco}</span>
                  <span className="sp-roi-red">{formatCurrency(output.currentAnnualTco)}</span>
                </div>
                <div className="sp-roi-card-row">
                  <span>{content.categories.tco.rediaccTco}</span>
                  <span className="sp-roi-green">{formatCurrency(output.rediaccAnnualTco)}</span>
                </div>
                <div className="sp-roi-card-row sp-roi-card-total">
                  <span>{content.categories.tco.savings}</span>
                  <span className="sp-roi-green">{formatCurrency(output.tcoSavings)}</span>
                </div>
              </div>

              {/* Dev Productivity */}
              <div className="sp-roi-card">
                <h4>{content.categories.devProductivity.title}</h4>
                <div className="sp-roi-card-row">
                  <span>{content.categories.devProductivity.hoursSaved}</span>
                  <span>{Math.round(output.devProductivityHours).toLocaleString('en-US')} hrs</span>
                </div>
                <div className="sp-roi-card-row">
                  <span>{content.categories.devProductivity.dollarValue}</span>
                  <span className="sp-roi-green">
                    {formatCurrency(output.devProductivityDollars)}
                  </span>
                </div>
                <div className="sp-roi-card-row">
                  <span>{content.categories.devProductivity.provisioningReduction}</span>
                  <span>{output.provisioningReduction}</span>
                </div>
              </div>

              {/* DR & Availability */}
              <div className="sp-roi-card">
                <h4>{content.categories.drAvailability.title}</h4>
                <div className="sp-roi-card-row">
                  <span>{content.categories.drAvailability.currentRisk}</span>
                  <span className="sp-roi-red">{formatCurrency(output.currentDowntimeRisk)}</span>
                </div>
                <div className="sp-roi-card-row">
                  <span>{content.categories.drAvailability.rediaccRisk}</span>
                  <span className="sp-roi-green">{formatCurrency(output.rediaccDowntimeRisk)}</span>
                </div>
                <div className="sp-roi-card-row">
                  <span>{content.categories.drAvailability.rtoImprovement}</span>
                  <span>{output.rtoImprovement}</span>
                </div>
                <div className="sp-roi-card-row sp-roi-card-total">
                  <span>{content.categories.drAvailability.savings}</span>
                  <span className="sp-roi-green">{formatCurrency(output.drSavings)}</span>
                </div>
              </div>

              {/* Compliance & Insurance */}
              <div className="sp-roi-card">
                <h4>{content.categories.compliance.title}</h4>
                <div className="sp-roi-card-row">
                  <span>{content.categories.compliance.storageSavings}</span>
                  <span className="sp-roi-green">{formatCurrency(output.storageSavings)}</span>
                </div>
                <div className="sp-roi-card-row">
                  <span>{content.categories.compliance.bandwidthSavings}</span>
                  <span className="sp-roi-green">{formatCurrency(output.bandwidthSavings)}</span>
                </div>
                <div className="sp-roi-card-row">
                  <span>{content.categories.compliance.complianceSavings}</span>
                  <span className="sp-roi-green">{formatCurrency(output.complianceSavings)}</span>
                </div>
                <div className="sp-roi-card-row">
                  <span>{content.categories.compliance.insuranceSavings}</span>
                  <span className="sp-roi-green">{formatCurrency(output.insuranceSavings)}</span>
                </div>
                <div className="sp-roi-card-row">
                  <span>{content.categories.compliance.auditTimeSaved}</span>
                  <span>{Math.round(output.auditHoursSaved).toLocaleString('en-US')} hrs</span>
                </div>
              </div>
            </div>
          </div>

          <div className="sp-roi-footnote">{content.footnote}</div>
        </div>
      </div>
    </section>
  );
};

export default SPRoiCalculator;
