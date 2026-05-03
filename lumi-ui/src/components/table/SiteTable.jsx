import { SITES_DATA } from '../../data/mockData';
import './SiteTable.css';

// ── status helpers ────────────────────────────────────────────────────────────
const MOCK_STATUS_MAP = {
  nominal: { label: 'Nominal',   cls: 'badge--ok'   },
  warning: { label: 'Warning',   cls: 'badge--warn' },
  high:    { label: 'High Load', cls: 'badge--err'  },
};

const DUM_STATUS_MAP = {
  online:  { label: 'Online',  cls: 'badge--ok'   },
  offline: { label: 'Offline', cls: 'badge--err'  },
  warning: { label: 'Warning', cls: 'badge--warn' },
};

function StatusBadge({ status, isDum = false }) {
  const map = isDum ? DUM_STATUS_MAP : MOCK_STATUS_MAP;
  const key = (status ?? '').toLowerCase();
  const { label, cls } = map[key] ?? (isDum ? DUM_STATUS_MAP.online : MOCK_STATUS_MAP.nominal);
  return <span className={`badge ${cls}`}>{label}</span>;
}

// ── DUM record normaliser ─────────────────────────────────────────────────────
// Extracts display-ready columns from a raw DUM record regardless of field names.
const ID_KEYS      = ['id', 'device_id', 'name', 'label', 'sensor_id', 'node_id'];
const STATUS_KEYS  = ['status', 'state', 'online', 'health'];
const TEMP_KEYS    = ['temperature', 'temp', 'avg_temp', 'temperature_c'];
const HUMIDITY_KEYS= ['humidity', 'hum', 'rh', 'relative_humidity'];
const GAS_KEYS     = ['gas_ppm', 'gas', 'ppm', 'co2', 'voc'];

function pick(obj, keys) {
  for (const k of keys) if (obj[k] != null) return obj[k];
  return null;
}
function fmt(v, decimals = 1) {
  if (v == null) return '—';
  const n = Number(v);
  return Number.isNaN(n) ? String(v) : n.toFixed(decimals);
}

function normRecord(r, i) {
  return {
    _key:     pick(r, ID_KEYS)     ?? `row-${i}`,
    id:       pick(r, ID_KEYS)     ?? `Device ${i + 1}`,
    status:   pick(r, STATUS_KEYS) ?? 'online',
    temp:     pick(r, TEMP_KEYS),
    humidity: pick(r, HUMIDITY_KEYS),
    gas:      pick(r, GAS_KEYS),
  };
}

// ── component ─────────────────────────────────────────────────────────────────
export default function SiteTable({ dumRecords = [], dumStatus = 'connecting' }) {
  const useDum = dumStatus === 'live' && dumRecords.length > 0;

  // ── DUM mode ──
  if (useDum) {
    const rows = dumRecords.map(normRecord);
    return (
      <div className="table-card">
        <div className="table-card__header">
          <span className="table-card__title">Device Records</span>
          <span className="table-card__period">{rows.length} from DUM</span>
        </div>
        <div className="table-card__scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Device / ID</th>
                <th>Status</th>
                <th className="cell-num">Temp (°C)</th>
                <th className="cell-num">Humidity (%)</th>
                <th className="cell-num">Gas (ppm)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row._key}>
                  <td>{row.id}</td>
                  <td><StatusBadge status={String(row.status)} isDum /></td>
                  <td className="cell-num">{fmt(row.temp)}</td>
                  <td className="cell-num">{fmt(row.humidity)}</td>
                  <td className="cell-num">{fmt(row.gas, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // ── fallback: mock data + optional overlay ──
  return (
    <div className="table-card">
      <div className="table-card__header">
        <span className="table-card__title">Site Overview</span>
        <span className="table-card__period">Real-time</span>
      </div>
      <div className="table-card__scroll" style={{ position: 'relative' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Facility Location</th>
              <th>Status</th>
              <th className="cell-num">Pwr Draw (kW)</th>
              <th className="cell-num">Avg Temp (°C)</th>
              <th className="cell-num">CO₂ Est (kg)</th>
            </tr>
          </thead>
          <tbody>
            {SITES_DATA.map((site) => (
              <tr key={site.id}>
                <td>{site.name}</td>
                <td><StatusBadge status={site.status} /></td>
                <td className="cell-num">{site.powerDraw.toFixed(1)}</td>
                <td className="cell-num">{site.avgTemp.toFixed(1)}</td>
                <td className="cell-num">{site.co2Est.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {dumStatus === 'down' && (
          <div className="table-model-down">Model Offline</div>
        )}
      </div>
    </div>
  );
}
