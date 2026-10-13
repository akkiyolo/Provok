import type { Metadata } from "next";

import { MessagesView } from "@/components/messages";

export const metadata: Metadata = { title: "Messages", robots: { index: false } };

export default function MessagesPage() {
  return <MessagesView />;
}
