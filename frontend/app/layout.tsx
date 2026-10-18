import "./globals.css";
import type { Metadata, Viewport } from "next";
import PhoneFrame from "@/components/PhoneFrame";

export const metadata: Metadata = {
  title: "ClinicQuick: your story, ready before the visit",
  description: "An AI intake that does the nurse's interview before you see the doctor. Synthetic demo data only.",
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#070C0E" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-CA" suppressHydrationWarning>
      <head>
        {/* pick the theme before first paint: saved choice, else the system setting */}
        <script dangerouslySetInnerHTML={{ __html: `try{var t=localStorage.getItem("cq.theme")||(matchMedia("(prefers-color-scheme: light)").matches?"light":"dark");document.documentElement.dataset.theme=t}catch(e){}` }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,500;12..96,600;12..96,700&family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap"
        />
      </head>
      <body><PhoneFrame>{children}</PhoneFrame></body>
    </html>
  );
}
