import { useEffect, useState } from "react";
import { listRepos } from "../api/client";
import type { ListReposParams, RepoOut } from "../api/types";

export function useRepos(params?: ListReposParams) {
  const [repos, setRepos] = useState<RepoOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    listRepos(params)
      .then((data) => {
        if (!cancelled) setRepos(data);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params?.stage, params?.domain, params?.sort]);

  return { repos, loading, error };
}
