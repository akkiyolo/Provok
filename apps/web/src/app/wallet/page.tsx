import type { Metadata } from "next";

import { WalletView } from "@/components/account";

export const metadata: Metadata = { title: "Wallet", robots: { index: false } };

export default function WalletPage() {
  return <WalletView />;
}
