import { ANOMALY_EVENTS } from '../../data/mockData';
import { AnomalyItem }    from './AnomalyItem';
import './AnomalyFeed.css';

// ── DUM anomaly extraction ────────────────────────────────────────────────────
// Looks for records that carry an anomaly / alert flag or high severity.
const ANOMALY_FLAGS   = ['anomaly', 'is_anomaly', 'alert', 'is_alert', 'flagged'];
const SEVERITY_KEYS   = ['severity', 'level', 'priority', 'anomaly_type', 'type'];
const DESC_KEYS       = ['description', 'message', 'desc', 'detail', 'label', 'name'];
const VALUE_KEYS      = ['value', 'reading_value', 'magnitude', 'score', 'confidence'];
const TIME_KEYS       = ['time', 'timestamp', 'ts', 'datetime', 'created_at'];
const ID_KEYS         = ['id', 'record_id', 'event_id', 'device_id'];

const SEVERITY_MAP = {
  critical: 'critical', high: 'critical', error: 'critical', alarm: 'critical',
  warning:  'warning',  warn: 'warning',  medium: 'warning',
  info:     'info',     low: 'info',      ok: 'info',
};

const VALUE_COLOR = {
  critical: 'var(--lumi-danger)',
  warning:  'var(--lumi-accent)',
  info:     'var(--lumi-secondary)',
};

function pick(obj, keys) {
  for (const k of keys) if (obj[k] != null) return obj[k];
  return null;
}

function isAnomalyRecord(r) {
  // True if any flag field is truthy, or severity suggests a problem.
  if (ANOMALY_FLAGS.some(k => r[k] === true || r[k] === 1 || r[k] === 'true')) return true;
  const sev = (pick(r, SEVERITY_KEYS) ?? '').toString().toLowerCase();
  return sev === 'critical' || sev === 'high' || sev === 'alarm' || sev === 'warning';
}

function toFeedEvent(r, i) {
  const rawSev   = (pick(r, SEVERITY_KEYS) ?? 'info').toString().toLowerCase();
  const severity = SEVERITY_MAP[rawSev] ?? 'info';
  const rawTime  = pick(r, TIME_KEYS);
  const time     = rawTime
    ? new Date(rawTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : '—';
  const rawVal   = pick(r, VALUE_KEYS);
  const value    = rawVal != null ? Number(rawVal).toFixed(2) : '—';
  const desc     = pick(r, DESC_KEYS) ?? pick(r, ID_KEYS) ?? `Record ${i + 1}`;

  return {
    id:         pick(r, ID_KEYS) ?? `dum-${i}`,
    severity,
    time,
    title:      (pick(r, SEVERITY_KEYS) ?? 'Event').toString().replace(/_/g, ' ').toUpperCase(),
    desc:       String(desc),
    value:      String(value),
    valueColor: VALUE_COLOR[severity],
  };
}

// ── component ─────────────────────────────────────────────────────────────────
export default function AnomalyFeed({ dumRecords = [], dumStatus = 'connecting' }) {
  const useDum = dumStatus === 'live';

  let events;
  if (useDum) {
    const anomalies = dumRecords.filter(isAnomalyRecord);
    events = anomalies.length > 0
      ? anomalies.map(toFeedEvent)
      : [];                           // DUM live but no anomalies yet
  } else {
    events = ANOMALY_EVENTS;          // mock fallback
  }

  return (
    <div className="feed-card">
      <div className="feed-card__header">
        <span className="feed-card__title">Live Anomaly Detection Feed</span>
        <span className="feed-card__period">
          {dumStatus === 'live' ? 'Powered by DUM Model' : 'Powered by AI Model'}
        </span>
      </div>

      {dumStatus === 'down' && (
        <div className="feed-model-down">Model Offline — last data unavailable</div>
      )}

      {dumStatus !== 'down' && events.length === 0 && dumStatus === 'live' && (
        <div className="feed-empty">No anomalies in current DUM records</div>
      )}

      {(dumStatus !== 'down') && events.length > 0 && (
        <ul className="anomaly-list">
          {events.map((event) => (
            <AnomalyItem key={event.id} event={event} />
          ))}
        </ul>
      )}
    </div>
  );
}
