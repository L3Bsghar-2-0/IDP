import KpiCard      from '../components/kpi/KpiCard';
import AreaChart    from '../components/charts/AreaChart';
import DonutChart   from '../components/charts/DonutChart';
import SiteTable    from '../components/table/SiteTable';
import AnomalyFeed  from '../components/feed/AnomalyFeed';
import ModelBadge   from '../components/badges/ModelBadge';
import { KPI_DATA } from '../data/mockData';
import './Dashboard.css';

// ── KPI builder ──────────────────────────────────────────────────────────────
// Tries known field names from the DUM summary; falls back to mock data.
const KPI_FIELD_MAP = [
  {
    id: 'k1',
    candidates: ['total_energy', 'energy_kwh', 'energy'],
    label: 'Total Energy', unit: 'kWh',
    sparkColor: 'var(--lumi-success)', sparkRange: [400, 800],
  },
  {
    id: 'k2',
    candidates: ['avg_temperature', 'temperature', 'temp_avg', 'temp'],
    label: 'Avg Temperature', unit: '°C',
    sparkColor: 'var(--lumi-accent)', sparkRange: [15, 45],
  },
  {
    id: 'k3',
    candidates: ['device_count', 'devices_online', 'active_devices', 'nodes'],
    label: 'Devices Online', unit: '',
    sparkColor: 'var(--lumi-text-muted)', sparkRange: [0, 20],
  },
  {
    id: 'k4',
    candidates: ['anomaly_count', 'anomalies', 'alerts', 'alert_count'],
    label: 'Anomalies', unit: 'today',
    sparkColor: 'var(--lumi-danger)', sparkRange: [0, 20],
  },
];

function buildKpis(summary) {
  if (!summary) return KPI_DATA;

  return KPI_FIELD_MAP.map((def, i) => {
    const key = def.candidates.find(c => summary[c] != null);
    const raw = key != null ? summary[key] : null;

    if (raw == null) return KPI_DATA[i];   // no matching field → keep mock card

    const value = typeof raw === 'number' ? Math.round(raw * 10) / 10 : Number(raw) || 0;
    return {
      id:         def.id,
      label:      def.label,
      value,
      unit:       def.unit,
      period:     'Live',
      change:     { value: 0, label: 'from DUM' },
      sparkColor: def.sparkColor,
      sparkRange: def.sparkRange,
    };
  });
}

// ── component ────────────────────────────────────────────────────────────────
export default function Dashboard({ dum = {} }) {
  const { records = [], summary = null, forecast = [], fetchedAt = null, status = 'connecting' } = dum;
  const kpis = buildKpis(summary);

  return (
    <>
      {/* Model status strip */}
      <div className="dashboard-status-bar">
        <ModelBadge status={status} fetchedAt={fetchedAt} summary={summary} />
        {summary?.model_version && (
          <span className="dashboard-status-bar__meta">
            Model inference active
          </span>
        )}
      </div>

      {/* KPI Cards */}
      <section className="grid-kpi">
        {kpis.map((kpi) => (
          <KpiCard key={kpi.id} {...kpi} />
        ))}
      </section>

      {/* Charts */}
      <section className="grid-charts">
        <AreaChart dumForecast={forecast} dumStatus={status} />
        <DonutChart dumRecords={records} dumStatus={status} />
      </section>

      {/* Bottom */}
      <section className="grid-bottom">
        <SiteTable dumRecords={records} dumStatus={status} />
        <AnomalyFeed dumRecords={records} dumStatus={status} />
      </section>
    </>
  );
}
