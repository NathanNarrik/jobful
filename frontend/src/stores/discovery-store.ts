"use client";

import { create } from "zustand";
import { getJob, listJobs, listPopularSkills } from "@/lib/api";
import type { DiscoveryFilters, JobDetail, JobListItem, SkillCount } from "@/types";

type DiscoveryState = {
  jobs: JobListItem[];
  total: number;
  offset: number;
  limit: number;
  filters: DiscoveryFilters;
  popularSkills: SkillCount[];
  activeJob: JobDetail | null;
  loading: boolean;
  detailLoading: boolean;
  error: string | null;
  setFilter: (key: keyof DiscoveryFilters, value: string) => void;
  loadJobs: (offset?: number) => Promise<void>;
  loadSkills: () => Promise<void>;
  openJob: (jobId: string) => Promise<void>;
  closeJob: () => void;
};

const initialFilters: DiscoveryFilters = {
  search: "",
  program_type: "",
  grad_year: "",
  remote_type: "",
  visa_status: "",
  skill: "",
};

export const useDiscoveryStore = create<DiscoveryState>((set, get) => ({
  jobs: [],
  total: 0,
  offset: 0,
  limit: 48,
  filters: initialFilters,
  popularSkills: [],
  activeJob: null,
  loading: false,
  detailLoading: false,
  error: null,
  setFilter: (key, value) => {
    set((state) => ({ filters: { ...state.filters, [key]: value }, offset: 0 }));
  },
  loadJobs: async (offset = 0) => {
    const { filters, limit } = get();
    set({ loading: true, error: null });
    try {
      const result = await listJobs({
        limit,
        offset,
        search: filters.search,
        program_type: filters.program_type,
        grad_year: filters.grad_year,
        remote_type: filters.remote_type,
        visa_status: filters.visa_status,
        skill: filters.skill,
      });
      set({ jobs: result.items, total: result.total, offset: result.offset, loading: false });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Unable to load jobs", loading: false });
    }
  },
  loadSkills: async () => {
    try {
      set({ popularSkills: await listPopularSkills() });
    } catch {
      set({ popularSkills: [] });
    }
  },
  openJob: async (jobId) => {
    set({ detailLoading: true, error: null });
    try {
      set({ activeJob: await getJob(jobId), detailLoading: false });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Unable to load job", detailLoading: false });
    }
  },
  closeJob: () => set({ activeJob: null }),
}));
