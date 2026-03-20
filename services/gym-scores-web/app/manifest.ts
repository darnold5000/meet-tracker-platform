import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Gym Scores",
    short_name: "Gym Scores",
    description: "Live gymnastics meet scores",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#dc2626",
    icons: [
      {
        src: "/icon-192.png",
        type: "image/png",
        sizes: "192x192",
      },
      {
        src: "/icon-512.png",
        type: "image/png",
        sizes: "512x512",
      },
      {
        src: "/icon-1024.png",
        type: "image/png",
        sizes: "1024x1024",
      },
    ],
  };
}
