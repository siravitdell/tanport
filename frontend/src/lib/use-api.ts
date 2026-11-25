"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";

interface State<T> {
  key: string | null;
  data: T | undefined;
  error: ApiError | Error | undefined;
}

export interface ApiResult<T> {
  data: T | undefined;
  error: ApiError | Error | undefined;
  loading: boolean;
  reload: () => void;
}

/**
 * GET `path` (null = don't fetch). A 401 means the session is gone: go to /login.
 * State is keyed by path, so a new path shows `loading` without a stale result.
 */
export function useApi<T>(path: string | null): ApiResult<T> {
  const router = useRouter();
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<State<T>>({ key: null, data: undefined, error: undefined });
  const key = path === null ? null : `${path}#${nonce}`;

  useEffect(() => {
    if (path === null || key === null) return;
    let active = true;
    api.get<T>(path).then(
      (data) => {
        if (active) setState({ key, data, error: undefined });
      },
      (error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          router.replace("/login");
          return;
        }
        setState({
          key,
          data: undefined,
          error: error instanceof Error ? error : new Error(String(error)),
        });
      },
    );
    return () => {
      active = false;
    };
  }, [path, key, router]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const current = state.key === key;
  return {
    data: current ? state.data : undefined,
    error: current ? state.error : undefined,
    loading: path !== null && !current,
    reload,
  };
}
