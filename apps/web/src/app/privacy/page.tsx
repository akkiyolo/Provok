import type { Metadata } from "next";

import { BUSINESS, LegalPage } from "@/components/legal";

export const metadata: Metadata = { title: "Privacy Policy" };

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy">
      <p>This policy explains how {BUSINESS.name} processes personal data on {BUSINESS.brand}, in line with India&apos;s Digital Personal Data Protection Act, 2023 and the IT Rules, 2011.</p>
      <h2>What we collect</h2>
      <ul>
        <li><b>Account data:</b> email, username, display name, optional photo and bio; a hashed password (never stored in plain text) or your Google account identifier.</li>
        <li><b>Debate data:</b> the turns you write or speak, transcripts and recordings of video debates, your votes, reports and reactions.</li>
        <li><b>Payment data:</b> order and payment identifiers from Razorpay. Card/UPI details are handled by Razorpay, never by us.</li>
        <li><b>Technical data:</b> IP address, device and browser information, and first-party usage events used for security, abuse prevention and product analytics.</li>
      </ul>
      <h2>Why we use it</h2>
      <ul>
        <li>To run debates, judge them, show results and rankings, and send account and debate notifications.</li>
        <li>To keep the platform safe: rate limiting, fraud and vote-manipulation detection, moderation.</li>
        <li>To process payments and meet legal and tax obligations.</li>
        <li>To improve the product using aggregated analytics.</li>
      </ul>
      <h2>AI processing</h2>
      <p>Debate text is sent to third-party AI model providers (such as Anthropic, Google, OpenAI or Groq) to generate AI turns, extract claims, moderate content and judge debates; speech in video debates is sent to a transcription provider. Providers process it under their API terms. We do not sell your data.</p>
      <h2>Who else sees it</h2>
      <p>Debates, usernames, profiles, ratings and vote counts are public. We share data with service providers (hosting, database, email, payments, AI, video, error monitoring) only as needed to run the Service, and with authorities when legally required.</p>
      <h2>Retention</h2>
      <p>We keep account data while your account is active. When you delete your account we erase your profile, sign-ins, follows and notifications; debate content is kept but de-identified. Payment records are kept as required by law.</p>
      <h2>Your rights</h2>
      <p>You can access and download your data (Settings → Download my data), correct it, and delete your account (Settings → Delete account). You may also nominate someone to exercise your rights and raise grievances with our Grievance Officer.</p>
      <h2>Security</h2>
      <p>We use encryption in transit, hashed passwords (Argon2), hashed session tokens, least-privilege access and audit logging. No system is perfectly secure; tell us at <a href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a> if you find a vulnerability.</p>
      <h2>Grievance Officer</h2>
      <p>{BUSINESS.grievanceOfficer}, {BUSINESS.name}, {BUSINESS.address}. Email: <a href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a>. We acknowledge complaints within 24 hours and resolve them within 15 days.</p>
    </LegalPage>
  );
}
