import { useEffect, useRef } from 'react';
import { Chart } from 'chart.js/auto';
import { ENERGY_FORECAST } from '../../data/mockData';
import './ChartCard.css';

export default function AreaChart() {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    const ctx = canvasRef.current.getContext('2d');
    const { labels, historical, forecast } = ENERGY_FORECAST;

    // Subtle fill gradient
    const gradient = ctx.createLinearGradient(0, 0, 0, 280);
    gradient.addColorStop(0, 'rgba(187,171,140,0.18)');
    gradient.addColorStop(1, 'rgba(12,12,14,0)');

    chartRef.current = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Historical',
            data: historical,
            borderColor: '#F5F4F0',
            backgroundColor: gradient,
            borderWidth: 1.8,
            fill: true,
            tension: 0.4,
            pointRadius: 0,
            pointHitRadius: 12,
          },
          {
            label: 'AI Forecast',
            data: forecast,
            borderColor: '#BBAB8C',
            borderWidth: 1.8,
            borderDash: [5, 5],
            fill: false,
            tension: 0.4,
            pointRadius: 0,
            pointHitRadius: 12,
          },
        ],
      },
      options: {
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
      },
    });

    return () => chartRef.current?.destroy();
  }, []);

  return (
    <div className="chart-card">
      <div className="chart-card__header">
        <span className="chart-card__title">Energy Consumption Forecast (kWh)</span>
        <span className="chart-card__period">Next 48 Hours</span>
      </div>
      <div className="chart-card__canvas-wrap">
        <canvas ref={canvasRef} />
      </div>
    </div>
  );
}
