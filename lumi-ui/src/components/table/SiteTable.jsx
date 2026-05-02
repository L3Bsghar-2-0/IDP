import { SITES_DATA } from '../../data/mockData';
import './SiteTable.css';

const STATUS_MAP = {
  nominal: { label: 'Nominal', cls: 'badge--ok' },
  warning: { label: 'Warning', cls: 'badge--warn' },
  high:    { label: 'High Load', cls: 'badge--err' },
};

function StatusBadge({ status }) {
  const { label, cls } = STATUS_MAP[status] ?? STATUS_MAP.nominal;
  return <span className={`badge ${cls}`}>{label}</span>;
}

/**
 * SiteTable — data-driven table from SITES_DATA array.
 * Each row is generated from a site object — no hardcoded rows.
 */
export default function SiteTable() {
  return (
    <div className="table-card">
      <div className="table-card__header">
        <span className="table-card__title">Site Overview</span>
        <span className="table-card__period">Real-time</span>
      </div>
      <div className="table-card__scroll">
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
      </div>
    </div>
  );
}
