import type { Metadata } from "next";

import { AdminView } from "@/components/admin";

export const metadata: Metadata = { title: "Admin", robots: { index: false, follow: false } };

export default function AdminPage() {
  return <AdminView />;
}
