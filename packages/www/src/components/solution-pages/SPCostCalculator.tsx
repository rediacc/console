import React, { useCallback, useMemo, useState } from 'react';
import Overlay from '../Overlay';
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
  /**
   * Passed in rather than looked up here, deliberately.
   *
   * This is an island. Reading the locale inside one means `useLanguage`, which returns
   * 'en' on the server and corrects itself after hydration, so the server HTML ships
   * English on every locale (inherited decision I17). The caller already has a
   * locale-correct translator; it hands the one string down.
   */
  closeLabel: string;
  /**
   * Raw markup for the trigger's thumbnail, resolved by the Astro caller.
   *
   * Passed down rather than globbed here for the same reason `closeLabel` is: this is an
   * island. `import.meta.glob` inside it would put ~1.3 KB of SVG into the CLIENT chunk,
   * where `check:ci-client-bundle-budget` counts it, to draw a picture that never
   * changes after first paint. As a prop it lands in the HTML instead.
   */
  thumb: string | null;
}

const SPCostCalculator: React.FC<Props> = ({ content, preset, closeLabel, thumb }) => {
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
  /**
   * THE CALCULATOR IS NOW BEHIND A CLICK, and the section it used to fill is a card.
   *
   * Measured at 1440x900 it was 1,150px tall, one and a quarter screens, and the single
   * largest object on a page that ran 8.7 screens. It also sat four screens below the
   * fold, so a 45-second visitor paid its full height and never saw it. Nothing is
   * deleted: the card states the answer at the default inputs, and the sliders that let
   * a reader argue with that answer are one click away.
   */
  const [open, setOpen] = useState(false);

  const handleChange = useCallback((id: string, val: number) => {
    setValues((prev) => ({ ...prev, [id]: val }));
    window.plausible?.('calculator_interact', { props: { field: id } });
  }, []);

  const computed = computeFn(values);
  const resultKeys = Object.keys(content.results);

  const calculator = (
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
  );

  return (
    <section className="sp-cost-section">
      <div className="sp-cost-section-inner">
        <div className="sp-overline">{content.overline}</div>
        <h2>{content.title}</h2>
        <p>{content.description}</p>

        {/* The card carries the CONCLUSION, not a teaser. A trigger that says only
            "open the calculator" asks for work before giving anything; this one answers
            the question at the default inputs and offers the sliders to whoever wants to
            disagree. `headerTitle` is reused as the button label because it is already an
            action phrase in all 13 locales, so this costs no new i18n keys. */}
        <button
          type="button"
          className="sp-calc-trigger"
          onClick={() => setOpen(true)}
          aria-haspopup="dialog"
          data-track="calculator_open"
        >
          {thumb && (
            <span
              className="sp-disclosure-thumb"
              aria-hidden="true"
              dangerouslySetInnerHTML={{ __html: thumb }}
            />
          )}
          <span className="sp-calc-trigger-figure">
            <span className="sp-calc-trigger-label">{content.annualLabel}</span>
            <span className="sp-calc-trigger-value">{computed.annual}</span>
          </span>
          <span className="sp-calc-trigger-cta">{content.headerTitle}</span>
        </button>

        <Overlay
          open={open}
          onClose={() => setOpen(false)}
          align="center"
          width="wide"
          label={content.headerTitle}
          title={content.headerTitle}
          closeLabel={closeLabel}
          closeTrackLabel="calculator-close"
          panelClassName="sp-calc-panel"
        >
          {calculator}
        </Overlay>
      </div>
    </section>
  );
};

export default SPCostCalculator;
