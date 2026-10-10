import type { Metadata } from "next";

import { BUSINESS, LegalPage } from "@/components/legal";

export const metadata: Metadata = { title: "Contact us" };

export default function ContactPage() {
  return (
    <LegalPage title="Contact us">
      <p>Questions, payments, account issues, safety reports or press — we read everything.</p>
      <ul>
        <li>Email: <a href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a></li>
        {BUSINESS.phone && <li>Phone: {BUSINESS.phone}</li>}
        <li>Business: {BUSINESS.name}</li>
        <li>Address: {BUSINESS.address}</li>
      </ul>
      <p>For content problems, the fastest route is the Report button on any turn, debate or profile.</p>
    </LegalPage>
  );
}
