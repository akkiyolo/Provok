"use client";

import { ConnectionState, type Participant, type RemoteTrack, Room, RoomEvent, Track } from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";

import { useToast } from "@/components/toast";
import { Button, SideTag } from "@/components/ui";
import { errorMessage, post } from "@/lib/api";
import { wsBase, wsTicket } from "@/lib/realtime";
import { cx, sideName } from "@/lib/format";
import type { DebateView, Position, SideView } from "@/lib/types";

interface TokenResponse { token: string; url: string; room: string; role: "debater" | "spectator"; position: Position | null; can_speak: boolean }

function weakConnection(): boolean {
  const c = (navigator as Navigator & { connection?: { effectiveType?: string; saveData?: boolean } }).connection;
  return !!c && (c.saveData === true || ["slow-2g", "2g", "3g"].includes(c.effectiveType ?? ""));
}

function Tile({ side, position, participant, caption, speaking, audioOnly }: {
  side: SideView | undefined; position: Position; participant: Participant | null; caption?: string; speaking: boolean; audioOnly: boolean;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [hasVideo, setHasVideo] = useState(false);
  useEffect(() => {
    const el = videoRef.current;
    if (!participant || !el) return;
    const sync = () => {
      const pub = participant.getTrackPublication(Track.Source.Camera);
      const track = pub?.track;
      if (track && !audioOnly && !pub.isMuted) {
        track.attach(el);
        setHasVideo(true);
      } else {
        setHasVideo(false);
      }
    };
    sync();
    participant.on("trackSubscribed", sync).on("trackUnsubscribed", sync).on("trackMuted", sync).on("trackUnmuted", sync).on("localTrackPublished", sync);
    return () => {
      participant.off("trackSubscribed", sync).off("trackUnsubscribed", sync).off("trackMuted", sync).off("trackUnmuted", sync).off("localTrackPublished", sync);
      participant.getTrackPublication(Track.Source.Camera)?.track?.detach(el);
    };
  }, [participant, audioOnly]);

  return (
    <figure className={cx("relative overflow-hidden rounded-3xl border-2 bg-surface-2 transition-shadow",
      position === "for" ? "border-for" : "border-against",
      speaking && (position === "for" ? "shadow-[0_0_48px_var(--for-glow)]" : "shadow-[0_0_48px_var(--against-glow)]"))}>
      <div className="relative aspect-[4/5] sm:aspect-video">
        <video ref={videoRef} autoPlay playsInline muted={participant?.isLocal} className={cx("size-full object-cover", !hasVideo && "hidden")} />
        {!hasVideo && (
          <div className="absolute inset-0 grid place-items-center">
            <span className={cx("font-display text-5xl font-extrabold", position === "for" ? "text-for" : "text-against")}>
              {sideName(side).charAt(0)}
            </span>
          </div>
        )}
        <div className="absolute left-3 top-3 flex items-center gap-2 rounded-full bg-black/55 px-2.5 py-1 backdrop-blur">
          <SideTag position={position} />
          <span className="text-[12px] font-semibold text-white">{sideName(side)}</span>
        </div>
        {speaking && <span className="absolute right-3 top-3 rounded-full bg-live px-2 py-0.5 font-mono text-[10px] font-bold text-white">SPEAKING</span>}
        {!participant && <span className="absolute bottom-3 left-3 text-[12px] text-dim">Not connected yet</span>}
      </div>
      <figcaption aria-live="polite" className="min-h-[3.25rem] border-t border-line px-3 py-2 text-[13.5px] leading-snug text-text/90">
        {caption || <span className="text-faint">Live captions appear here.</span>}
      </figcaption>
    </figure>
  );
}

export function VideoStage({ debate, captions, speakers }: { debate: DebateView; captions: Partial<Record<Position, string>>; speakers: Position[] | null }) {
  const toast = useToast();
  const roomRef = useRef<Room | null>(null);
  const sttRef = useRef<{ ws: WebSocket; rec: MediaRecorder } | null>(null);
  const [state, setState] = useState<ConnectionState>(ConnectionState.Disconnected);
  const [participants, setParticipants] = useState<Record<string, Participant>>({});
  const [role, setRole] = useState<TokenResponse | null>(null);
  const [audioOnly, setAudioOnly] = useState(() => (typeof navigator !== "undefined" ? weakConnection() : false));
  const [ending, setEnding] = useState(false);
  const on = debate.status === "lobby" || ["opening", "rebuttal", "cross_exam", "closing"].includes(debate.status);

  const sideFor = (p: Position) => debate.sides.find((s) => s.position === p);
  const identityFor = (p: Position) => (sideFor(p)?.user?.id ? `u:${sideFor(p)!.user!.id}` : "");

  const refresh = useCallback(() => {
    const room = roomRef.current;
    if (!room) return;
    const map: Record<string, Participant> = { [room.localParticipant.identity]: room.localParticipant };
    room.remoteParticipants.forEach((p) => (map[p.identity] = p));
    setParticipants(map);
  }, []);

  const startStt = useCallback(async (room: Room) => {
    if (sttRef.current) return;
    const mic = room.localParticipant.getTrackPublication(Track.Source.Microphone)?.track?.mediaStreamTrack;
    if (!mic || typeof MediaRecorder === "undefined") return;
    const ticket = await wsTicket();
    if (!ticket) return;
    const ws = new WebSocket(`${wsBase()}/ws/debates/${debate.id}/stt?ticket=${encodeURIComponent(ticket)}`);
    ws.binaryType = "arraybuffer";
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
    const rec = new MediaRecorder(new MediaStream([mic]), mime ? { mimeType: mime } : undefined);
    rec.ondataavailable = (e) => e.data.size && ws.readyState === 1 && ws.send(e.data);
    ws.onopen = () => rec.start(250);
    ws.onclose = () => rec.state !== "inactive" && rec.stop();
    sttRef.current = { ws, rec };
  }, [debate.id]);

  useEffect(() => {
    if (!on) return;
    let cancelled = false;
    const room = new Room({ adaptiveStream: true, dynacast: true });
    roomRef.current = room;
    room
      .on(RoomEvent.ConnectionStateChanged, (s) => setState(s))
      .on(RoomEvent.ParticipantConnected, refresh)
      .on(RoomEvent.ParticipantDisconnected, refresh)
      .on(RoomEvent.TrackSubscribed, (_t: RemoteTrack) => {
        if (_t.kind === Track.Kind.Audio) _t.attach();
        refresh();
      })
      .on(RoomEvent.ParticipantPermissionsChanged, async () => {
        // The server decides who may speak; follow it.
        const allowed = room.localParticipant.permissions?.canPublishSources?.includes(1 /* MICROPHONE */) ?? false;
        await room.localParticipant.setMicrophoneEnabled(allowed).catch(() => undefined);
        if (allowed) void startStt(room);
      });

    (async () => {
      try {
        const tok = await post<TokenResponse>(`/video/${debate.id}/token`);
        if (cancelled) return;
        setRole(tok);
        await room.connect(tok.url, tok.token);
        if (tok.role === "debater") {
          if (!audioOnly) await room.localParticipant.setCameraEnabled(true).catch(() => toast("Camera blocked — you're on audio only.", "info"));
          if (tok.can_speak) {
            await room.localParticipant.setMicrophoneEnabled(true);
            void startStt(room);
          }
        }
        refresh();
      } catch (e) {
        toast(`Video unavailable: ${errorMessage(e)}`, "error");
      }
    })();
    return () => {
      cancelled = true;
      sttRef.current?.ws.close();
      sttRef.current = null;
      void room.disconnect();
      roomRef.current = null;
    };
    // audioOnly intentionally excluded: toggling it shouldn't reconnect the room
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debate.id, on, refresh, startStt, toast]);

  useEffect(() => {
    const room = roomRef.current;
    if (room && role?.role === "debater" && room.state === ConnectionState.Connected) {
      void room.localParticipant.setCameraEnabled(!audioOnly).catch(() => undefined);
    }
  }, [audioOnly, role]);

  const endTurn = async () => {
    setEnding(true);
    try {
      await post(`/debates/${debate.id}/end-turn`);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setEnding(false);
    }
  };

  const mySpeaking = role?.position && speakers?.includes(role.position);
  return (
    <section aria-label="Video stage" className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3">
        {(["for", "against"] as Position[]).map((p) => (
          <Tile key={p} side={sideFor(p)} position={p} participant={participants[identityFor(p)] ?? null}
            caption={captions[p]} speaking={!!speakers?.includes(p)} audioOnly={audioOnly} />
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className={cx("font-mono text-[11px]", state === ConnectionState.Connected ? "text-ok" : "text-faint")}>
          ● {state === ConnectionState.Connected ? "connected" : state}
        </span>
        <label className="ml-2 flex items-center gap-2 text-[13px] text-dim">
          <input type="checkbox" checked={audioOnly} onChange={(e) => setAudioOnly(e.target.checked)} className="accent-[var(--for)]" />
          Audio only
        </label>
        {role?.role === "debater" && mySpeaking && debate.expected?.position === role.position && (
          <Button size="sm" variant={role.position === "for" ? "for" : "against"} className="ml-auto" loading={ending} onClick={endTurn}>
            I&apos;m done — end my turn
          </Button>
        )}
      </div>
    </section>
  );
}
