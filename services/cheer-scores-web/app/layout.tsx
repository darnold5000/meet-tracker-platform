import type { Metadata, Viewport } from "next";
import Script from "next/script";
import { MvpFeedbackFab } from "@/components/MvpFeedbackFab";
import { MvpPwaInstallProvider } from "@/components/MvpPwaInstallProvider";
import "./globals.css";

export const viewport: Viewport = {
  themeColor: "#00adef",
};

export const metadata: Metadata = {
  title: "Cheer Tracker",
  description: "Track live all-star cheer competition scores",
  manifest: "/manifest.webmanifest?v=5",
  icons: {
    icon: "/icon-512.png?v=5",
    apple: "/apple-touch-icon.png?v=5",
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Cheer Tracker",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <MvpPwaInstallProvider>{children}</MvpPwaInstallProvider>
        <MvpFeedbackFab />
        <Script src="https://tally.so/widgets/embed.js" strategy="lazyOnload" />
      </body>
    </html>
  );
}
