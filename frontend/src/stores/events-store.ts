"use client";

import { create } from "zustand";
import { getEvent, listEventSources, listEvents } from "@/lib/api";
import type { EventDetail, EventFilters, EventListItem, EventSourceSummary } from "@/types";

type EventsState = {
  events: EventListItem[];
  sources: EventSourceSummary[];
  total: number;
  offset: number;
  limit: number;
  filters: EventFilters;
  activeEvent: EventDetail | null;
  loading: boolean;
  detailLoading: boolean;
  error: string | null;
  setFilter: (key: keyof EventFilters, value: string) => void;
  loadEvents: (offset?: number) => Promise<void>;
  loadSources: () => Promise<void>;
  openEvent: (eventId: string) => Promise<void>;
  closeEvent: () => void;
};

const initialFilters: EventFilters = {
  search: "",
  firm: "",
  firm_kind: "",
  event_type: "",
  location_type: "",
  starts_after: "",
};

export const useEventsStore = create<EventsState>((set, get) => ({
  events: [],
  sources: [],
  total: 0,
  offset: 0,
  limit: 48,
  filters: initialFilters,
  activeEvent: null,
  loading: false,
  detailLoading: false,
  error: null,
  setFilter: (key, value) => {
    set((state) => ({ filters: { ...state.filters, [key]: value }, offset: 0 }));
  },
  loadEvents: async (offset = 0) => {
    const { filters, limit } = get();
    set({ loading: true, error: null });
    try {
      const result = await listEvents({
        limit,
        offset,
        search: filters.search,
        firm: filters.firm,
        firm_kind: filters.firm_kind,
        event_type: filters.event_type,
        location_type: filters.location_type,
        starts_after: filters.starts_after,
      });
      set({ events: result.items, total: result.total, offset: result.offset, loading: false });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Unable to load events", loading: false });
    }
  },
  loadSources: async () => {
    try {
      set({ sources: await listEventSources() });
    } catch {
      set({ sources: [] });
    }
  },
  openEvent: async (eventId) => {
    set({ detailLoading: true, error: null });
    try {
      set({ activeEvent: await getEvent(eventId), detailLoading: false });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Unable to load event", detailLoading: false });
    }
  },
  closeEvent: () => set({ activeEvent: null }),
}));
