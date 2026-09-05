import type { Metadata, Viewport } from "next";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: {
    default: "ClearLedger | Settlement Control",
    template: "%s | ClearLedger",
  },
  description: "Evidence-first payment-to-bank reconciliation, exception control, and cash confidence.",
  applicationName: "ClearLedger",
};

export const viewport: Viewport = {
  colorScheme: "light",
  themeColor: "#081225",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
