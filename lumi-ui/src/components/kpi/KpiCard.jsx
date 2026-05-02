import { useCountUp } from '../../hooks/useCountUp';
import Sparkline from './Sparkline';
import './KpiCard.css';

const DownArrow = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <path d="M12 5v14M19 12l-7 7-7-7" />
  </svg>
);
const UpArrow = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <path d="M12 19V5M5 12l7-7 7 7" />
  </svg>
);

/**
 * KpiCard — fully data-driven KPI display component.
 * @prop {string}  label       - Card heading
 * @prop {number}  value       - Numeric value (animated)
 * @prop {string}  unit        - Unit label
 * @prop {string}  period      - Period label shown top-right
 * @prop {object}  change      - { value: number, label: string, positive?: bool }
 * @prop {string}  sparkColor  - Sparkline line color (CSS var or hex)
 * @prop {number[]} sparkRange - [min, max] for generated sparkline data
 */
export default function KpiCard({
  label, value, unit, period, change = {}, sparkColor, sparkRange,
}) {
  const animated = useCountUp(value);
  const isPositive = change.positive ?? change.value > 0;
  const isDecrease = change.value < 0;

  // For energy/CO2 decrease is good (green); for count increase is good
  const changeClass = isDecrease
    ? 'kpi-card__change--decrease'
    : isPositive
      ? 'kpi-card__change--increase'
      : '';

  return (
    <div className="kpi-card">
      <div className="kpi-card__header">
        <span className="kpi-card__label">{label}</span>
        <span className="kpi-card__period">{period}</span>
      </div>

      <div className="kpi-card__value">
        <span className="kpi-card__number">{animated.toLocaleString()}</span>
        <span className="kpi-card__unit">{unit}</span>
      </div>

      <div className={`kpi-card__change ${changeClass}`}>
        {isDecrease ? <DownArrow /> : <UpArrow />}
        <span>
          {Math.abs(change.value)}{typeof change.value === 'number' && change.label?.includes('prev') ? '%' : ''}
          {' '}{change.label}
        </span>
      </div>

      <Sparkline color={sparkColor} range={sparkRange} />
    </div>
  );
}
