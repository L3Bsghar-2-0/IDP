import KpiCard from '../components/kpi/KpiCard';
import AreaChart from '../components/charts/AreaChart';
import DonutChart from '../components/charts/DonutChart';
import SiteTable from '../components/table/SiteTable';
import AnomalyFeed from '../components/feed/AnomalyFeed';
import { KPI_DATA } from '../data/mockData';
import './Dashboard.css';

export default function Dashboard() {
  return (
    <>
      {/* KPI Cards — 4-column grid */}
      <section className="grid-kpi">
        {KPI_DATA.map((kpi) => (
          <KpiCard key={kpi.id} {...kpi} />
        ))}
      </section>

      {/* Charts Row — 60/40 */}
      <section className="grid-charts">
        <AreaChart />
        <DonutChart />
      </section>

      {/* Bottom Row — 50/50 */}
      <section className="grid-bottom">
        <SiteTable />
        <AnomalyFeed />
      </section>
    </>
  );
}
