import type { ReactNode } from 'react';

interface MarkdownMessageProps {
  content: string;
  streaming?: boolean;
}

type MarkdownBlock =
  | { type: 'paragraph'; text: string }
  | { type: 'heading'; level: number; text: string }
  | { type: 'ul'; items: string[] }
  | { type: 'ol'; items: string[] }
  | { type: 'blockquote'; text: string }
  | { type: 'code'; language: string; text: string }
  | { type: 'table'; headers: string[]; rows: string[][] }
  | { type: 'hr' };

export function MarkdownMessage({ content, streaming }: MarkdownMessageProps) {
  const blocks = parseMarkdown(content);
  return (
    <div className="markdown-message">
      {blocks.map((block, index) => renderBlock(block, index))}
      {streaming && <span className="markdown-stream-cursor" aria-label="AI is responding" />}
    </div>
  );
}

function parseMarkdown(content: string): MarkdownBlock[] {
  const lines = String(content || '').replace(/\r\n/g, '\n').split('\n');
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed.startsWith('```')) {
      const language = trimmed.slice(3).trim();
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push({ type: 'code', language, text: codeLines.join('\n') });
      continue;
    }

    if (/^---+$/.test(trimmed)) {
      blocks.push({ type: 'hr' });
      index += 1;
      continue;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(trimmed);
    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2] });
      index += 1;
      continue;
    }

    if (isTableStart(lines, index)) {
      const headers = splitTableRow(lines[index]);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        rows.push(splitTableRow(lines[index]));
        index += 1;
      }
      blocks.push({ type: 'table', headers, rows });
      continue;
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*[-*+]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*+]\s+/, '').trim());
        index += 1;
      }
      blocks.push({ type: 'ul', items });
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+\.\s+/, '').trim());
        index += 1;
      }
      blocks.push({ type: 'ol', items });
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      const quoteLines: string[] = [];
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^\s*>\s?/, '').trim());
        index += 1;
      }
      blocks.push({ type: 'blockquote', text: quoteLines.join('\n') });
      continue;
    }

    const paragraph: string[] = [];
    while (index < lines.length && lines[index].trim() && !isBlockStart(lines, index)) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ type: 'paragraph', text: paragraph.join(' ') });
  }

  return blocks;
}

function renderBlock(block: MarkdownBlock, index: number) {
  if (block.type === 'heading') {
    const Tag = `h${Math.min(block.level + 2, 6)}` as keyof JSX.IntrinsicElements;
    return <Tag key={index}>{renderInline(block.text)}</Tag>;
  }
  if (block.type === 'paragraph') {
    return <p key={index}>{renderInline(block.text)}</p>;
  }
  if (block.type === 'ul') {
    return (
      <ul key={index}>
        {block.items.map((item, itemIndex) => (
          <li key={itemIndex}>{renderInline(item)}</li>
        ))}
      </ul>
    );
  }
  if (block.type === 'ol') {
    return (
      <ol key={index}>
        {block.items.map((item, itemIndex) => (
          <li key={itemIndex}>{renderInline(item)}</li>
        ))}
      </ol>
    );
  }
  if (block.type === 'blockquote') {
    return <blockquote key={index}>{renderInline(block.text)}</blockquote>;
  }
  if (block.type === 'code') {
    return (
      <pre key={index} className="markdown-code">
        {block.language && <span className="markdown-code-language">{block.language}</span>}
        <code>{block.text}</code>
      </pre>
    );
  }
  if (block.type === 'table') {
    return (
      <div className="markdown-table-wrap" key={index}>
        <table>
          <thead>
            <tr>
              {block.headers.map((header, headerIndex) => (
                <th key={headerIndex}>{renderInline(header)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex}>{renderInline(cell)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return <hr key={index} />;
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text))) {
    if (match.index > cursor) {
      nodes.push(text.slice(cursor, match.index));
    }
    const token = match[0];
    const key = `${match.index}-${token}`;

    if (token.startsWith('`')) {
      nodes.push(<code key={key}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith('**')) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith('*')) {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    } else {
      const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      const href = link ? safeHref(link[2]) : '';
      nodes.push(
        href ? (
          <a href={href} key={key} target="_blank" rel="noreferrer">
            {link?.[1]}
          </a>
        ) : (
          token
        ),
      );
    }
    cursor = match.index + token.length;
  }

  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }
  return nodes;
}

function isBlockStart(lines: string[], index: number) {
  const line = lines[index] || '';
  const trimmed = line.trim();
  return (
    trimmed.startsWith('```') ||
    /^---+$/.test(trimmed) ||
    /^(#{1,4})\s+/.test(trimmed) ||
    /^\s*[-*+]\s+/.test(line) ||
    /^\s*\d+\.\s+/.test(line) ||
    /^\s*>\s?/.test(line) ||
    isTableStart(lines, index)
  );
}

function isTableStart(lines: string[], index: number) {
  return !!lines[index]?.includes('|') && isTableSeparator(lines[index + 1] || '');
}

function isTableSeparator(line: string) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function splitTableRow(line: string) {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim());
}

function safeHref(value: string) {
  const trimmed = value.trim();
  return /^(https?:\/\/|mailto:)/i.test(trimmed) ? trimmed : '';
}
