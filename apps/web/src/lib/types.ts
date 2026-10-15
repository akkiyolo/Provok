// Types mirroring the Provok API (backend/app/services/debate_view.py and routes).

export type Position = "for" | "against";
export type Mode = "hvh" | "hva" | "ava";
export type Timing = "live" | "async" | "video";
export type RoundName = "opening" | "rebuttal" | "cross_exam" | "closing";
export type TurnKind = "argument" | "question" | "answer";
export type Status =
  | "waiting_for_opponent"
  | "swarm_fallback_offered"
  | "lobby"
  | "opening"
  | "rebuttal"
  | "cross_exam"
  | "closing"
  | "judging"
  | "completed"
  | "paused"
  | "abandoned"
  | "cancelled";
export type ClaimStatus = "unaddressed" | "rebutted" | "conceded" | "supported" | "unsupported" | "misattributed";

export const ROUNDS: RoundName[] = ["opening", "rebuttal", "cross_exam", "closing"];
export const ROUND_LABEL: Record<RoundName, string> = {
  opening: "Opening",
  rebuttal: "Rebuttal",
  cross_exam: "Cross-ex",
  closing: "Closing",
};

export interface PublicUser {
  id: string | null;
  username: string;
  display_name: string;
  avatar_url: string | null;
  rating: number | null;
  /** Finished debates; the rating means something only once this is above zero. */
  debates?: number;
  /** Provok's own accounts (e.g. @provok). */
  verified?: boolean;
}

export interface ModelRef {
  key: string;
  display_name: string;
  provider: string | null;
  tier: string | null;
}

export interface SideView {
  id: string;
  position: Position;
  participant_type: "human" | "swarm" | null;
  user: PublicUser | null;
  invited: PublicUser | null;
  model: ModelRef | null;
  persona: string | null;
  ready: boolean;
  /** The open seat can only be taken through a private invite link. */
  invite_link: boolean;
  /** Only sent to the debate's creator. */
  invite_token: string | null;
}

export interface Citation {
  n: number;
  url: string;
  title: string;
}

export interface TurnView {
  id: string;
  round: RoundName;
  turn_index: number;
  position: Position;
  kind: TurnKind;
  content: string;
  hidden: boolean;
  word_count: number;
  source: "typed" | "transcript" | "swarm";
  is_forfeit: boolean;
  model: { key: string; display_name: string } | null;
  citations: Citation[];
  created_at: string;
}

export interface Tally {
  for: number;
  against: number;
  for_count: number;
  against_count: number;
  for_share: number;
}

export interface RoundView {
  round: RoundName;
  started_at: string | null;
  ended_at: string | null;
  vote_open: boolean;
  vote_closes_at: string | null;
  vote_closed_at: string | null;
  tally: Tally | null;
}

export interface ClaimView {
  id: string;
  seq: number;
  position: Position;
  turn_id: string;
  text: string;
  source_url: string | null;
  responds_to: number | null;
  status: ClaimStatus;
}

export interface Momentum {
  for_share: number;
  rounds_closed: number;
  votes_weight: number;
}

export interface DebateView {
  id: string;
  question: string;
  topic_category: string;
  mode: Mode;
  timing: Timing;
  status: Status;
  current_round: RoundName | null;
  turn_index: number;
  expected: { position: Position; kind: TurnKind } | null;
  deadline_at: string | null;
  server_time: string;
  word_limit: number;
  is_featured: boolean;
  paused_reason: string | null;
  conceded_position: Position | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  version: string | null;
  created_by: string | null;
  sides: SideView[];
  turns: TurnView[];
  rounds: RoundView[];
  claims: ClaimView[];
  momentum: Momentum | null;
  verdict: { winner_position: Position | null; is_close: boolean; scores: Record<string, number> } | null;
  viewers: number;
  viewer: { position: Position | null; is_creator: boolean; is_admin: boolean; votes: Record<string, Position> } | null;
}

export interface DebateCard {
  id: string;
  question: string;
  topic_category: string;
  mode: Mode;
  timing: Timing;
  status: Status;
  current_round: RoundName | null;
  deadline_at: string | null;
  is_featured: boolean;
  created_at: string;
  completed_at: string | null;
  sides: SideView[];
  momentum: Momentum | null;
  votes: number;
  viewers: number;
  winner_position: Position | null;
}

export interface Page<T> {
  items: T[];
  next_cursor?: string | null;
}

export interface Me {
  id: string;
  email: string;
  email_verified: boolean;
  username: string;
  display_name: string;
  avatar_url: string | null;
  bio: string | null;
  role: "user" | "admin";
  status: "active" | "restricted" | "banned" | "deleted";
  rating: number;
  wins: number;
  losses: number;
  draws: number;
  credits: number;
  free_ai_debates_left: number;
  has_password: boolean;
  onboarded: boolean;
  email_notifications: boolean;
  banner_url: string | null;
  website: string | null;
  location: string | null;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  expires_in: number;
  user: Me;
}

