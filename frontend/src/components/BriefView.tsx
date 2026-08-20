import type { Brief } from "../api";
import { Markdown } from "../markdown";

export function BriefView({
  brief,
  running,
}: {
  brief: Brief | null;
  running: boolean;
}) {
  if (!brief) {
    return (
      <p className="muted" aria-live="polite">
        {running ? "The brief is being generated…" : "No brief has been generated."}
      </p>
    );
  }
  return (
    <article className="brief" aria-label="Research brief">
      <div className="muted small">
        Version {brief.version} · generated {new Date(brief.created_at + "Z").toLocaleString()}
      </div>
      <Markdown text={brief.content_markdown} />
    </article>
  );
}
