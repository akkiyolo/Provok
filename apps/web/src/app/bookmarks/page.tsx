import type { Metadata } from "next";

import { BookmarksView } from "@/components/posts/feeds";

export const metadata: Metadata = { title: "Bookmarks", robots: { index: false } };

export default function BookmarksPage() {
  return <BookmarksView />;
}
