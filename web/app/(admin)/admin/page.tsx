"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, RefreshCw } from "lucide-react";
import { apiFetch, proxyUrl } from "@/lib/api-client";
import { formatUtc } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";

interface Job {
    service: string;
    job_id: string;
    status: string;
    chamber: string | null;
    total_documents: number | null;
    processed_documents: number | null;
    created_at: string | null;
    error_message: string | null;
}

const SERVICES = ["downloader", "parser", "vectorizer"];

export default function AdminPipelinePage() {
    const qc = useQueryClient();

    const jobs = useQuery({
        queryKey: ["admin-jobs"],
        queryFn: () =>
            apiFetch<{ jobs: Job[] }>(proxyUrl("admin", "/api/v1/jobs?limit=25")),
        refetchInterval: 5000,
    });

    const trigger = useMutation({
        mutationFn: (service: string) =>
            apiFetch(proxyUrl("admin", `/api/v1/admin/pipeline/${service}/trigger`), {
                method: "POST",
                body: JSON.stringify({}),
            }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-jobs"] }),
    });

    const retry = useMutation({
        mutationFn: ({ service, jobId }: { service: string; jobId: string }) =>
            apiFetch(
                proxyUrl(
                    "admin",
                    `/api/v1/admin/pipeline/jobs/${service}/${jobId}/retry`,
                ),
                { method: "POST" },
            ),
        onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-jobs"] }),
    });

    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-semibold">Pipeline Orchestration</h1>

            <Card>
                <CardHeader>
                    <CardTitle>Manual triggers</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-wrap gap-2">
                    {SERVICES.map((service) => (
                        <Button
                            key={service}
                            variant="outline"
                            onClick={() => trigger.mutate(service)}
                            disabled={trigger.isPending}
                        >
                            <Play className="h-4 w-4" /> Trigger {service}
                        </Button>
                    ))}
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>Recent jobs</CardTitle>
                </CardHeader>
                <CardContent>
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Service</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead>Progress</TableHead>
                                <TableHead>Chamber</TableHead>
                                <TableHead>Created</TableHead>
                                <TableHead />
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {(jobs.data?.jobs ?? []).map((job) => (
                                <TableRow key={`${job.service}-${job.job_id}`}>
                                    <TableCell className="font-medium">{job.service}</TableCell>
                                    <TableCell>
                                        <Badge
                                            variant={
                                                job.status === "COMPLETED"
                                                    ? "success"
                                                    : job.status === "FAILED"
                                                        ? "destructive"
                                                        : "secondary"
                                            }
                                        >
                                            {job.status}
                                        </Badge>
                                    </TableCell>
                                    <TableCell>
                                        {job.processed_documents ?? 0} / {job.total_documents ?? "—"}
                                    </TableCell>
                                    <TableCell>{job.chamber ?? "—"}</TableCell>
                                    <TableCell className="text-xs text-muted-foreground">
                                        {formatUtc(job.created_at)}
                                    </TableCell>
                                    <TableCell>
                                        {job.status === "FAILED" && (
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={() =>
                                                    retry.mutate({
                                                        service: job.service,
                                                        jobId: job.job_id,
                                                    })
                                                }
                                            >
                                                <RefreshCw className="h-4 w-4" /> Retry
                                            </Button>
                                        )}
                                    </TableCell>
                                </TableRow>
                            ))}
                            {!jobs.data?.jobs?.length && (
                                <TableRow>
                                    <TableCell colSpan={6} className="text-muted-foreground">
                                        No jobs yet.
                                    </TableCell>
                                </TableRow>
                            )}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>
        </div>
    );
}
