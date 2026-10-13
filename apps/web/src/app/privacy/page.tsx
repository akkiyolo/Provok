import type { Metadata } from "next";

import { BUSINESS, LegalPage } from "@/components/legal";

export const metadata: Metadata = { title: "Privacy Policy" };

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy">
      <p>This policy explains how {BUSINESS.name} processes personal data on {BUSINESS.brand}, on the web and in our Android app, in line with India&apos;s Digital Personal Data Protection Act, 2023 (DPDP Act) and the IT Rules, 2011.</p>
      <h2>What we collect</h2>
      <ul>
        <li><b>Account data:</b> email, username, display name, optional photo and bio; a hashed password (never stored in plain text) or your Google account identifier.</li>
        <li><b>Posts:</b> what you post, reply, quote or repost, the photos you attach, and your likes, bookmarks, blocks and mutes.</li>
        <li><b>Direct messages:</b> the messages you send and receive. They are stored on our servers (not end-to-end encrypted) so we can deliver them; we don&apos;t read them except to investigate a report or when the law requires.</li>
        <li><b>Debate data:</b> the turns you write or speak, transcripts of video debates (and recordings, if recording is enabled for a debate), your votes, reports and reactions.</li>
        <li><b>Payment data:</b> order and payment identifiers from Razorpay. Card/UPI details are handled by Razorpay, never by us.</li>
        <li><b>Technical data:</b> IP address, device and browser information, error reports, and first-party usage events used for security, abuse prevention and product analytics. To count post views once per person, we keep a short-lived (one hour) record of who viewed a post.</li>
      </ul>
      <h2>Why we use it</h2>
      <ul>
        <li>To run debates, judge them, show results and rankings, and send account and debate notifications.</li>
        <li>To keep the platform safe: rate limiting, fraud and vote-manipulation detection, moderation.</li>
        <li>To process payments and meet legal and tax obligations.</li>
        <li>To find and fix errors, and to improve the product using aggregated analytics.</li>
      </ul>
      <p>We process your data on the basis of your consent, given when you create an account, and for the legitimate uses the DPDP Act allows (such as complying with law). We do not sell your data or use it for third-party advertising.</p>
      <h2>Service providers we use</h2>
      <p>These companies process data for us, only to provide the Service and under their contractual terms:</p>
      <ul>
        <li><b>Amazon Web Services</b> (India, Mumbai region): hosting, database, file storage, email delivery and uptime monitoring. Most AI models also run on AWS (Amazon Bedrock), where your debate text stays with AWS (some requests are processed in other AWS regions) and is not shared with the companies that made the models.</li>
        <li><b>Other AI model providers</b> (Groq, Google, Anthropic, OpenAI; servers mainly in the United States): debate text, when a debate uses one of their models, to generate AI turns, extract claims, moderate content and judge debates.</li>
        <li><b>Tavily</b> (United States): web searches built from debate topics, so AI debaters can cite sources. Searches do not include your account details.</li>
        <li><b>LiveKit</b> and <b>Deepgram</b> (United States): live audio and video, and speech-to-text, for video debates only.</li>
        <li><b>Razorpay</b> (India): payments.</li>
        <li><b>Sentry</b> (United States): error reports, with passwords, tokens and cookies removed before sending.</li>
        <li><b>Google</b>: &ldquo;Continue with Google&rdquo; sign-in, if you choose it.</li>
      </ul>
      <p>When a post contains a link, our server visits that page once to build a preview card (title, description, image); the image is then loaded by your browser from the linked site.</p>
      <p>Some of these providers process data outside India. We only transfer data to countries the Government of India has not restricted under the DPDP Act.</p>
      <h2>Who else sees it</h2>
      <p>Debates, usernames, profiles, ratings and vote counts are public. Otherwise we share data only with the providers above, and with authorities when legally required.</p>
      <h2>Emails</h2>
      <p>Account emails (email confirmation, password reset) are sent when you ask for them. Debate emails (challenges, your turn, verdicts) can be turned off at any time with the unsubscribe link in each email or in Settings → Email.</p>
      <h2>Cookies and storage</h2>
      <p>We use one essential cookie to keep you signed in, and a short-lived one while you sign in with Google. Your browser also stores small preferences such as the colour theme. We use no advertising or third-party tracking cookies.</p>
      <h2>The Android app</h2>
      <p>The app shows the {BUSINESS.brand} website and collects nothing beyond what the website does. It does not read your contacts, location or files. The camera and microphone are used only when you join a video debate, after Chrome asks for your permission.</p>
      <h2>Retention</h2>
      <p>We keep account data while your account is active. When you delete your account we erase your profile, sign-ins, follows, notifications, posts, likes, bookmarks, blocks, mutes and conversations; debate content is kept but de-identified, because each debate belongs to both sides and its audience. Payment records are kept as long as tax law requires. Server logs and error reports are kept for up to 90 days.</p>
      <h2>Your rights</h2>
      <ul>
        <li><b>Access:</b> download your data from Settings → Download my data.</li>
        <li><b>Correction:</b> edit your profile in Settings, or ask us to correct anything else.</li>
        <li><b>Erasure and withdrawing consent:</b> delete your account in Settings → Delete account. This also withdraws your consent; processing before that stays lawful.</li>
        <li><b>Nomination:</b> nominate someone to exercise these rights if you die or become incapacitated.</li>
        <li><b>Grievances:</b> contact our Grievance Officer (below). If you are not satisfied with the outcome, you can complain to the Data Protection Board of India.</li>
      </ul>
      <h2>Children</h2>
      <p>{BUSINESS.brand} is for people aged 18 and over. We do not knowingly process children&apos;s data; if we learn that an account belongs to someone under 18, we delete it.</p>
      <h2>Security</h2>
      <p>We use encryption in transit and at rest, hashed passwords (Argon2), hashed session tokens, least-privilege access and audit logging. No system is perfectly secure; tell us at <a href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a> if you find a vulnerability. If a breach affects your data, we will notify you and the Data Protection Board as the law requires.</p>
      <h2>Changes</h2>
      <p>If we change this policy in a way that matters, we will tell you by email or in the app before the change takes effect.</p>
      <h2>Grievance Officer</h2>
      <p>{BUSINESS.grievanceOfficer}, {BUSINESS.name}, {BUSINESS.address}. Email: <a href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a>. We acknowledge complaints within 24 hours and resolve them within 15 days.</p>
    </LegalPage>
  );
}
