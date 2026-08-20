import { useEffect, useState } from "react";
import { api, type AuditEvent, type AuditVerify } from "../api";

export function AuditLog({
  requestId,
  refreshKey,
}: {
  requestId: number;
  refreshKey: string; // reload when workflow status changes
}) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [verify, setVerify] = useState<AuditVerify | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.auditLog(requestId), api.auditVerify()])
      .then(([log, verification]) => {
        if (!cancelled) {
          setEvents(log);
          setVerify(verification);
        }
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Failed to load audit log");
      });
    return () => {
      cancelled = true;
    };
  }, [requestId, refreshKey]);

  if (error) return <p className="error" role="alert">{error}</p>;

  return (
    <div>
      {verify && (
        <p className={verify.intact ? "notice ok" : "error"}>
          Hash chain {verify.intact ? "verified intact" : "BROKEN"} across{" "}
          {verify.events_checked} event(s). Every entry is chained to the previous
          one with SHA-256, so history cannot be silently edited.
        </p>
      )}
      <div className="table-scroll">
        <table className="audit-table">
          <thead>
            <tr>
              <th scope="col">Time (UTC)</th>
              <th scope="col">Actor</th>
              <th scope="col">Event</th>
              <th scope="col">Details</th>
              <th scope="col">Hash</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr key={event.id}>
                <td className="mono small">
                  {event.created_at.replace("T", " ").slice(0, 19)}
                </td>
                <td>
                  <span className={`badge actor-${event.actor}`}>{event.actor}</span>
                </td>
                <td>{event.event_type.replaceAll("_", " ")}</td>
                <td className="small payload">{event.payload_json}</td>
                <td className="mono small" title={event.hash}>
                  {event.hash.slice(0, 10)}…
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
