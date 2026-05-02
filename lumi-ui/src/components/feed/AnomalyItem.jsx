import './AnomalyFeed.css';

const SEVERITY_CLASS = {
  critical: 'anomaly-item--critical',
  warning:  'anomaly-item--warning',
  info:     'anomaly-item--info',
};

/**
 * AnomalyItem — single event row with left-border severity coding.
 */
export function AnomalyItem({ event }) {
  const cls = SEVERITY_CLASS[event.severity] ?? SEVERITY_CLASS.info;
  return (
    <li className={`anomaly-item ${cls}`}>
      <div className="anomaly-item__time">{event.time}</div>
      <div className="anomaly-item__body">
        <span className="anomaly-item__title">{event.title}</span>
        <span className="anomaly-item__desc">{event.desc}</span>
      </div>
      <div className="anomaly-item__value" style={{ color: event.valueColor }}>
        {event.value}
      </div>
    </li>
  );
}
