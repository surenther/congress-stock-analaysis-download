"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { apiFetch, proxyUrl } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

interface WatchlistItem {
    id: string;
    type: string;
    value: string;
}

interface FeedRow {
    doc_id: string;
    filer_name: string;
    chamber: string;
    filing_date: string;
    ticker: string;
    action: string;
    value_range: string;
}

export default function WatchlistsPage() {
    const qc = useQueryClient();
    const [type, setType] = useState("ticker");
    const [value, setValue] = useState("");

    const list = useQuery({
        queryKey: ["watchlists"],
        queryFn: () =>
            apiFetch<{ items: WatchlistItem[] }>(
                proxyUrl("analytics", "/api/v1/watchlists"),
            ),
    });

    const feed = useQuery({
        queryKey: ["watchlist-feed"],
        queryFn: () =>
            apiFetch<{ results: FeedRow[] }>(
                proxyUrl("analytics", "/api/v1/watchlists/feed"),
            ),
    });

    const add = useMutation({
        mutationFn: () =>
            apiFetch(proxyUrl("analytics", "/api/v1/watchlists"), {
                method: "POST",
                body: JSON.stringify({ type, value }),
            }),
        onSuccess: () => {
            setValue("");
            qc.invalidateQueries({ queryKey: ["watchlists"] });
            qc.invalidateQueries({ queryKey: ["watchlist-feed"] });
        },
    });

    const remove = useMutation({
        mutationFn: (id: string) =>
            apiFetch(proxyUrl("analytics", `/api/v1/watchlists/${id}`), {
                method: "DELETE",
            }),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ["watchlists"] });
            qc.invalidateQueries({ queryKey: ["watchlist-feed"] });
        },
    });

    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-semibold">Watchlists</h1>

            <Card>
                <CardHeader>
                    <CardTitle>Add a watch</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-wrap items-end gap-3">
                    <select
                        className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                        value={type}
                        onChange={(e) => setType(e.target.value)}
                    >
                        <option value="ticker">Ticker</option>
                        <option value="member">Member</option>
                    </select>
                    <Input
                        className="max-w-xs"
                        placeholder={type === "ticker" ? "NVDA" : "Member name"}
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                    />
                    <Button
                        onClick={() => add.mutate()}
                        disabled={!value || add.isPending}
                    >
                        <Plus className="h-4 w-4" /> Add
                    </Button>
                </CardContent>
            </Card>

            <div className="grid gap-4 lg:grid-cols-2">
                <Card>
                    <CardHeader>
                        <CardTitle>Watching</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                        {(list.data?.items ?? []).map((item) => (
                            <div
                                key={item.id}
                                className="flex items-center justify-between rounded-md border p-2 text-sm"
                            >
                                <div className="flex items-center gap-2">
                                    <Badge variant="secondary">{item.type}</Badge>
                                    <span>{item.value}</span>
                                </div>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => remove.mutate(item.id)}
                                >
                                    <Trash2 className="h-4 w-4" />
                                </Button>
                            </div>
                        ))}
                        {!list.data?.items?.length && (
                            <p className="text-sm text-muted-foreground">
                                No watchlist entries yet.
                            </p>
                        )}
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <CardTitle>Monitoring feed</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                        {(feed.data?.results ?? []).map((row, i) => (
                            <div
                                key={`${row.doc_id}-${i}`}
                                className="rounded-md border p-2 text-sm"
                            >
                                <div className="font-medium">{row.filer_name}</div>
                                <div className="text-xs text-muted-foreground">
                                    {row.ticker} · {row.action} · {row.value_range} ·{" "}
                                    {row.filing_date}
                                </div>
                            </div>
                        ))}
                        {!feed.data?.results?.length && (
                            <p className="text-sm text-muted-foreground">
                                No recent activity for your watchlist.
                            </p>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
