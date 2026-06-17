"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  Send,
  Loader2,
  User,
  Play,
  X,
  ExternalLink,
  Clock,
  Sparkles,
  Youtube,
  Instagram,
  Twitter,
  Facebook,
  Music2,
  Globe,
  Check,
  Volume2,
  VolumeX,
  LucideIcon,
} from "lucide-react";

// --------------------------------------------------------------------------- //
//  Τύποι
// --------------------------------------------------------------------------- //

type CharacterId = "sakis" | "alekos";
type Platform = "youtube" | "instagram" | "tiktok" | "x" | "facebook" | "web";

interface Character {
  id: CharacterId;
  name: string;
  initial: string;
  tagline: string;
  grad: string;
  img?: string; // φωτό· αν λείπει ή αποτύχει, δείχνει monogram
}

interface Source {
  platform: Platform;
  sourceId: string;
  url: string;
  title: string;
  timestamp: number;
}

interface ChatMessage {
  role: "user" | "bot";
  text: string;
  character?: CharacterId;
  source?: Source;
}

interface AskResponse {
  answer: string;
  platform: Platform;
  source_id: string;
  url: string;
  title: string;
  timestamp: number;
  audio_base64: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const SEEK_LEAD_SECONDS = 3;

const CHARACTERS: Character[] = [
  {
    id: "sakis",
    name: "Σάκης",
    initial: "Σ",
    tagline: "Ο γκουρού του gaming",
    grad: "from-[#e10600] to-[#7a0000]",
    img: "/images/sakis.jpg",
  },
  {
    id: "alekos",
    name: "Αλέκος",
    initial: "Α",
    tagline: "Ο μάστορας του unboxing",
    grad: "from-[#ff3b1f] to-[#9a1500]",
    img: "/images/alekos.jpg",
  },
];

interface PlatformMeta {
  label: string;
  Icon: LucideIcon;
  color: string;
  canEmbed: boolean; // αν υποστηρίζει inline preview με άλμα σε σημείο
}

const PLATFORM_META: Record<Platform, PlatformMeta> = {
  youtube: { label: "YouTube", Icon: Youtube, color: "#ff0000", canEmbed: true },
  instagram: { label: "Instagram", Icon: Instagram, color: "#e1306c", canEmbed: false },
  tiktok: { label: "TikTok", Icon: Music2, color: "#25f4ee", canEmbed: false },
  x: { label: "X", Icon: Twitter, color: "#ffffff", canEmbed: false },
  facebook: { label: "Facebook", Icon: Facebook, color: "#1877f2", canEmbed: false },
  web: { label: "Web", Icon: Globe, color: "#9aa0a6", canEmbed: false },
};

const SUGGESTIONS = [
  "Τι είναι το Dark Files;",
  "Τι λένε για τις φωτογραφίες Polaroid;",
  "Πες μου για τις εξαφανίσεις",
];

// Ποια platforms είναι ενεργά τώρα και ποια «Σύντομα» στο UI.
const PLATFORM_STRIP: { p: Platform; soon: boolean }[] = [
  { p: "youtube", soon: false },
  { p: "instagram", soon: true },
  { p: "tiktok", soon: true },
  { p: "x", soon: true },
  { p: "facebook", soon: true },
];

// --------------------------------------------------------------------------- //
//  Βοηθητικά
// --------------------------------------------------------------------------- //

const charById = (id?: CharacterId) => CHARACTERS.find((c) => c.id === id);

function formatTime(total: number): string {
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const ytThumb = (id: string) => `https://i.ytimg.com/vi/${id}/hqdefault.jpg`;

function ytEmbedUrl(src: Source): string {
  const start = Math.max(0, src.timestamp - SEEK_LEAD_SECONDS);
  return `https://www.youtube.com/embed/${src.sourceId}?start=${start}&autoplay=1&rel=0&modestbranding=1`;
}

// Το link «προς τα έξω» — για YouTube με timestamp, αλλιώς το canonical URL.
function outUrl(src: Source): string {
  if (src.platform === "youtube") {
    const start = Math.max(0, src.timestamp - SEEK_LEAD_SECONDS);
    return `https://www.youtube.com/watch?v=${src.sourceId}&t=${start}s`;
  }
  return src.url;
}

// --------------------------------------------------------------------------- //
//  Component
// --------------------------------------------------------------------------- //

export default function Home() {
  const [character, setCharacter] = useState<CharacterId>("sakis");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<Source | null>(null);
  const [muted, setMuted] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mutedRef = useRef(false);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Φόρτωση προτίμησης ήχου από το localStorage (μία φορά)
  useEffect(() => {
    const saved = window.localStorage.getItem("uh_muted");
    if (saved === "1") {
      setMuted(true);
      mutedRef.current = true;
    }
  }, []);

  const toggleMuted = () => {
    setMuted((prev) => {
      const next = !prev;
      mutedRef.current = next;
      window.localStorage.setItem("uh_muted", next ? "1" : "0");
      if (next && audioRef.current) audioRef.current.pause(); // σταμάτα ό,τι παίζει
      return next;
    });
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setPreview(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const playAudio = useCallback((base64: string) => {
    if (!base64 || mutedRef.current) return; // σεβασμός στο mute
    if (!audioRef.current) audioRef.current = new Audio();
    audioRef.current.src = `data:audio/mpeg;base64,${base64}`;
    audioRef.current.play().catch(() => {});
  }, []);

  const ask = async (query: string) => {
    if (!query.trim() || loading) return;

    setMessages((prev) => [...prev, { role: "user", text: query }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, voice_character: character }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail?.detail ?? "Κάτι πήγε στραβά.");
      }
      const data: AskResponse = await res.json();

      setMessages((prev) => [
        ...prev,
        {
          role: "bot",
          text: data.answer,
          character,
          source: data.source_id
            ? {
                platform: data.platform,
                sourceId: data.source_id,
                url: data.url,
                title: data.title,
                timestamp: data.timestamp,
              }
            : undefined,
        },
      ]);

      if (data.audio_base64) playAudio(data.audio_base64);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        { role: "bot", text: `Ωχ μάγκα, κάτι έσκασε: ${err.message}`, character },
      ]);
    } finally {
      setLoading(false);
    }
  };

