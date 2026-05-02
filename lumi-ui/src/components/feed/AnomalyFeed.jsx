import { ANOMALY_EVENTS } from '../../data/mockData';
import { AnomalyItem } from './AnomalyItem';
import './AnomalyFeed.css';

/**
 * AnomalyFeed — renders a scrollable list of anomaly events from ANOMALY_EVENTS.
 */
export default function AnomalyFeed() {
  return (
    <div className="feed-card">
      <div className="feed-card__header">
        <span className="feed-card__title">Live Anomaly Detection Feed</span>
        <span className="feed-card__period">Powered by AI Model</span>
      </div>
      <ul className="anomaly-list">
        {ANOMALY_EVENTS.map((event) => (
          <AnomalyItem key={event.id} event={event} />
        ))}
      </ul>
    </div>
  );
}
