import { useEffect, useRef } from 'react';
import { Chart } from 'chart.js/auto';
import { SITE_BREAKDOWN } from '../../data/mockData';
import './ChartCard.css';

const SEGMENT_COLORS = ['#F5F4F0', '#776B5D', '#3A3A4C', '#BBAB8C', '#1f1f2e'];

export default function DonutChart() {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    const ctx = canvasRef.current.getContext('2d');
    const { labels, values } = SITE_BREAKDOWN;

    chartRef.current = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data: values,
          backgroundColor: SEGMENT_COLORS,
          borderWidth: 0,
          hoverOffset: 6,
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
              padding: 14,
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
            callbacks: {
              label: (ctx) => ` ${ctx.label}: ${ctx.parsed}%`,
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
        <span className="chart-card__title">Consumption by Site</span>
        <span className="chart-card__period">MTD Breakdown</span>
      </div>
      <div className="chart-card__canvas-wrap">
        <canvas ref={canvasRef} />
      </div>
    </div>
  );
}
