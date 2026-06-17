import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "uh.ai — Unboxholics Voice Companion",
  description: "Semantic Video Search & Voice Companion για τους Unboxholics.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="el">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
