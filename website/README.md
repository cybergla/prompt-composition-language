# pcl-website

Landing page for [PCL — Prompt Composition Language](https://github.com/cybergla/prompt-composition-language).

Live at: **https://cybergla.github.io/pcl-website**

## Stack

- Vanilla HTML/CSS/JS — no build step
- [Tailwind CSS](https://tailwindcss.com) via CDN
- [JetBrains Mono](https://fonts.google.com/specimen/JetBrains+Mono) + [Syne](https://fonts.google.com/specimen/Syne) via Google Fonts
- Deployed on GitHub Pages via GitHub Actions

## Deployment

Pushing to `main` triggers `.github/workflows/deploy.yml`, which deploys to GitHub Pages automatically.

To enable Pages on a new repo: **Settings → Pages → Source → GitHub Actions**.