export interface Meta {
  models: ModelRef[];
  default_model_key: string | null;
  personas: { key: string; description: string }[];
  word_limit: { default: number; min: number; max: number };
  timings: Record<Timing, number>;
  free_ai_debates: number;
  credit_costs: { standard: number; flagship: number };
  free_covers_flagship: boolean;
  categories: string[];
  blocked_categories: string[];
  features: { ai_debates: boolean; video: boolean; payments: boolean; google_login: boolean; signups: boolean };
  livekit_url: string | null;
  question_chars: { min: number; max: number };
}

export interface VerdictResponse {
  debate: DebateView;
  judge: {
    winner_position: Position | null;
    is_close: boolean;
    scores: { for?: number; against?: number; margin?: number; runs_agree?: boolean };
    per_round: Partial<Record<RoundName, Record<Position, Record<string, number>>>>;
    reasoning: string;
    decisive_claims: { id: string; seq: number; position: Position; text: string; status: ClaimStatus }[];
    model_key: string | null;
    model_name: string | null;
    created_at: string;
  };
  audience: {
    per_round: Partial<Record<RoundName, Tally | null>>;
    totals: { for: number; against: number };
    winner_position: Position | null;
    final_vote_open: boolean;
    final_vote_closes_at: string | null;
  };
  clips: { id: string; url: string; reason: string; caption: string | null; duration_ms: number }[];
}

export interface Profile {
  id: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  bio: string | null;
  rating: number;
  rank: number;
  wins: number;
  losses: number;
  draws: number;
  created_at: string;
  followers: number;
  following: number;
  is_following: boolean;
  is_me: boolean;
  debates: DebateCard[];
  posts_count: number;
  is_blocked: boolean;
  blocks_you: boolean;
  is_muted: boolean;
  banner_url: string | null;
  website: string | null;
  location: string | null;
  verified: boolean;
  pinned: PostView | null;
}

// ── Social layer (backend/app/services/posts.py build_views) ───────────────

export interface PostMedia {
  id: string;
  url: string;
  width: number;
  height: number;
  alt: string | null;
}

export interface PostView {
  id: string;
  /** The row this item came from: the post itself, or the repost that put it in a feed. */
  feed_id: string;
  author: PublicUser | null;
  text: string | null;
  created_at: string;
  /** Detected script: en, hi, bn, ta, … (null for photo-only posts). */
  lang: string | null;
  /** Debates started from this post with "Challenge". */
  debates: number;
  factcheck: FactCheck | null;
  media: PostMedia[];
  reply_to: { id: string; username: string | null } | null;
  counts: { replies: number; reposts: number; quotes: number; likes: number; views: number };
  link_preview: LinkPreview | null;
  poll: Poll | null;
  /** Pinned to its author's profile. */
  pinned: boolean;
  viewer: { liked: boolean; reposted: boolean; bookmarked: boolean; is_author: boolean };
  reposted_by: PublicUser | null;
  /** Embedded quoted post; `{ unavailable: true }` when it was deleted or hidden. */
  quote?: PostView | { unavailable: true } | null;
}

export interface LinkPreview {
  url: string;
  title: string;
  description: string | null;
  image: string | null;
  site: string;
}

export interface Poll {
  /** `votes` is null until you've voted (or the poll has ended), so nobody votes with the herd. */
  options: { label: string; votes: number | null }[];
  total: number;
  ends_at: string;
  closed: boolean;
  viewer_vote: number | null;
}

export interface Suggestion {
  user: PublicUser;
  reason: string;
}

export interface DailyDebate {
  day: string;
  question: string;
  post: PostView | null;
  debate: DebateCard | null;
}

export interface Conversation {
  id: string;
  with: PublicUser;
  last: DirectMessage | null;
  last_message_at: string | null;
  unread: boolean;
  /** From someone you don't follow and you haven't replied yet. */
  request: boolean;
}

export interface DirectMessage {
  id: string;
  text: string;
  mine: boolean;
  created_at: string;
}

export type FactCheckRating = "accurate" | "mostly_accurate" | "missing_context" | "misleading" | "false" | "unverifiable";

export interface FactCheck {
  status: "pending" | "done" | "opinion" | "failed" | null;
  rating: FactCheckRating | null;
  summary: string | null;
  sources: { title: string; url: string }[];
}

export interface Trend {
  tag: string;
  people: number;
  posts: number;
}

export interface Wallet {
  credits: number;
  free_ai_debates_total: number;
  free_ai_debates_left: number;
  costs: { standard: number; flagship: number; free_covers_flagship: boolean };
  packs: { id: string; credits: number; amount_inr: number; label?: string }[];
  payments_enabled: boolean;
  razorpay_key_id: string | null;
  history: { delta: number; reason: string; balance_after: number; ref_id: string | null; created_at: string }[];
  payments: { id: string; pack_id: string; amount_inr: number; credits: number; status: string; created_at: string }[];
}

export interface NotificationItem {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  link: string | null;
  read: boolean;
  created_at: string;
}
