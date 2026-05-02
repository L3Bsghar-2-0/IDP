import './Layout.css';

export default function Layout({ sidebar, topbar, children }) {
  return (
    <div className="lumi-layout">
      <div className="lumi-layout__sidebar">{sidebar}</div>
      <div className="lumi-layout__topbar">{topbar}</div>
      <main className="lumi-layout__main">{children}</main>
    </div>
  );
}
