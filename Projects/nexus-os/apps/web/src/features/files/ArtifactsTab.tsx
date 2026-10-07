import { formatRelativeTime } from "@nexus/shared";
import { Badge, Button, Card, EmptyState, ErrorState, Select, Skeleton } from "@nexus/ui";
import { Package } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { useArtifactContent, useArtifactVersions, useArtifacts } from "../../lib/agentQueries";
import { errorMessage } from "../../lib/queries";

function ArtifactViewer({ id }: { id: string }) {
  const versions = useArtifactVersions(id);
  const [picked, setPicked] = useState<number | undefined>();
  const content = useArtifactContent(id, picked);
  const [preview, setPreview] = useState(false);
  const artifact = content.data?.artifact;
  const canPreview = artifact?.type === "website" || artifact?.type === "chart";

  return (
    <Card className="mt-3">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{artifact?.name ?? "Artifact"}</span>
        {versions.data && versions.data.length > 1 ? (
          <>
            <label htmlFor="artifact-version" className="sr-only">
              Version
            </label>
            <Select
              id="artifact-version"
              className="h-8 w-auto py-0 text-[13px]"
              value={String(content.data?.version ?? "")}
              onChange={(e) => setPicked(Number(e.target.value))}
            >
              {[...versions.data].reverse().map((v) => (
                <option key={v.version} value={v.version}>
                  Version {v.version} · {formatRelativeTime(v.created_at)}
                </option>
              ))}
            </Select>
          </>
        ) : null}
        {canPreview ? (
          <Button size="sm" onClick={() => setPreview((p) => !p)}>
            {preview ? "Show source" : "Preview"}
          </Button>
        ) : null}
      </header>
      <div className="p-3">
        {content.isPending ? (
          <Skeleton className="h-32" />
        ) : content.isError ? (
          <ErrorState message={errorMessage(content.error)} onRetry={() => void content.refetch()} />
        ) : preview && canPreview ? (
          // Sandboxed with no permissions: no scripts, no forms, no same-origin access, no navigation.
          <iframe
            title={`Preview of ${content.data.artifact.name}`}
            sandbox=""
            srcDoc={content.data.content}
            className="h-96 w-full rounded-md border border-line bg-white"
          />
        ) : (
          <>
            {content.data.truncated ? <p className="mb-2 text-xs text-warning">Only the start is shown.</p> : null}
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words font-mono text-xs">{content.data.content}</pre>
          </>
        )}
      </div>
    </Card>
  );
}

export function ArtifactsTab({ projectId }: { projectId: string }) {
  const artifacts = useArtifacts(projectId);
  const [params, setParams] = useSearchParams();
  const selected = params.get("artifact") ?? undefined;

  function select(id: string) {
    const next = new URLSearchParams(params);
    next.set("artifact", id);
    setParams(next, { replace: true });
  }

  if (artifacts.isPending) return <Skeleton className="h-28" />;
  if (artifacts.isError) return <ErrorState message={errorMessage(artifacts.error)} onRetry={() => void artifacts.refetch()} />;
  if (artifacts.data.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={<Package />}
          title="No deliverables yet"
          description="Reports, documents, code and pages that agents finish are saved here, and every change keeps its earlier versions."
        />
      </Card>
    );
  }
  return (
    <div>
      <Card>
        <ul className="divide-y divide-line" aria-label="Artifacts">
          {artifacts.data.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                onClick={() => select(a.id)}
                aria-current={selected === a.id ? "true" : undefined}
                className="flex w-full flex-wrap items-center gap-2 px-3 py-2.5 text-left text-[13px] hover:bg-raised/60 aria-[current=true]:bg-raised"
              >
                <span className="min-w-0 flex-1 truncate font-medium">{a.name}</span>
                <Badge>{a.type}</Badge>
                <span className="font-mono text-[11px] text-fg-subtle">v{a.version}</span>
                <span className="text-xs text-fg-subtle">{formatRelativeTime(a.updated_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      </Card>
      {selected ? <ArtifactViewer key={selected} id={selected} /> : null}
    </div>
  );
}
