import { useEffect, useRef } from 'react';
import { Chart } from 'chart.js/auto';

const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

export default function Sparkline({ color = 'var(--lumi-accent)', range = [0, 100] }) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    const ctx = canvasRef.current.getContext('2d');
    const data = Array.from({ length: 24 }, () => rand(range[0], range[1]));

    chartRef.current = new Chart(ctx, {
      type: 'line',
      data: {
        labels: Array(24).fill(''),
        datasets: [{
          data,
          borderColor: color,
          borderWidth: 1.5,
          tension: 0.35,
          pointRadius: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: { x: { display: false }, y: { display: false } },
        layout: { padding: 0 },
      },
    });

    return () => chartRef.current?.destroy();
  }, [color, range[0], range[1]]);

  return (
    <div style={{ height: '40px', width: '100%', position: 'relative', marginTop: '12px' }}>
      <canvas ref={canvasRef} />
    </div>
  );
}
