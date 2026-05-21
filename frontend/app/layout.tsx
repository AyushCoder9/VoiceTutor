import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Fraunces } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});
const display = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://voicetutor.local"),
  title: {
    default: "VoiceTutor · Hands-free Spanish tutor",
    template: "%s · VoiceTutor",
  },
  description:
    "A voice-first, hands-free Spanish language tutor powered by Pipecat, Groq, Deepgram, and ElevenLabs. Put the phone down. Talk. Learn.",
  applicationName: "VoiceTutor",
  keywords: ["spanish", "language learning", "voice ai", "pipecat", "tutor"],
  authors: [{ name: "VoiceTutor" }],
  openGraph: {
    title: "VoiceTutor · Hands-free Spanish tutor",
    description: "Voice-first Spanish tutor. Put the phone down. Talk. Learn.",
    siteName: "VoiceTutor",
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "VoiceTutor",
    description: "Voice-first Spanish tutor.",
  },
};

export const viewport: Viewport = {
  themeColor: "#a78bfa",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable} ${display.variable} smooth-scroll`}>
      <body className="bg-ink-950 text-zinc-100 antialiased">
        <div className="aurora" />
        <div className="grid-bg" />
        {children}
      </body>
    </html>
  );
}
