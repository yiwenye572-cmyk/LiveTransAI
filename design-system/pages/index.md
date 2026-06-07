# LiveTransAI — Index Page Overrides

> Overrides [`../livetransai/MASTER.md`](../livetransai/MASTER.md) for the landing page only.

## Layout

- **Pattern:** Desktop left-right split (Hero left, features right); mobile/tablet stacked
- **Structure:**
  - Left: logo, tagline, dual CTA, hint at bottom
  - Right: section title「核心能力」→ Featured correction → 1×3 feature grid
- **CTA:** Only in Hero; feature cards are informational, not clickable
- **Container:** max-width 1320px, vertically centered on viewport (min-height 100vh)

## Colors

Use dark OLED tokens from [`frontend/theme.css`](../../frontend/theme.css), not the light palette in MASTER:

- Accent (links, highlights): `--color-accent` (teal `#5eead4`)
- Featured card accent: `--color-correction` left border
- CTA buttons: `--color-cta` (blue, action-only)

## Featured Card (Scheme B)

- Full-width correction card with static Diff mock
- Badge: 「核心差异」
- Diff: strikethrough old text + accent new text

## Feature Grid (Scheme A)

- 3 cards: 实时双语字幕, 多场景与术语, 语音播报
- Desktop: 3 columns; tablet: 2+1; mobile: 1 column

## Icons

- Lucide-style inline SVG, 24×24 viewBox
- No emoji icons

## Interaction

- Feature cards: no `cursor: pointer`, no scale hover
- Optional subtle border/background transition on hover (200ms)
- Buttons/links in Hero only: pointer + focus ring from theme

## Responsive

- **Desktop (≥1024px):** 2-column split, equal vertical center, gap 40–64px
- **Tablet (769–1023px):** Stacked hero + features; 3-col grid for standard cards
- **Mobile (≤768px):** Single column stack
- Container max-width: 1320px (1920px viewport centered)
