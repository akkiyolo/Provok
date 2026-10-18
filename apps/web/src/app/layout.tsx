import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";

import { VerifyBanner } from "@/components/auth-pages";
import { InviteBanner } from "@/components/invite";
import { BottomNav, Footer, TopNav } from "@/components/nav";
import { Providers } from "@/components/providers";

import "./globals.css";

const display = Bricolage_Grotesque({ variable: "--font-bricolage", subsets: ["latin"], weight: ["500", "700", "800"], display: "swap" });
const sans = Geist({ variable: "--font-geist-sans", subsets: ["latin"], display: "swap" });
const mono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"], display: "swap" });

const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: { default: "Provok — Ask anything. Pick your corners.", template: "%s · Provok" },
  description:
    "The live arena for ideas. Debate humans or AI swarms, watch model-vs-model showdowns, vote every round, and get an evidence-based verdict from an impartial AI judge.",
  applicationName: "Provok",
  keywords: ["debate", "AI debate", "argument", "Claude vs GPT", "debate app", "live debate", "AI judge"],
  openGraph: { type: "website", siteName: "Provok", locale: "en_IN" },
  twitter: { card: "summary_large_image" },
  formatDetection: { telephone: false },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0b" },
    { media: "(prefers-color-scheme: light)", color: "#f6f4ef" },
  ],
};

// Runs before paint: dark-first, honour saved choice, no flash.
const themeScript = `try{var t=localStorage.getItem('provok:theme');document.documentElement.dataset.theme=t==='light'||t==='dark'?t:'dark'}catch(e){document.documentElement.dataset.theme='dark'}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning className={`${display.variable} ${sans.variable} ${mono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-dvh">
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-full focus:bg-text focus:px-4 focus:py-2 focus:text-bg">
          Skip to content
        </a>
        <Providers>
          <Suspense fallback={<div className="h-14 border-b border-line sm:h-16" />}>
            <TopNav />
            <VerifyBanner />
            <InviteBanner />
          </Suspense>
          <main id="main">{children}</main>
          <Suspense>
            <Footer />
            <BottomNav />
          </Suspense>
        </Providers>
      </body>
    </html>
  );
}
