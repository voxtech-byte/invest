# Design System Specification: Institutional Trading Architecture

## 1. Overview & Creative North Star
**Creative North Star: The Kinetic Ledger**

This design system is built for the high-stakes environment of institutional trading, where precision is the only currency. We are moving away from the "standard SaaS" aesthetic to create a "Kinetic Ledger"—an interface that feels like a high-performance instrument. 

Unlike retail platforms that use bright glows and rounded friendliness, this system prioritizes **Atmospheric Authority**. We achieve this through "The Kinetic Ledger" philosophy: a layout that uses intentional asymmetry to guide the eye toward critical data, high-density information architecture that respects the user's expertise, and a tonal depth that feels carved rather than painted. We do not use "visual fluff." Every pixel must serve a functional purpose in the interpretation of market movement.

---

## 2. Colors & Surface Logic
The palette is rooted in a deep charcoal foundation to reduce eye strain during 12-hour shifts.

### The "No-Line" Rule
Standard UI relies on heavy borders to separate content. In this design system, we prohibit 1px solid borders for major sectioning. Boundaries are defined through **Tonal Transitions**. A sidebar should not be "walled off" by a line; it should be distinguished by sitting on `surface-container-low` (#1B1B1C) against a `background` (#131313) canvas.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers. We use the Material surface tiers to create "nested" depth:
- **Base Level:** `surface` (#131313) - The primary workspace.
- **De-emphasized:** `surface-container-lowest` (#0E0E0E) - For background utility zones.
- **Interactive Layers:** `surface-container` (#202020) and `surface-container-high` (#2A2A2A) - For cards and active widgets.

### Semantic Accents
- **Neutral/Primary:** `primary` (#66D9CC / Teal). Used for focus states and primary actions.
- **Profit (Positive):** `secondary` (#88D982 / Emerald). Use only for upward trends and successful execution.
- **Risk (Negative):** `tertiary` (#FFB3AC / Crimson). Reserved for downward trends, high-risk exposure, and system alerts.

---

## 3. Typography
The typographic system is a study in functional contrast. We pair a high-performance Sans-serif (Inter) with a precision Monospace for all numeric data.

### Hierarchy & Identity
- **Display & Headline:** Used sparingly for dashboard titles or high-level portfolio totals. These use `headline-lg` (2rem) to provide an editorial "anchor" to the page.
- **The Data Layer (Monospace):** All price data, timestamps, and ticker symbols must use a Monospace font. This ensures that when numbers change (e.g., a stock price flickering), the characters do not shift horizontally, maintaining visual stability.
- **Labels:** Use `label-sm` (0.6875rem) in `on-surface-variant` (#BCC9C6) for secondary metadata. This creates a "sub-layer" of information that is readable but doesn't compete with primary figures.

---

## 4. Elevation & Depth
We reject traditional drop shadows in favor of **Tonal Layering**.

- **The Layering Principle:** Depth is achieved by "stacking" surface tiers. To make a widget feel "raised," place a `surface-container-high` element inside a `surface-container` section. The slight shift in gray values creates a sophisticated, architectural lift.
- **The "Ghost Border" Fallback:** If a container requires a physical boundary for accessibility, use a "Ghost Border." This is a 1px line using `outline-variant` (#3D4947) at **20% opacity**. It should be felt, not seen.
- **Glassmorphism:** For floating overlays (like right-click context menus), use `surface-container` with a 12px Backdrop Blur. This allows the high-density data underneath to be subtly visible, maintaining the user's spatial awareness.

---

## 5. Components

### Buttons
- **Style:** 4px corner radius (`DEFAULT`). Minimum height of 32px for high-density layouts.
- **Primary:** `primary-container` (#26A69A) background with `on-primary-container` text. 
- **States:** Hover should trigger a 10% opacity increase or a shift to `primary-fixed`. **Never scale or grow.**

### Tables (The Ledger)
The table is the heart of the platform.
- **Styling:** Strictly no vertical or horizontal borders.
- **Separation:** Use `surface-container-low` for even rows and `surface-container-high` for odd rows to create a "Zebra" striping effect that guides the eye across long data sets.
- **Density:** Cell padding should be 8px vertical, 12px horizontal to maximize data visibility.

### Input Fields
- **Container:** `surface-container-highest` (#353535) with a 1px "Ghost Border" on the bottom edge only.
- **Focus:** Transition the bottom border to `primary` (#66D9CC). No outer glows.

### Data Visualization (Charts)
- **Lines:** 1.5px stroke width.
- **Fills:** Prohibited. No area gradients under lines.
- **Legends:** Must be placed outside the chart area to maximize the "data-to-ink" ratio.
- **Gridlines:** Use `outline-variant` at 10% opacity.

---

## 6. Do’s and Don’ts

### Do
- **Do** use Monospace for all numbers. Alignment is critical for rapid scanning.
- **Do** use `surface-container-lowest` to "well" or "inset" utility areas like terminal logs.
- **Do** leverage whitespace as a separator. If two sections feel cluttered, increase padding rather than adding a line.
- **Do** keep corner radiuses strictly at 4px. It strikes the balance between modern and industrial.

### Don't
- **Don't** use pure black (#000000). It kills the tonal depth of the charcoal base.
- **Don't** use emojis or illustrative icons. Use only functional, geometric SVG icons.
- **Don't** use gradients or glows. They imply a "consumer" feel that undermines the professional nature of the platform.
- **Don't** use tooltips for essential data. If the user needs to see it to trade, it should be on the surface.