  // Επιστροφή στην αρχική (καθαρισμός συνομιλίας)
  const goHome = () => {
    setMessages([]);
    setPreview(null);
    setInput("");
    if (audioRef.current) audioRef.current.pause();
  };

  const activeChar = charById(character)!;
  const isEmpty = messages.length === 0;

  return (
    <div className="uh-bg flex h-screen flex-col">
      {/* ===== Header ===== */}
      <header className="flex items-center justify-between border-b border-white/5 bg-white/[0.02] px-6 py-4 backdrop-blur-xl">
        <Logo onClick={goHome} />
        <div className="flex items-center gap-3">
          {/* Mute / unmute */}
          <button
            onClick={toggleMuted}
            title={muted ? "Ενεργοποίηση φωνής" : "Σίγαση φωνής"}
            aria-pressed={muted}
            className={`flex h-9 w-9 items-center justify-center rounded-full border transition ${
              muted
                ? "border-white/10 bg-white/5 text-white/40 hover:text-white"
                : "border-uh-red/40 bg-uh-red/10 text-uh-red shadow-[0_0_14px_rgba(225,6,0,0.3)]"
            }`}
          >
            {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
          </button>

          <div className="flex items-center gap-1 rounded-full border border-white/10 bg-white/5 p-1 backdrop-blur-xl">
            {CHARACTERS.map((c) => {
            const active = character === c.id;
            return (
              <button
                key={c.id}
                onClick={() => setCharacter(c.id)}
                className={`flex items-center gap-2 rounded-full py-1.5 pl-1.5 pr-4 text-sm font-semibold transition ${
                  active
                    ? "bg-uh-red text-white shadow-[0_0_18px_rgba(225,6,0,0.45)]"
                    : "text-white/50 hover:text-white"
                }`}
              >
                <Avatar char={c} className="h-6 w-6 rounded-full" />
                <span className="hidden sm:inline">{c.name}</span>
              </button>
            );
          })}
          </div>
        </div>
      </header>

      {/* ===== Chat ===== */}
      <main className="uh-scroll flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-8">
          {isEmpty ? (
            <EmptyState activeChar={activeChar} onPick={ask} />
          ) : (
            <div className="space-y-6">
              {messages.map((m, i) => (
                <MessageBubble key={i} message={m} onPreview={setPreview} />
              ))}
              {loading && <TypingIndicator char={activeChar} />}
              <div ref={chatEndRef} />
            </div>
          )}
        </div>
      </main>

      {/* ===== Input bar ===== */}
      <div className="border-t border-white/5 bg-black/40 px-4 py-4 backdrop-blur-xl">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(input);
          }}
          className="mx-auto flex max-w-3xl items-center gap-3"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={`Ρώτα τον ${activeChar.name}... π.χ. «Τι είπαν για...»`}
            disabled={loading}
            className="flex-1 rounded-2xl border border-white/10 bg-white/5 px-5 py-4 text-sm outline-none transition placeholder:text-white/30 focus:border-uh-red focus:bg-white/[0.07] focus:shadow-[0_0_24px_rgba(225,6,0,0.2)]"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="flex h-14 w-14 items-center justify-center rounded-2xl bg-uh-red transition hover:bg-uh-red-bright hover:shadow-[0_0_24px_rgba(225,6,0,0.5)] disabled:opacity-30 disabled:shadow-none"
          >
            {loading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <Send className="h-5 w-5" />
            )}
          </button>
        </form>
        <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-white/25">
          Beta · μόνο πηγές YouTube &amp; βίντεο 2026 · οι απαντήσεις βασίζονται σε περιεχόμενο των Unboxholics και μπορεί να περιέχουν ανακρίβειες
        </p>
      </div>

      {preview && <PreviewModal source={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}

// --------------------------------------------------------------------------- //
//  Brand & Avatar
// --------------------------------------------------------------------------- //

const UH_LOGO_URL =
  "https://yt3.googleusercontent.com/dGO1IqMD9GiAcqfEp1JyUQjw41WG7Me2aFYc6HBqpde4TAkRrxw6GecfVUpvS6ao1eq1eVRy4Q=s160-c-k-c0x00ffffff-no-rj";

function Logo({ onClick }: { onClick?: () => void }) {
  const [err, setErr] = useState(false);
  return (
    <button
      onClick={onClick}
      title="Αρχική"
      className="flex items-center gap-3 rounded-xl transition hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-uh-red"
    >
      <div className="relative flex h-11 w-11 items-center justify-center overflow-hidden rounded-xl bg-gradient-to-br from-[#e10600] to-[#8a0000] shadow-[0_0_28px_rgba(225,6,0,0.5)] ring-1 ring-white/10">
        {!err ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={UH_LOGO_URL}
            alt="Unboxholics"
            onError={() => setErr(true)}
            className="h-full w-full object-cover"
          />
        ) : (
          <span className="text-lg font-black italic tracking-tighter text-white">UH</span>
        )}
        <span className="pointer-events-none absolute -left-2 top-0 h-full w-1/2 -skew-x-12 bg-white/10" />
      </div>
      <div className="text-left">
        <h1 className="flex items-center gap-2 text-xl font-black italic tracking-tight">
          uh<span className="text-uh-red">.ai</span>
          <span className="rounded-full border border-uh-red/40 bg-uh-red/10 px-1.5 py-0.5 text-[9px] font-bold uppercase not-italic tracking-wider text-uh-red">
            Beta
          </span>
        </h1>
        <p className="text-[11px] uppercase tracking-[0.2em] text-white/40">
          Unboxholics Voice Companion
        </p>
      </div>
    </button>
  );
}

