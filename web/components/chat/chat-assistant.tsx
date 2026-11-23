"use client";

import { useState } from "react";
import { MessageSquare, Send, X } from "lucide-react";
import { apiFetch, proxyUrl, scopeViolationCode, type ApiError } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CitationCard, type Citation } from "./citation-card";
import { ScopeErrorBanner } from "./scope-error-banner";

interface RagResponse {
    query: string;
    answer: string;
    sources: Citation[];
    user_chamber_access: string[];
}

interface ScopeDetail {
    code: string;
    message: string;
    requested_chamber?: string | null;
    allowed_chambers?: string[];
}

/**
 * Floating RAG chat assistant (FR-3.1). Opens a slide-out panel, answers
 * natural-language questions, renders grounded citations, and shows an inline
 * banner on a chamber-scope violation.
 */
export function ChatAssistant() {
    const [open, setOpen] = useState(false);
    const [prompt, setPrompt] = useState("");
    const [loading, setLoading] = useState(false);
    const [answer, setAnswer] = useState<string | null>(null);
    const [sources, setSources] = useState<Citation[]>([]);
    const [scopeError, setScopeError] = useState<ScopeDetail | null>(null);
    const [error, setError] = useState<string | null>(null);

    async function ask(e: React.FormEvent) {
        e.preventDefault();
        if (!prompt.trim()) return;
        setLoading(true);
        setError(null);
        setScopeError(null);
        setAnswer(null);
        setSources([]);
        try {
            const data = await apiFetch<RagResponse>(
                proxyUrl("rag", "/api/v1/rag/query"),
                {
                    method: "POST",
                    body: JSON.stringify({ prompt, top_k: 8 }),
                },
            );
            setAnswer(data.answer);
            setSources(data.sources ?? []);
        } catch (err) {
            const apiError = err as ApiError;
            if (scopeViolationCode(err) === "CHAMBER_SCOPE_VIOLATION") {
                setScopeError(apiError.detail as ScopeDetail);
            } else {
                setError(apiError.message);
            }
        } finally {
            setLoading(false);
        }
    }

    return (
        <>
            <Button
                className="fixed bottom-6 right-6 z-40 h-12 w-12 rounded-full shadow-lg"
                size="icon"
                onClick={() => setOpen((v) => !v)}
                aria-label="Open assistant"
            >
                {open ? <X className="h-5 w-5" /> : <MessageSquare className="h-5 w-5" />}
            </Button>

            {open && (
                <div className="fixed bottom-24 right-6 z-40 flex h-[32rem] w-96 flex-col rounded-lg border bg-background shadow-xl">
                    <div className="border-b px-4 py-3 font-medium">AI Assistant</div>
                    <div className="flex-1 space-y-3 overflow-y-auto p-4">
                        {scopeError && (
                            <ScopeErrorBanner
                                message={scopeError.message}
                                allowedChambers={scopeError.allowed_chambers}
                                requestedChamber={scopeError.requested_chamber}
                            />
                        )}
                        {error && <p className="text-sm text-destructive">{error}</p>}
                        {answer && (
                            <div className="whitespace-pre-wrap text-sm">{answer}</div>
                        )}
                        {sources.length > 0 && (
                            <div className="space-y-2">
                                <p className="text-xs font-medium text-muted-foreground">
                                    Sources
                                </p>
                                {sources.map((c, i) => (
                                    <CitationCard key={`${c.doc_id}-${i}`} citation={c} />
                                ))}
                            </div>
                        )}
                        {!answer && !scopeError && !error && (
                            <p className="text-sm text-muted-foreground">
                                Ask a question about congressional disclosures, e.g. “Which House
                                members bought semiconductor stocks?”
                            </p>
                        )}
                    </div>
                    <form onSubmit={ask} className="flex gap-2 border-t p-3">
                        <Input
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value)}
                            placeholder="Ask a question…"
                        />
                        <Button type="submit" size="icon" disabled={loading}>
                            <Send className="h-4 w-4" />
                        </Button>
                    </form>
                </div>
            )}
        </>
    );
}
