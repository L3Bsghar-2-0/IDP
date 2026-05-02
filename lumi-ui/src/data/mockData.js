/**
 * LUMI — Centralised Mock Data Layer
 * All values are isolated here so swapping in a real API
 * (e.g. fetch('/api/v1/sensors')) requires changing only this file.
 */

// ─── KPI Cards ──────────────────────────────────────────────────────────────
export const KPI_DATA = [
  {
    id: 'energy',
    label: 'Total Energy Consumed',
    value: 14250,
    unit: 'kWh',
    period: '24h',
    change: { value: -12.4, label: 'vs prev' },
    sparkColor: 'var(--lumi-success)',
    sparkRange: [400, 800],
  },
  {
    id: 'co2',
    label: 'Est. CO₂ Emissions',
    value: 2840,
    unit: 'kg',
    period: '24h',
    change: { value: -8.1, label: 'vs prev' },
    sparkColor: 'var(--lumi-success)',
    sparkRange: [100, 250],
  },
  {
    id: 'sensors',
    label: 'Active IoT Sensors',
    value: 342,
    unit: '/ 350',
    period: 'Live',
    change: { value: 2, label: 'reconnected', positive: true },
    sparkColor: 'var(--lumi-text-muted)',
    sparkRange: [340, 345],
  },
  {
    id: 'docs',
    label: 'Docs Processed',
    value: 1284,
    unit: 'files',
    period: 'Total',
    change: { value: 45, label: 'today', positive: true },
    sparkColor: 'var(--lumi-accent)',
    sparkRange: [0, 5],
  },
];

// ─── Site Comparison Table ───────────────────────────────────────────────────
export const SITES_DATA = [
  {
    id: 'sfax',
    name: 'Usine Sfax — Zone Industrielle',
    status: 'high',
    powerDraw: 845.2,
    avgTemp: 28.4,
    co2Est: 1240,
  },
  {
    id: 'bizerte',
    name: 'Raffinerie Bizerte',
    status: 'nominal',
    powerDraw: 620.8,
    avgTemp: 24.1,
    co2Est: 890,
  },
  {
    id: 'benarous',
    name: 'Entrepôt de Ben Arous',
    status: 'warning',
    powerDraw: 310.5,
    avgTemp: 26.8,
    co2Est: 410,
  },
  {
    id: 'lyon',
    name: 'Site Lyon — Vénissieux',
    status: 'nominal',
    powerDraw: 420.0,
    avgTemp: 22.5,
    co2Est: 560,
  },
  {
    id: 'tunis',
    name: 'Centre R&D Tunis',
    status: 'nominal',
    powerDraw: 145.2,
    avgTemp: 21.0,
    co2Est: 210,
  },
];

// ─── Anomaly Events ──────────────────────────────────────────────────────────
export const ANOMALY_EVENTS = [
  {
    id: 'a1',
    severity: 'critical',
    time: '10:42 AM',
    title: 'Unusual Power Spike detected',
    desc: 'Usine Sfax — Compressor Line B',
    value: '+42%',
    valueColor: 'var(--lumi-danger)',
  },
  {
    id: 'a2',
    severity: 'warning',
    time: '10:15 AM',
    title: 'HVAC Inefficiency Warning',
    desc: 'Entrepôt de Ben Arous — Zone 3',
    value: '+15%',
    valueColor: 'var(--lumi-accent)',
  },
  {
    id: 'a3',
    severity: 'info',
    time: '09:30 AM',
    title: 'New PDF Report Parsed',
    desc: 'STEG_Facture_Janvier_2026.pdf',
    value: 'Ready',
    valueColor: 'var(--lumi-secondary)',
  },
  {
    id: 'a4',
    severity: 'info',
    time: '08:12 AM',
    title: 'Sensor Calibration Complete',
    desc: 'Raffinerie Bizerte — Node 42',
    value: 'OK',
    valueColor: 'var(--lumi-secondary)',
  },
  {
    id: 'a5',
    severity: 'critical',
    time: '02:14 AM',
    title: 'Night-time Baseline Exceeded',
    desc: 'Site Lyon — Server Room Cooling',
    value: '+22%',
    valueColor: 'var(--lumi-danger)',
  },
];

// ─── Site Donut Breakdown ────────────────────────────────────────────────────
export const SITE_BREAKDOWN = {
  labels: ['Usine Sfax', 'Raffinerie Bizerte', 'Site Lyon', 'Entrepôt Ben Arous', 'Centre R&D Tunis'],
  values: [35, 25, 20, 15, 5],
};

// ─── Energy Forecast (48-hour window) ───────────────────────────────────────
const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

const histData = Array.from({ length: 24 }, () => rand(500, 900));
const fcast = [
  ...Array(23).fill(null),
  histData[23],
  ...Array.from({ length: 24 }, () => rand(600, 950)),
];

export const ENERGY_FORECAST = {
  labels: Array.from({ length: 48 }, (_, i) => `${String(i).padStart(2, '0')}:00`),
  historical: histData,
  forecast: fcast,
};

// ─── Navigation Items ────────────────────────────────────────────────────────
export const NAV_GROUPS = [
  {
    title: 'Intelligence',
    items: [
      { label: 'Overview', path: '/' },
      { label: 'Site Analytics', path: '/sites' },
      { label: 'Emissions Tracking', path: '/emissions' },
      { label: 'Predictive Models', path: '/models' },
    ],
  },
  {
    title: 'Operations',
    items: [
      { label: 'Anomaly Feed', path: '/anomalies' },
      { label: 'Sensor Fleet', path: '/sensors' },
      { label: 'Document Parsing', path: '/documents' },
    ],
  },
  {
    title: 'Settings',
    items: [
      { label: 'Configuration', path: '/config' },
      { label: 'User Management', path: '/users' },
    ],
  },
];
