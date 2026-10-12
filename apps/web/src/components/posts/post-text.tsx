import Link from "next/link";

// Mirrors backend/app/services/posts.py: hashtags may use Indian scripts (U+0900–U+0DFF).
const TOKEN_RE = /(https?:\/\/[^\s<]+[^\s<.,:;"')\]!?])|(?<![\w@])@([A-Za-z0-9_]{3,20})\b|(?<![\wऀ-෿#&])#([\wऀ-෿]{1,64})/gu;

/** Post text with clickable links, @mentions and #hashtags. Built from text nodes, never raw HTML. */
export function PostText({ text, className }: { text: string; className?: string }) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(TOKEN_RE)) {
    const i = m.index ?? 0;
    if (i > last) parts.push(text.slice(last, i));
    const [whole, url, user, tag] = m;
    if (url) {
      const shown = url.replace(/^https?:\/\/(www\.)?/, "");
      parts.push(
        <a key={i} href={url} target="_blank" rel="noopener noreferrer nofollow ugc" className="text-text underline decoration-line-strong underline-offset-2 hover:decoration-text">
          {shown.length > 40 ? `${shown.slice(0, 38)}…` : shown}
        </a>,
      );
    } else if (user) {
      parts.push(<Link key={i} href={`/u/${user.toLowerCase()}`} className="font-medium text-text hover:underline">@{user}</Link>);
    } else if (tag && !/^\d+$/.test(tag)) {
      parts.push(<Link key={i} href={`/tag/${encodeURIComponent(tag.toLowerCase())}`} className="font-medium text-text hover:underline">#{tag}</Link>);
    } else {
      parts.push(whole);
    }
    last = i + whole.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <p className={className ?? "whitespace-pre-wrap break-words text-[15px] leading-relaxed"}>{parts}</p>;
}
