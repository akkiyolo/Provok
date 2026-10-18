import type { NextRequest } from "next/server";

// Invite links (/r/<code>): remember who sent the visitor, then show the home page. The API reads this cookie
// when the visitor creates an account (email or Google), so it must be readable on every path.
const CODE = /^[abcdefghjkmnpqrstuvwxyz23456789]{8}$/;
const DAYS = Number(process.env.REFERRAL_COOKIE_DAYS ?? 30);

export async function GET(req: NextRequest, ctx: RouteContext<"/r/[code]">) {
  const { code } = await ctx.params;
  // A relative Location keeps the visitor on whatever host they used (provok.in, staging, localhost).
  const res = new Response(null, { status: 307, headers: { Location: "/", "Cache-Control": "no-store" } });
  if (CODE.test(code)) {
    // Behind Caddy the app itself is spoken to over plain HTTP; the proxy says what the visitor used.
    const https = (req.headers.get("x-forwarded-proto") ?? req.nextUrl.protocol.replace(":", "")) === "https";
    const secure = https ? "; Secure" : "";
    res.headers.append("Set-Cookie", `provok_ref=${code}; Path=/; Max-Age=${DAYS * 86400}; SameSite=Lax${secure}`);
  }
  return res;
}
