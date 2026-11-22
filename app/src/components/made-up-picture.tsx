import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** The made-up pictures an empty place shows, drawn by code as the boards draw them (the Pic
 * board): never a real photo. Their colours are the pictures', not the interface's. */
export type Kind = "alps" | "dunes" | "aurora" | "meadow" | "lake" | "bloom";

const SKIES: Record<Kind, string> = {
  alps: "linear-gradient(180deg,#4f86d2 0%,#9ec2ec 58%,#e3edf7 100%)",
  dunes: "linear-gradient(180deg,#f2d2a0 0%,#f8e7cb 60%)",
  aurora: "linear-gradient(180deg,#040d18 0%,#0b2131 60%,#12303f 100%)",
  meadow: "linear-gradient(180deg,#78b1e8 0%,#cde5fa 62%)",
  lake: "linear-gradient(180deg,#eeaf79 0%,#f6d6b0 48%,#a6bfcf 48.4%,#6d8ea7 100%)",
  bloom: "radial-gradient(circle at 50% 46%,#2e3f2b 0%,#141c12 70%)",
};

const SCENES: Record<Kind, ReactNode> = {
  alps: (
    <>
      <path
        d="M0 205 L64 130 L118 172 L186 78 L248 150 L300 108 L360 160 L400 140 L400 300 L0 300 Z"
        fill="#8199bb"
      />
      <path d="M186 78 L168 104 L180 100 L188 110 L196 99 L206 106 Z" fill="#f4f7fb" />
      <path
        d="M0 246 L84 176 L146 216 L228 150 L316 226 L400 196 L400 300 L0 300 Z"
        fill="#46597a"
      />
      <path d="M0 266 Q200 238 400 260 L400 300 L0 300 Z" fill="#3d5537" />
    </>
  ),
  dunes: (
    <>
      <circle cx="300" cy="80" r="20" fill="#fff4dc" />
      <path d="M0 170 Q90 130 180 168 T400 150 L400 300 L0 300 Z" fill="#e3ab6a" />
      <path d="M0 214 Q110 168 230 210 T400 196 L400 300 L0 300 Z" fill="#cd8b4d" />
      <path d="M0 258 Q140 214 280 254 T400 246 L400 300 L0 300 Z" fill="#b2713c" />
    </>
  ),
  aurora: (
    <>
      <circle cx="40" cy="30" r="1.2" fill="#ffffff" opacity=".8" />
      <circle cx="170" cy="22" r="1.3" fill="#ffffff" opacity=".8" />
      <circle cx="330" cy="24" r="1.4" fill="#ffffff" opacity=".8" />
      <path
        d="M0 120 C60 60 120 150 190 90 S320 50 400 110 L400 150 C320 100 260 170 190 130 S70 120 0 170 Z"
        fill="#3cf0a6"
        opacity=".35"
      />
      <path
        d="M0 230 L70 180 L130 214 L200 160 L270 210 L330 176 L400 214 L400 300 L0 300 Z"
        fill="#071019"
      />
    </>
  ),
  meadow: (
    <>
      <ellipse cx="90" cy="64" rx="38" ry="14" fill="#ffffff" opacity=".92" />
      <ellipse cx="290" cy="90" rx="44" ry="13" fill="#ffffff" opacity=".85" />
      <path d="M0 190 Q120 160 240 182 T400 172 L400 300 L0 300 Z" fill="#86b552" />
      <path d="M0 230 Q160 198 400 226 L400 300 L0 300 Z" fill="#5f9640" />
      <circle cx="104" cy="246" r="3.5" fill="#e86b8a" />
      <circle cx="236" cy="250" r="3.5" fill="#f5d04a" />
    </>
  ),
  lake: (
    <>
      <circle cx="230" cy="112" r="16" fill="#fff0d6" opacity=".9" />
      <path
        d="M0 145 L60 96 L110 128 L170 70 L230 120 L290 88 L350 126 L400 104 L400 145 Z"
        fill="#5a6a86"
      />
      <path
        d="M0 145 L60 194 L110 162 L170 220 L230 170 L290 202 L350 164 L400 186 L400 145 Z"
        fill="#5a6a86"
        opacity=".45"
      />
      <path d="M0 270 Q120 256 260 272 T400 266 L400 300 L0 300 Z" fill="#3b4a3a" />
    </>
  ),
  bloom: (
    <>
      <ellipse cx="90" cy="250" rx="70" ry="18" fill="#3f6b3a" transform="rotate(-24 90 250)" />
      <g transform="translate(200 146)">
        {[0, 45, 90, 135, 180, 225, 270, 315].map((turn, at) => (
          <ellipse
            key={turn}
            cx="0"
            cy="-50"
            rx="22"
            ry="46"
            fill={at % 2 ? "#f7c3d4" : "#f29bb6"}
            transform={`rotate(${turn})`}
          />
        ))}
        <circle cx="0" cy="0" r="20" fill="#f6cf4d" />
      </g>
    </>
  ),
};

/** One made-up picture, filling its box. */
export function MadeUpPicture({ kind, className }: { kind: Kind; className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn("relative overflow-hidden rounded-4", className)}
      style={{ background: SKIES[kind] }}
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 400 300"
        preserveAspectRatio="xMidYMid slice"
        className="absolute inset-0 size-full"
      >
        {SCENES[kind]}
      </svg>
    </div>
  );
}
