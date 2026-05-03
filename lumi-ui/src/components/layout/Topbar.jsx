import { useLiveClock } from '../../hooks/useLiveClock';
import ModelBadge       from '../badges/ModelBadge';
import './Topbar.css';

const MenuIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <path d="M3 12h18M3 6h18M3 18h18" />
  </svg>
);

export default function Topbar({ title, onMenuClick, dumStatus = 'connecting', dumSummary = null, dumFetchedAt = null }) {
  const time = useLiveClock();

  return (
    <header className="topbar">
      <div className="topbar__left">
        <button className="topbar__menu-btn" onClick={onMenuClick} aria-label="Toggle menu">
          <MenuIcon />
        </button>
        <h1 className="topbar__title">{title}</h1>
      </div>

      <div className="topbar__right">
        <ModelBadge status={dumStatus} fetchedAt={dumFetchedAt} summary={dumSummary} />
        <span className="topbar__clock">{time}</span>
      </div>
    </header>
  );
}
