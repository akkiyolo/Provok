"use client";

import { useQuery } from "@tanstack/react-query";

import { get } from "./api";
import type { Meta } from "./types";

/** Platform config: models, personas, limits, feature flags. Cached for the session. */
export function useMeta(): Meta | undefined {
  return useQuery({ queryKey: ["meta"], queryFn: () => get<Meta>("/meta"), staleTime: 5 * 60_000 }).data;
}
