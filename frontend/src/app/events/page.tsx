import { AppShell } from "@/components/app-shell";
import { EventsClient } from "@/components/events-client";

export default function EventsPage() {
  return (
    <AppShell>
      <EventsClient />
    </AppShell>
  );
}
