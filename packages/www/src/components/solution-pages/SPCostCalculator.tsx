import React, { useState, useCallback, useMemo } from 'react';
import { PRESETS, SLIDER_CONFIGS } from './cost-presets';

interface CalculatorContent {
  overline: string;
  title: string;
  description: string;
  headerTitle: string;
  sliders: Record<string, string>;
  withoutTag: string;
  withTag: string;
  results: Record<string, string>;
  annualLabel: string;
  withResults: Record<string, string>;
  withResultLabels?: Record<string, string>;
  withAnnual: string;
  withAnnualLabel?: string;
  footnote: string;
}

interface Props {
  content: CalculatorContent;
  preset: string;
}

const SPCostCalculator: React.FC<Props> = ({ content, preset }) => {
  const sliderConfigs = useMemo(() => SLIDER_CONFIGS[preset] ?? [], [preset]);
  const computeFn = PRESETS[preset];

  const initialValues = useMemo(() => {
    const vals: Record<string, number> = {};
    for (const s of sliderConfigs) {
      vals[s.id] = s.defaultValue;
    }
    return vals;
  }, [sliderConfigs]);

  const [values, setValues] = useState(initialValues);

  const handleChange = useCallback((id: string, val: number) => {
    setValues((prev) => ({ ...prev, [id]: val }));
  }, []);

  const computed = computeFn(values);
  const resultKeys = Object.keys(content.results);

  return (
    <section className="sp-cost-section">
      <div className="sp-cost-section-inner">
        <div className="sp-overline">{content.overline}</div>
        <h2>{content.title}</h2>
        <p>{content.description}</p>

        <div className="sp-calculator">
          <div className="sp-calc-header">
            <svg viewBox="0 0 24 24">
              <rect x="4" y="2" width="16" height="20" rx="2" />
              <line x1="8" y1="6" x2="16" y2="6" />
              <line x1="8" y1="10" x2="10" y2="10" />
              <line x1="12" y1="10" x2="14" y2="10" />
              <line x1="8" y1="14" x2="10" y2="14" />
              <line x1="12" y1="14" x2="14" y2="14" />
              <line x1="8" y1="18" x2="16" y2="18" />
            </svg>
            <h3>{content.headerTitle}</h3>
          </div>

          <div className="sp-calc-inputs">
            {sliderConfigs.map((slider) => (
              <div className="sp-calc-input" key={slider.id}>
                <label>
                  {content.sliders[slider.id]}
                  <span className="sp-calc-input-value">{values[slider.id]}</span>
                </label>
                <input
                  type="range"
                  min={slider.min}
                  max={slider.max}
                  step={slider.step ?? 1}
                  value={values[slider.id]}
                  onChange={(e) => handleChange(slider.id, Number.parseInt(e.target.value))}
                />
              </div>
            ))}
          </div>

          <div className="sp-calc-results">
            <div className="sp-calc-result-col without">
              <div className="sp-calc-result-tag">{content.withoutTag}</div>
              {resultKeys.map((key) => (
                <div className="sp-calc-result-row" key={key}>
                  <span>{content.results[key]}</span>
                  <span className="sp-calc-result-num">{computed.results[key] ?? '\u2014'}</span>
                </div>
              ))}
              <div className="sp-calc-result-big">
                <div className="sp-calc-result-big-label">{content.annualLabel}</div>
                <div className="sp-calc-result-big-value">{computed.annual}</div>
              </div>
            </div>
            <div className="sp-calc-result-col with">
              <div className="sp-calc-result-tag">{content.withTag}</div>
              {resultKeys.map((key) => (
                <div className="sp-calc-result-row" key={key}>
                  <span>{content.withResultLabels?.[key] ?? content.results[key]}</span>
                  <span className="sp-calc-result-num">
                    {computed.withResults?.[key] ?? content.withResults[key]}
                  </span>
                </div>
              ))}
              <div className="sp-calc-result-big">
                <div className="sp-calc-result-big-label">
                  {content.withAnnualLabel ?? content.annualLabel}
                </div>
                <div className="sp-calc-result-big-value">
                  {computed.withAnnual ?? content.withAnnual}
                </div>
              </div>
            </div>
          </div>

          <div className="sp-calc-footnote">{content.footnote}</div>
        </div>
      </div>
    </section>
  );
};

export default SPCostCalculator;
