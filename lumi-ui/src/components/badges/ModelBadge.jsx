import './ModelBadge.css';

/**
 * ModelBadge — shows DUM model connection status + version in the topbar.
 *
 * @prop {'connecting'|'live'|'stale'|'down'} status
 * @prop {string|null}  fetchedAt  ISO timestamp of last relay tick
 * @prop {object|null}  summary    DUM summary object (may carry model_version)
 */
export default function ModelBadge({ status = 'connecting', fetchedAt = null, summary = null }) {
  const version = summary?.model_version ?? summary?.version ?? null;

  const time = fetchedAt
    ? new Date(fetchedAt).toLocaleTimeString([], {
        hour:   '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : null;

  return (
    <div className={`model-badge model-badge--${status}`} title="DUM model connection">
      <span className={`model-badge__dot model-badge__dot--${status}`} />

      <span className="model-badge__label">
        DUM{version ? ` v${version}` : ''}
      </span>

      <span className="model-badge__status">
        {STATUS_TEXT[status]}
      </span>

      {status === 'live' && time && (
        <span className="model-badge__time">{time}</span>
      )}
    </div>
  );
}

const STATUS_TEXT = {
  connecting: 'Connecting…',
  live:       'Live',
  stale:      'Stale',
  down:       'Model Down',
};
