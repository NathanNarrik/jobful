"use client";

import { useEffect } from "react";
import { useApplicationStore } from "@/stores/application-store";

export function Toast() {
  const { toast, clearToast } = useApplicationStore();

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(clearToast, 2600);
    return () => window.clearTimeout(timeout);
  }, [clearToast, toast]);

  if (!toast) return null;

  return (
    <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-md bg-[var(--foreground)] px-4 py-2 text-sm font-medium text-white shadow-lg">
      {toast}
    </div>
  );
}
