// Shared layout + business details for legal/info pages (server component).
// The details are public (shown on every legal page) and baked in at build time from GitHub repository variables
// of the same names (see .github/workflows/deploy.yml). Bracketed text is shown until they are set.

export const BUSINESS = {
  name: process.env.NEXT_PUBLIC_LEGAL_NAME || "[Your registered business name]",
  brand: "Provok",
  email: process.env.NEXT_PUBLIC_SUPPORT_EMAIL || "support@provok.in",
  address: process.env.NEXT_PUBLIC_LEGAL_ADDRESS || "[Registered address, City, State, PIN, India]",
  city: process.env.NEXT_PUBLIC_LEGAL_CITY || "[City]",
  phone: process.env.NEXT_PUBLIC_SUPPORT_PHONE || "",
  grievanceOfficer: process.env.NEXT_PUBLIC_GRIEVANCE_OFFICER || "[Grievance Officer name]",
  updated: "11 October 2026",
};

export function LegalPage({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <article className="mx-auto max-w-3xl px-4 pb-20 pt-10 sm:px-6">
      <p className="font-mono text-[11px] font-bold tracking-[0.18em] text-faint">LAST UPDATED {BUSINESS.updated.toUpperCase()}</p>
      <h1 className="font-display mt-3 text-[clamp(2.2rem,6vw,3.4rem)] font-extrabold leading-[0.95]">{title}</h1>
      <div className="mt-8 flex flex-col gap-5 text-[15.5px] leading-[1.75] text-text/90 [&_a]:underline [&_a]:underline-offset-4 [&_h2]:font-display [&_h2]:mt-6 [&_h2]:text-2xl [&_h2]:font-bold [&_li]:ml-5 [&_li]:list-disc [&_ul]:flex [&_ul]:flex-col [&_ul]:gap-2">
        {children}
      </div>
    </article>
  );
}
