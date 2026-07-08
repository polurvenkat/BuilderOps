import { useEffect, useState } from "react";
import { getPipelineStatus } from "../api/client";
import type { PipelineStageStatusOut } from "../api/types";

export function usePipelineStatus(repoId: number, enabled: boolean) {
  const [stages, setStages] = useState<PipelineStageStatusOut[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) {
      setStages(null);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    getPipelineStatus(repoId)
      .then((data) => {
        if (!cancelled) setStages(data.stages);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [repoId, enabled]);

  return { stages, loading, error };
}
