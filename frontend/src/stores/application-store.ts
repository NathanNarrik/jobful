"use client";

import { create } from "zustand";
import { createApplication, listApplications, updateApplication } from "@/lib/api";
import type { ApplicationRecord, ApplicationStatus } from "@/types";

type ApplicationState = {
  applications: ApplicationRecord[];
  loading: boolean;
  error: string | null;
  toast: string | null;
  loadApplications: () => Promise<void>;
  trackJob: (jobId: string, status: ApplicationStatus) => Promise<ApplicationRecord | null>;
  moveApplication: (applicationId: string, status: ApplicationStatus, kanbanOrder?: number) => Promise<void>;
  saveNotes: (applicationId: string, notes: string) => Promise<void>;
  clearToast: () => void;
};

export const useApplicationStore = create<ApplicationState>((set, get) => ({
  applications: [],
  loading: false,
  error: null,
  toast: null,
  loadApplications: async () => {
    set({ loading: true, error: null });
    try {
      set({ applications: await listApplications(), loading: false });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : "Unable to load applications",
        loading: false,
      });
    }
  },
  trackJob: async (jobId, status) => {
    try {
      const application = await createApplication(jobId, status);
      set((state) => ({
        applications: [
          application,
          ...state.applications.filter((item) => item.id !== application.id && item.job_id !== jobId),
        ],
        toast: status === "APPLIED" ? "Marked applied. Nice, clean loop." : "Saved to your board.",
      }));
      return application;
    } catch (error) {
      set({ toast: error instanceof Error ? error.message : "Unable to track job" });
      return null;
    }
  },
  moveApplication: async (applicationId, status, kanbanOrder = 0) => {
    const previous = get().applications;
    const next = previous.map((application) =>
      application.id === applicationId ? { ...application, status, kanban_order: kanbanOrder } : application,
    );
    set({ applications: next });
    try {
      const updated = await updateApplication(applicationId, { status, kanban_order: kanbanOrder });
      set((state) => ({
        applications: state.applications.map((application) =>
          application.id === applicationId ? updated : application,
        ),
      }));
    } catch {
      set({ applications: previous, toast: "Update failed. Card restored." });
    }
  },
  saveNotes: async (applicationId, notes) => {
    const previous = get().applications;
    set({
      applications: previous.map((application) =>
        application.id === applicationId ? { ...application, notes } : application,
      ),
    });
    try {
      const updated = await updateApplication(applicationId, { notes });
      set((state) => ({
        applications: state.applications.map((application) =>
          application.id === applicationId ? updated : application,
        ),
      }));
    } catch {
      set({ applications: previous, toast: "Notes did not save." });
    }
  },
  clearToast: () => set({ toast: null }),
}));
