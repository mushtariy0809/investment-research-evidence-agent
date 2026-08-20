// Minimal markdown renderer for research briefs.
//
// Why not a library? The brief is LLM-generated text; rendering it as HTML is
// an XSS surface. This renderer never uses dangerouslySetInnerHTML — all text
// goes through React text nodes (escaped by construction) and only a small
// whitelist of transforms (headings, lists, quotes, bold, citations) becomes
// real elements. No markup from the model ever reaches the DOM as live HTML.

import type { JSX } from "react";

function renderInline(text: string): JSX.Element {
  // Split on **bold**, *italic*, and [E#] citation markers.
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|\[E\d+\])/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return <strong key={i}>{part.slice(2, -2)}</strong>;
        }
        if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
          return <em key={i}>{part.slice(1, -1)}</em>;
        }
        if (/^\[E\d+\]$/.test(part)) {
          return (
            <span key={i} className="cite" title="Evidence citation">
              {part}
            </span>
          );
        }
        return part;
      })}
    </>
  );
}

export function Markdown({ text }: { text: string }) {
  const blocks: JSX.Element[] = [];
  let list: string[] = [];
  let key = 0;

  const flushList = () => {
    if (list.length > 0) {
      blocks.push(
        <ul key={key++}>
          {list.map((item, i) => (
            <li key={i}>{renderInline(item)}</li>
          ))}
        </ul>,
      );
      list = [];
    }
  };

  for (const raw of text.split("\n")) {
    const line = raw.trim(); // leading indent must not hide list/quote markers
    if (line.startsWith("- ")) {
      list.push(line.slice(2));
      continue;
    }
    flushList();
    if (line.startsWith("### ")) {
      blocks.push(<h4 key={key++}>{renderInline(line.slice(4))}</h4>);
    } else if (line.startsWith("## ")) {
      blocks.push(<h3 key={key++}>{renderInline(line.slice(3))}</h3>);
    } else if (line.startsWith("> ")) {
      blocks.push(
        <blockquote key={key++}>{renderInline(line.slice(2))}</blockquote>,
      );
    } else if (line.trim() !== "") {
      blocks.push(<p key={key++}>{renderInline(line)}</p>);
    }
  }
  flushList();
  return <div className="markdown">{blocks}</div>;
}
