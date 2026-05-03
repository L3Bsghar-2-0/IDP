import { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout    from './components/layout/Layout';
import Sidebar   from './components/layout/Sidebar';
import Topbar    from './components/layout/Topbar';
import Dashboard from './pages/Dashboard';
import { useDumData } from './hooks/useDumData';

// Placeholder pages for router completeness
const Placeholder = ({ title }) => (
  <div style={{
    display: 'flex', flexDirection: 'column',
    alignItems: 'center', justifyContent: 'center',
    height: '60vh', gap: '12px', color: 'var(--lumi-text-muted)',
  }}>
    <span style={{ fontSize: '40px', opacity: 0.3 }}>◈</span>
    <p style={{ fontSize: '14px', textTransform: 'uppercase', letterSpacing: '1px' }}>
      {title} — Coming Soon
    </p>
  </div>
);

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const dum = useDumData();                    // single WS connection for the whole app

  return (
    <BrowserRouter>
      <Layout
        sidebar={
          <Sidebar
            isOpen={sidebarOpen}
            onClose={() => setSidebarOpen(false)}
          />
        }
        topbar={
          <Topbar
            title="Facility Command Center"
            onMenuClick={() => setSidebarOpen((o) => !o)}
            dumStatus={dum.status}
            dumSummary={dum.summary}
            dumFetchedAt={dum.fetchedAt}
          />
        }
      >
        <Routes>
          <Route path="/"          element={<Dashboard dum={dum} />} />
          <Route path="/sites"     element={<Placeholder title="Site Analytics" />} />
          <Route path="/emissions" element={<Placeholder title="Emissions Tracking" />} />
          <Route path="/models"    element={<Placeholder title="Predictive Models" />} />
          <Route path="/anomalies" element={<Placeholder title="Anomaly Feed" />} />
          <Route path="/sensors"   element={<Placeholder title="Sensor Fleet" />} />
          <Route path="/documents" element={<Placeholder title="Document Parsing" />} />
          <Route path="/config"    element={<Placeholder title="Configuration" />} />
          <Route path="/users"     element={<Placeholder title="User Management" />} />
          <Route path="*"          element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