function Avatar({ char, className = "" }: { char: Character; className?: string }) {
  const [err, setErr] = useState(false);
  return (
    <div className={`relative shrink-0 overflow-hidden ${className}`}>
      {char.img && !err ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={char.img}
          alt={char.name}
          onError={() => setErr(true)}
          className="h-full w-full object-cover"
        />
      ) : (
        <div
          className={`flex h-full w-full items-center justify-center bg-gradient-to-br ${char.grad} font-black text-white`}
        >
          {char.initial}
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
//  Chat sub-components
// --------------------------------------------------------------------------- //

function EmptyState({
  activeChar,
  onPick,
}: {
  activeChar: Character;
  onPick: (q: string) => void;
}) {
  return (
    <div className="flex flex-col items-center pt-8 text-center">
      <Avatar
        char={activeChar}
        className="mb-6 h-20 w-20 rounded-2xl text-3xl shadow-[0_0_45px_rgba(225,6,0,0.5)] ring-1 ring-white/10"
      />
      <h2 className="text-3xl font-black tracking-tight sm:text-4xl">
        Ρώτα ό,τι θες για τα βίντεο
      </h2>
      <p className="mt-3 max-w-md text-white/50">
        Ο <span className="font-semibold text-white">{activeChar.name}</span> ψάχνει στα
        βίντεο των Unboxholics στο YouTube, σου απαντάει και σε πάει στο ακριβές σημείο.
      </p>

      <div className="mt-8 flex w-full flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-center">
        {SUGGESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => onPick(q)}
            className="group flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/70 backdrop-blur-xl transition hover:border-uh-red/50 hover:text-white"
          >
            <Sparkles className="h-4 w-4 text-uh-red" />
            {q}
          </button>
        ))}
      </div>

      <PlatformStrip />
    </div>
  );
}

