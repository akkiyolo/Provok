import type { Metadata } from "next";

import { NotificationsView } from "@/components/account";

export const metadata: Metadata = { title: "Notifications", robots: { index: false } };

export default function NotificationsPage() {
  return <NotificationsView />;
}
