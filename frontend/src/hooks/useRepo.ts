import { useEffect, useState } from "react";
import { getRepo } from "../api/client";
import type { RepoOut } from "../api/types";

export function useRepo(id: number) {
  const [repo, setRepo] = useState<RepoOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getRepo(id)
      .then((data) => {
        if (!cancelled) setRepo(data);
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
  }, [id]);

  return { repo, loading, error };
}
