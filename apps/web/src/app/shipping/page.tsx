import type { Metadata } from "next";

import { BUSINESS, LegalPage } from "@/components/legal";

export const metadata: Metadata = { title: "Shipping & Delivery Policy" };

export default function ShippingPage() {
  return (
    <LegalPage title="Shipping & Delivery Policy">
      <p>{BUSINESS.brand} sells digital credits only. Nothing is shipped physically.</p>
      <p>Credits are delivered to your account wallet immediately after a successful payment — usually within seconds and at most within 30 minutes. If they don&apos;t arrive, email <a href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a> with your order ID.</p>
    </LegalPage>
  );
}
