import { AppShell } from "@/components/app-shell";
import { CompaniesClient } from "@/components/companies-client";

export default function CompaniesPage() {
  return (
    <AppShell>
      <CompaniesClient />
    </AppShell>
  );
}
