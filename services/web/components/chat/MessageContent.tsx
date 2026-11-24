"use client";

import React from "react";

/**
 * Minimal, dependency-free Markdown renderer for assistant answers.
 *
 * Supports the subset the RAG model actually emits: paragraphs, unordered and
 * ordered lists, bold (**text**), inline code (`text`), and single line breaks.
 * This keeps chat answers readable instead of showing raw `**` / `-` markers.
 */

function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
    // Split on **bold** and `code` tokens while preserving order.
    const tokens = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
    return tokens
        .filter((t) => t !== "")
        .map((token, i) => {
            const key = `${keyPrefix}-${i}`;
            if (token.startsWith("**") && token.endsWith("**") && token.length > 4) {
                return (
                    <strong key={key} className="font-semibold text-foreground">
                        {token.slice(2, -2)}
                    </strong>
                );
            }
            if (token.startsWith("`") && token.endsWith("`") && token.length > 2) {
                return (
                    <code
                        key={key}
                        className="rounded bg-muted/60 px-1 py-0.5 font-mono text-[0.85em] text-emerald-300"
                    >
                        {token.slice(1, -1)}
                    </code>
                );
            }
            return <React.Fragment key={key}>{token}</React.Fragment>;
        });
}

const UL_RE = /^\s*[-*•]\s+/;
const OL_RE = /^\s*\d+[.)]\s+/;

export function MessageContent({ content }: { content: string }) {
    const lines = (content || "").replace(/\r\n/g, "\n").split("\n");
    const blocks: React.ReactNode[] = [];
    let i = 0;

    while (i < lines.length) {
        const line = lines[i];

        if (!line.trim()) {
            i += 1;
            continue;
        }

        // Ordered list
        if (OL_RE.test(line)) {
            const items: string[] = [];
            while (i < lines.length && OL_RE.test(lines[i])) {
                items.push(lines[i].replace(OL_RE, ""));
                i += 1;
            }
            blocks.push(
                <ol key={`ol-${i}`} className="ml-4 list-decimal space-y-1">
                    {items.map((it, idx) => (
                        <li key={idx} className="pl-1">
                            {renderInline(it, `oli-${i}-${idx}`)}
                        </li>
                    ))}
                </ol>,
            );
            continue;
        }

        // Unordered list
        if (UL_RE.test(line)) {
            const items: string[] = [];
            while (i < lines.length && UL_RE.test(lines[i])) {
                items.push(lines[i].replace(UL_RE, ""));
                i += 1;
            }
            blocks.push(
                <ul key={`ul-${i}`} className="ml-4 list-disc space-y-1 marker:text-emerald-500">
                    {items.map((it, idx) => (
                        <li key={idx} className="pl-1">
                            {renderInline(it, `uli-${i}-${idx}`)}
                        </li>
                    ))}
                </ul>,
            );
            continue;
        }

        // Paragraph: consume consecutive non-empty, non-list lines.
        const para: string[] = [];
        while (
            i < lines.length &&
            lines[i].trim() &&
            !UL_RE.test(lines[i]) &&
            !OL_RE.test(lines[i])
        ) {
            para.push(lines[i].trim());
            i += 1;
        }
        blocks.push(
            <p key={`p-${i}`} className="leading-relaxed">
                {renderInline(para.join(" "), `p-${i}`)}
            </p>,
        );
    }

    return <div className="space-y-2">{blocks}</div>;
}