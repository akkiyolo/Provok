import type { Metadata } from "next";
import { Suspense } from "react";

import { ProfileView } from "@/components/account";

export async function generateMetadata({ params }: PageProps<"/u/[username]">): Promise<Metadata> {
  const { username } = await params;
  return { title: `@${username}`, description: `Debates, rating and record of @${username} on Provok.` };
}

async function Route({ params }: { params: PageProps<"/u/[username]">["params"] }) {
  const { username } = await params;
  return <ProfileView username={decodeURIComponent(username)} />;
}

export default function ProfilePage({ params }: PageProps<"/u/[username]">) {
  return <Suspense><Route params={params} /></Suspense>;
}
