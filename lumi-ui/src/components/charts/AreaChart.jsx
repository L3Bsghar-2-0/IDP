import { useEffect, useRef } from 'react';
import { Chart } from 'chart.js/auto';
import { ENERGY_FORECAST } from '../../data/mockData';
import './ChartCard.css';

// ── forecast parser ───────────────────────────────────────────────────────────
// Handles whatever field names the DUM model uses for time + numeric value.
const TIME_KEYS  = ['time', 'timestamp', 'ts', 'date', 'datetime', 't'];
const VALUE_KEYS = ['value', 'predicted', 'predicted_value', 'forecast_value', 'y', 'val', 'v'];

function parseDumForecast(forecast) {
  if (!Array.isArray(forecast) || !forecast.length) return null;
  const first   = forecast[0];
  const timeKey = TIME_KEYS.find(k => first[k] != null);
  const valKey  = VALUE_KEYS.find(k => first[k] != null);
  if (!timeKey || !valKey) return null;

  const points = forecast
    .map(p => ({ time: p[timeKey], value: p[valKey] }))
    .filter(p => typeof p.value === 'number' && !Number.isNaN(p.value));

  return points.length >= 2 ? points : null;
}

function formatTick(raw) {
  try {
    return new Date(raw).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return String(raw);
  }
}

const CHART_OPTS = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index', intersect: false },
  plugins: {
    legend: {
      position: 'top',
      align: 'end',
      labels: {
        boxWidth: 10,
        usePointStyle: true,
        pointStyleWidth: 10,
        color: '#A3A3B5',
        font: { family: '"Helvetica Neue", Helvetica, Arial, sans-serif', size: 11 },
      },
    },
    tooltip: {
      backgroundColor: '#28283A',
      titleColor: '#F5F4F0',
      bodyColor: '#A3A3B5',
      borderColor: '#3A3A4C',
      borderWidth: 1,
    },
  },
  scales: {
    y: {
      beginAtZero: false,
      border: { dash: [4, 4], color: 'transparent' },
      grid: { color: '#3A3A4C' },
      ticks: {
        color: '#A3A3B5',
        font: { size: 11, family: '"Helvetica Neue", Helvetica, Arial, sans-serif' },
      },
    },
    x: {
      grid: { display: false },
      ticks: {
        maxTicksLimit: 8,
        color: '#A3A3B5',
        font: { size: 11, family: '"Helvetica Neue", Helvetica, Arial, sans-serif' },
      },
    },
  },
};

// ── component ─────────────────────────────────────────────────────────────────
export default function AreaChart({ dumForecast = [], dumStatus = 'connecting' }) {
  const canvasRef = useRef(null);
  const chartRef  = useRef(null);

  useEffect(() => {
    const ctx      = canvasRef.current.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 280);
    gradient.addColorStop(0, 'rgba(187,171,140,0.18)');
    gradient.addColorStop(1, 'rgba(12,12,14,0)');

    const dumPoints = parseDumForecast(dumForecast);
    const useDum    = dumStatus === 'live' && dumPoints !== null;

    let labels, datasets;

    if (useDum) {
      labels = dumPoints.map(p => formatTick(p.time));
      datasets = [{
        label: 'DUM Forecast',
        data:        dumPoints.map(p => p.value),
        borderColor: '#BBAB8C',
        backgroundColor: gradient,
        borderWidth: 1.8,
        borderDash:  [5, 5],
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        pointHitRadius: 12,
      }];
    } else {
      const { labels: mockLabels, historical, forecast } = ENERGY_FORECAST;
      labels = mockLabels;
      datasets = [
        {
          label: 'Historical',
          data:            historical,
          borderColor:     '#F5F4F0',
          backgroundColor: gradient,
          borderWidth: 1.8,
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHitRadius: 12,
        },
        {
          label: 'AI Forecast',
          data:        forecast,
          borderColor: '#BBAB8C',
          borderWidth: 1.8,
          borderDash:  [5, 5],
          fill: false,
          tension: 0.4,
          pointRadius: 0,
          pointHitRadius: 12,
        },
      ];
    }

    if (chartRef.current) {
      chartRef.current.data.labels   = labels;
      chartRef.current.data.datasets = datasets;
      chartRef.current.update('none');
      return;
    }

    chartRef.current = new Chart(ctx, { type: 'line', data: { labels, datasets }, options: CHART_OPTS });

    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  // Only re-run when the forecast payload actually changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dumStatus, JSON.stringify(dumForecast)]);

  const title    = dumStatus === 'live' && parseDumForecast(dumForecast)
    ? 'DUM Model Forecast'
    : 'Energy Consumption Forecast (kWh)';
  const subtitle = dumStatus === 'live' && parseDumForecast(dumForecast)
    ? `${dumForecast.length} points`
    : 'Next 48 Hours';

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
