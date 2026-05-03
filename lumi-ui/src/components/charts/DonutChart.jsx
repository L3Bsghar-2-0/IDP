import { useEffect, useRef } from 'react';
import { Chart } from 'chart.js/auto';
import { SITE_BREAKDOWN } from '../../data/mockData';
import './ChartCard.css';

const SEGMENT_COLORS = ['#F5F4F0', '#776B5D', '#3A3A4C', '#BBAB8C', '#1f1f2e', '#A3A3B5'];

// ── breakdown builder ─────────────────────────────────────────────────────────
// Groups DUM records by the first categorical field found.
const CATEGORY_KEYS = ['category', 'type', 'sensor_type', 'label', 'class', 'site', 'location', 'zone'];

function buildDumBreakdown(records) {
  if (!Array.isArray(records) || !records.length) return null;
  const first   = records[0];
  const catKey  = CATEGORY_KEYS.find(k => typeof first[k] === 'string');
  if (!catKey) return null;

  const counts = {};
  for (const r of records) {
    const cat = r[catKey] ?? 'Other';
    counts[cat] = (counts[cat] ?? 0) + 1;
  }
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 6);
  return {
    labels: entries.map(([k]) => k),
    values: entries.map(([, v]) => v),
    isCount: true,
  };
}

// ── component ─────────────────────────────────────────────────────────────────
export default function DonutChart({ dumRecords = [], dumStatus = 'connecting' }) {
  const canvasRef = useRef(null);
  const chartRef  = useRef(null);

  useEffect(() => {
    const dumBreakdown = dumStatus === 'live' ? buildDumBreakdown(dumRecords) : null;
    const { labels, values, isCount } = dumBreakdown ?? { ...SITE_BREAKDOWN, isCount: false };

    const tooltipLabel = isCount
      ? (ctx) => ` ${ctx.label}: ${ctx.parsed} record${ctx.parsed !== 1 ? 's' : ''}`
      : (ctx) => ` ${ctx.label}: ${ctx.parsed}%`;

    if (chartRef.current) {
      chartRef.current.data.labels                              = labels;
      chartRef.current.data.datasets[0].data                   = values;
      chartRef.current.options.plugins.tooltip.callbacks.label = tooltipLabel;
      chartRef.current.update();
      return;
    }

    chartRef.current = new Chart(canvasRef.current.getContext('2d'), {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data:            values,
          backgroundColor: SEGMENT_COLORS,
          borderWidth:     0,
          hoverOffset:     6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '74%',
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              boxWidth: 10,
              padding:  14,
              color: '#A3A3B5',
              font: { family: '"Helvetica Neue", Helvetica, Arial, sans-serif', size: 11 },
            },
          },
          tooltip: {
            backgroundColor: '#28283A',
            titleColor:      '#F5F4F0',
            bodyColor:       '#A3A3B5',
            borderColor:     '#3A3A4C',
            borderWidth:     1,
            callbacks: { label: tooltipLabel },
          },
        },
      },
    });

    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dumStatus, JSON.stringify(dumRecords)]);

  const title    = dumStatus === 'live' && buildDumBreakdown(dumRecords)
    ? 'Records by Category'
    : 'Consumption by Site';
  const subtitle = dumStatus === 'live' && buildDumBreakdown(dumRecords)
    ? `${dumRecords.length} records`
    : 'MTD Breakdown';

  return (
    <div className="chart-card">
      <div className="chart-card__header">
        <span className="chart-card__title">{title}</span>
        <span className="chart-card__period">{subtitle}</span>
      </div>
      <div className="chart-card__canvas-wrap">
        <canvas ref={canvasRef} />
        {dumStatus === 'down' && (
          <div className="chart-model-down">Model Offline</div>
        )}
      </div>
    </div>
  );
}
