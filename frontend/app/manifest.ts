import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Agentic Trading Terminal",
    short_name: "Trading",
    description: "AI agents research; you approve every order.",
    start_url: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#0b0e14",
    theme_color: "#0b0e14",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
