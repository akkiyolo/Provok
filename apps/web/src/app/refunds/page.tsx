import type { Metadata } from "next";

import { BUSINESS, LegalPage } from "@/components/legal";

export const metadata: Metadata = { title: "Refund & Cancellation Policy" };

export default function RefundsPage() {
  return (
    <LegalPage title="Refund & Cancellation Policy">
      <p>Credits are digital and delivered instantly to your {BUSINESS.brand} wallet after a successful payment.</p>
      <h2>Automatic refunds</h2>
      <ul>
        <li>If an AI debate is cancelled before it starts, or stops because of a technical failure on our side, the credits (or free debate) you used are returned to your wallet automatically.</li>
        <li>If you were charged but credits did not arrive within 30 minutes, contact us and we will credit you or refund you in full.</li>
      </ul>
      <h2>Refund requests</h2>
      <ul>
        <li>Unused credit packs can be refunded within 7 days of purchase. Email <a href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a> with your order ID.</li>
        <li>Credits already spent on completed debates are not refundable.</li>
        <li>Approved refunds go back to the original payment method within 5–7 business days via Razorpay.</li>
      </ul>
      <h2>Cancellation</h2>
      <p>There are no subscriptions. You can stop using the Service at any time; unused credits remain in your wallet until your account is deleted.</p>
    </LegalPage>
  );
}