function PlatformStrip() {
  return (
    <div className="mt-12 flex flex-col items-center gap-3">
      <p className="text-[11px] uppercase tracking-[0.25em] text-white/30">
        Πηγές περιεχομένου
      </p>
      <div className="flex flex-wrap items-center justify-center gap-2">
        {PLATFORM_STRIP.map(({ p, soon }) => {
          const m = PLATFORM_META[p];
          const Icon = m.Icon;
          return (
            <div
              key={p}
              className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                soon
                  ? "border-white/10 bg-white/[0.03] text-white/35"
                  : "border-uh-red/40 bg-uh-red/10 text-white shadow-[0_0_18px_rgba(225,6,0,0.25)]"
              }`}
            >
              <Icon
                className="h-3.5 w-3.5"
                style={{ color: soon ? "currentColor" : m.color }}
              />
              {m.label}
              {soon ? (
                <span className="ml-0.5 rounded-full bg-white/10 px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-white/45">
                  Σύντομα
                </span>
              ) : (
                <Check className="h-3 w-3 text-uh-red" />
              )}
            </div>
          );
        })}
      </div>
      <p className="mt-2 max-w-md text-center text-[11px] leading-relaxed text-white/30">
        Beta έκδοση — προς το παρόν χρησιμοποιούμε μόνο πηγές <span className="text-white/50">YouTube</span> και βίντεο του <span className="text-white/50">2026</span>.
      </p>
    </div>
  );
}

function MessageBubble({
  message,
  onPreview,
}: {
  message: ChatMessage;
  onPreview: (s: Source) => void;
}) {
  const isUser = message.role === "user";
  const char = charById(message.character);

  return (
    <div
      className={`flex animate-fade-up gap-3 ${
        isUser ? "flex-row-reverse" : "flex-row"
      }`}
    >
      {isUser ? (
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/10">
          <User className="h-4 w-4" />
        </div>
      ) : char ? (
        <Avatar
          char={char}
          className="h-9 w-9 rounded-xl text-sm shadow-[0_0_18px_rgba(225,6,0,0.4)] ring-1 ring-white/10"
        />
      ) : (
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-uh-red text-sm">
          UH
        </div>
      )}

      <div className={`max-w-[85%] ${isUser ? "items-end" : "items-start"}`}>
        {!isUser && char && (
          <p className="mb-1 text-xs font-bold uppercase tracking-wider text-uh-red">
            {char.name} · UH-Bot
          </p>
        )}
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed backdrop-blur-xl ${
            isUser
              ? "bg-white/10 text-white"
              : "border border-white/10 bg-white/[0.04] text-white/90 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
          }`}
        >
          {message.text}
        </div>

        {message.source && (
          <SourceCard source={message.source} onPreview={onPreview} />
        )}
      </div>
    </div>
  );
}

function SourceCard({
  source,
  onPreview,
}: {
  source: Source;
  onPreview: (s: Source) => void;
}) {
  const meta = PLATFORM_META[source.platform] ?? PLATFORM_META.web;
  const { Icon } = meta;
  const hasTimestamp = source.platform === "youtube" && source.timestamp > 0;

  return (
    <div className="mt-3 overflow-hidden rounded-2xl border border-white/10 bg-white/[0.04] shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] backdrop-blur-xl">
      <div className="flex gap-3 p-3">
        {/* Visual: YouTube thumbnail (preview) ή platform-icon tile (link-out) */}
        {meta.canEmbed ? (
          <button
            onClick={() => onPreview(source)}
            className="group relative h-[68px] w-[120px] shrink-0 overflow-hidden rounded-lg bg-black ring-1 ring-white/10"
            title="Preview"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={ytThumb(source.sourceId)}
              alt={source.title}
              className="h-full w-full object-cover opacity-80 transition group-hover:scale-105 group-hover:opacity-100"
            />
            <span className="absolute inset-0 flex items-center justify-center bg-black/30 transition group-hover:bg-black/10">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-uh-red shadow-[0_0_18px_rgba(225,6,0,0.6)]">
                <Play className="h-4 w-4 fill-white" />
              </span>
            </span>
          </button>
        ) : (
          <a
            href={outUrl(source)}
            target="_blank"
            rel="noopener noreferrer"
            className="group relative flex h-[68px] w-[120px] shrink-0 items-center justify-center overflow-hidden rounded-lg ring-1 ring-white/10"
            style={{ background: `linear-gradient(135deg, ${meta.color}33, #111)` }}
            title={`Άνοιγμα στο ${meta.label}`}
          >
            <Icon className="h-7 w-7 transition group-hover:scale-110" style={{ color: meta.color }} />
          </a>
        )}

        {/* Πληροφορίες */}
        <div className="flex min-w-0 flex-1 flex-col justify-between py-0.5">
          <div className="flex items-center gap-2">
            <span
              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide"
              style={{ backgroundColor: `${meta.color}22`, color: meta.color }}
            >
              <Icon className="h-3 w-3" />
              {meta.label}
            </span>
            {hasTimestamp && (
              <span className="inline-flex items-center gap-1 rounded-full bg-uh-red/15 px-2 py-0.5 text-[10px] font-semibold text-uh-red">
                <Clock className="h-3 w-3" />
                {formatTime(source.timestamp)}
              </span>
            )}
          </div>

          <p className="line-clamp-2 text-sm font-semibold text-white/90">
            {source.title || "Πηγή Unboxholics"}
          </p>

          <div className="flex items-center gap-3">
            {meta.canEmbed && (
              <button
                onClick={() => onPreview(source)}
                className="text-xs font-semibold text-white/60 transition hover:text-white"
              >
                Preview
              </button>
            )}
            <a
              href={outUrl(source)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs font-semibold text-white/60 transition hover:text-white"
            >
              {meta.label} <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}

function TypingIndicator({ char }: { char: Character }) {
  return (
    <div className="flex animate-fade-up gap-3">
      <Avatar
        char={char}
        className="h-9 w-9 rounded-xl text-sm shadow-[0_0_18px_rgba(225,6,0,0.4)] ring-1 ring-white/10"
      />
      <div className="flex flex-col">
        <p className="mb-1 text-xs font-bold uppercase tracking-wider text-uh-red">
          {char.name} · UH-Bot
        </p>
        <div className="flex items-center gap-1.5 rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-4 backdrop-blur-xl">
          {[0, 0.15, 0.3].map((d) => (
            <span
              key={d}
              className="h-2 w-2 animate-dot rounded-full bg-uh-red"
              style={{ animationDelay: `${d}s` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function PreviewModal({ source, onClose }: { source: Source; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md"
      onClick={onClose}
    >
      <div
        className="w-full max-w-3xl animate-pop overflow-hidden rounded-2xl border border-white/10 bg-[#0c0c0c]/95 shadow-2xl backdrop-blur-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-white/5 px-5 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">
              {source.title || "Βίντεο Unboxholics"}
            </p>
            {source.timestamp > 0 && (
              <p className="text-xs text-uh-red">
                Ξεκινά στο {formatTime(source.timestamp)}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-white/60 transition hover:bg-white/10 hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="aspect-video w-full bg-black">
          <iframe
            className="h-full w-full"
            src={ytEmbedUrl(source)}
            title={source.title}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        </div>

        <div className="flex justify-end border-t border-white/5 px-5 py-3">
          <a
            href={outUrl(source)}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg bg-uh-red px-4 py-2 text-sm font-semibold transition hover:bg-uh-red-bright"
          >
            Άνοιγμα στο YouTube <ExternalLink className="h-4 w-4" />
          </a>
        </div>
      </div>
    </div>
  );
}
