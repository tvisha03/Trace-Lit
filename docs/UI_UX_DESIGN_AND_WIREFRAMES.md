# TraceLit — UI/UX Design & Wireframes

> Design system, component library, wireframes, and interaction patterns.
> Dark academic aesthetic — gold-accent citation attribution, sentence-level verification, trust through traceability.
> **Reference files:** `TraceLit_UI_Design.md` (full spec), `tracelit-v4.html` (interactive prototype)

---

## 1. Design Philosophy

TraceLit is built around a single north star: **trust through traceability**. Every pixel serves one promise — *you can verify where every claim came from, instantly, without breaking your reading flow.*

### Core Principles

1. **Zero-interrupt attribution** — Verify any AI sentence via hover peek pane without navigating away from the chat.
2. **Academic visual language** — Serif headings, mono metadata accents, restrained gold for citations. Dark theme for long literature review sessions.
3. **Progressive disclosure** — Glance → claim. Hover → source paragraph. Click → full PDF at exact paragraph.
4. **Honest confidence** — Colour-coded confidence scores, always prominent. Low confidence is never hidden.
5. **Local-first privacy** — No cloud sync indicators, on-device model status shown permanently in the topbar.

---

## 2. Design System

### 2.1 Colour Palette

```css
:root {
  /* Backgrounds (darkest → lightest) */
  --bg:       #080808;   /* Base page background */
  --s1:       #0f0f0f;   /* Primary panel background */
  --s2:       #141414;   /* Message bubbles, input fields */
  --s3:       #1a1a1a;   /* User message bubbles, active states */
  --s4:       #212121;   /* Tooltips, elevated surfaces */
  --s5:       #2a2a2a;   /* Scrollbar thumbs, deep accents */

  /* Borders */
  --b1:       #222222;   /* Default dividers, card borders */
  --b2:       #2e2e2e;   /* Hover border states */
  --b3:       #3a3a3a;   /* Focus rings, strong separators */

  /* Text */
  --t1:       #ececec;   /* Primary text */
  --t2:       #aaaaaa;   /* Secondary text, body copy */
  --t3:       #666666;   /* Tertiary text, timestamps, metadata */
  --t4:       #444444;   /* Disabled text, placeholder labels */

  /* Accent — Gold (citations, active states) */
  --gold:     #c9a96e;
  --gold-dim: rgba(201,169,110, 0.12);   /* Gold tint background */
  --gold-glow:rgba(201,169,110, 0.06);   /* Subtle gold wash */

  /* Semantic — Confidence Colours (CRITICAL for attribution) */
  --hi:       #34d399;   /* High confidence (≥85%), success, active status */
  --hi-dim:   rgba(52,211,153, 0.12);
  --med:      #fbbf24;   /* Medium confidence (65–84%), warnings */
  --low:      #f87171;   /* Low confidence (<65%), errors */
  --info:     #60a5fa;   /* Active tool highlight, info states */
}
```

### 2.2 Typography

Three font families from the DM type family:

```css
--serif: 'DM Serif Display', Georgia, serif;     /* Headings, logo, PDF paper titles */
--mono:  'DM Mono', monospace;                    /* Metadata, citations, badges, timestamps */
--sans:  'DM Sans', system-ui, sans-serif;        /* All body text, UI labels, messages */
```

**Type Scale:**

| Role | Size | Weight | Font | Colour |
|------|------|--------|------|--------|
| App logo | 17px | 400 | DM Serif | --t1 |
| Section heading | 20px | 700 | DM Sans | --t1 |
| PDF section title | 19px | 700 | DM Sans | --t1 |
| PDF subsection | 15px | 600 | DM Sans | --t2 |
| Paper title (card) | 12.5px | 500 | DM Sans | --t1 |
| Message body | 14px | 400 | DM Sans | --t1/--t2 |
| Message author | 12.5px | 600 | DM Sans | --t1 |
| UI labels | 13px | 400/500 | DM Sans | --t2 |
| Tool names | 12.5px | 400 | DM Sans | --t2 |
| Mono badges | 9–11px | 400/500 | DM Mono | --t3/--gold |
| Timestamps | 10px | 400 | DM Mono | --t3 |
| Citation superscript | 0.72em | 600 | DM Mono | --gold |
| Confidence text | 11.5px | 500 | DM Sans | --hi/--med/--low |

### 2.3 Spacing Scale

```
4px    xs   — icon gaps, tight padding
6px    sm   — button internal, pill padding
8px    md   — card gaps, component spacing
12px   lg   — section padding internal
16px   xl   — panel padding standard
24px   2xl  — chat message padding, section gaps
28px   3xl  — message bottom margin
```

### 2.4 Border Radius

```css
3px    /* micro — badges, tags, inline elements */
6px    /* default (--r) — buttons, cards, inputs, panels */
8px    /* chat — message bubbles */
10px   /* pane — peek pane floating card */
50%    /* circle — avatars, status dots, pills */
```

---

## 3. Layout Architecture

### 3.1 Application Shell

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              TOPBAR  (50px)                                │
├─────────┬──────────────────────────────────┬──────────┬────────────────────┤
│         │                                  │          │                    │
│  LEFT   │                                  │  RIGHT   │    PDF VIEWER      │
│ SIDEBAR │         CHAT PANEL               │ SIDEBAR  │   (conditional,    │
│ (224px) │         (flex: 1)                │ (274px)  │    580px)          │
│         │                                  │          │                    │
└─────────┴──────────────────────────────────┴──────────┴────────────────────┘
```

**Panel Widths:**
- Left sidebar: `224px` fixed
- Chat panel: `flex: 1` (fills remaining space, min `400px`)
- Right sidebar: `274px` fixed
- PDF viewer: `580px` fixed, hidden by default (width → 0 when closed, animated via cubic-bezier)

**Heights:**
- Topbar: `50px`
- Workspace: `calc(100vh - 50px)`, all panels `height: 100%`

### 3.2 Full Workspace Wireframe

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  TraceLit  [HAVF v3]  │ Workspace  Library  Analytics  Settings             ║
║                                                    ● llama3.1:8b   [AK]     ║
╠═══════════╦════════════════════════════════════╦══════════╦══════════════════╣
║ SESSIONS  ║  ● 8 papers   ● HAVF active  ──── ║  Papers  ║ [BERT title...] ║
║ ─────────  ║                     Expand Regen Copy ║  Task    ║ Devlin·2018 p4 ║
║ ▌ Transformer   ║ ─────────────────────────────────── ║  Gaps    ║ ─────────────  ║
║   Arch.    ║                                    ║  Export  ║                  ║
║   Today·8p ║  [You]  10:23                      ║ ─────────  ║  3. Pre-training ║
║            ║  What is masked language           ║ [1] BERT 📖  ║                  ║
║  BERT vs   ║  modeling...?                      ║ Devlin·2018  ║  3.1 Masked LM   ║
║  GPT       ║                                    ║ ✓ Indexed  ║                  ║
║            ║  [TraceLit]  10:23                 ║            ║  We mask 15%...  ║
║  LoRA FT   ║  Masked language modeling          ║ [2] Attn 📖  ║                  ║
║            ║  is a pre-training technique       ║ Vaswani'17   ║  In contrast to  ║
║ ─────────  ║  where random tokens are masked¹.  ║ ✓ Indexed  ║  denoising...    ║
║ TOOLS      ║  Unlike traditional LMs that only  ║            ║                  ║
║ ANALYSIS   ║  see previous tokens, MLM enables  ║ [3] GPT-3 📖 ║  3.2 Inspiration ║
║ ▸ Chat Q&A ║  simultaneous bi-directional²       ║ Brown'20     ║                  ║
║   Deep Ext ║  context.                          ║ ✓ Indexed  ║  The MLM was     ║
║   Compare  ║                                    ║            ║  inspired by...  ║
║   Gap Anal ║  15% of tokens are randomly        ║ [4] LoRA 📖  ║                  ║
║            ║  selected for masking¹. Inspired   ║ Hu'21        ║                  ║
║ VERIFY     ║  by the Cloze task³.               ║ ✓ Indexed  ║  ← · → − 100% + ║
║   Fact Chk ║                                    ║            ║                  ║
║   Conf Aud ║  ✓ 89% avg confidence              ║            ║ Page 4 / 16      ║
║            ║  Sources: ¹·²·³ BERT               ║            ║                  ║
║ EXPORT     ║ ─────────────────────────────────── ║            ║                  ║
║   Report   ║  ┌────────────────────────────┐    ║            ║                  ║
║   BibTeX   ║  │ Ask a question across...   │ →  ║            ║                  ║
║            ║  └────────────────────────────┘    ║            ║                  ║
║            ║  [⚡ HAVF On] [🎯 All Papers▾] [📎] ║            ║                  ║
╚═══════════╩════════════════════════════════════╩══════════╩══════════════════╝
```

### 3.3 Topbar

```
┌──────────────────────────────────────────────────────────────────────┐
│  TraceLit  [HAVF v3]  │ Workspace  Library  Analytics  Settings      │
│        ↑        ↑              ↑ nav-tabs (13px, --t3/--t1)          │
│   DM Serif  mono badge                                               │
│   17px      9.5px gold                        ● llama3.1:8b   [AK]  │
│                                                ↑ status dot + mono   │
│                                                  breathing animation │
└──────────────────────────────────────────────────────────────────────┘
Height: 50px  |  Background: --s1  |  Border-bottom: 1px solid --b1
```

---

## 4. Panel: Left Sidebar (224px)

### 4.1 Structure

- **Sessions pane** (265px fixed height, scrollable) — lists research sessions
- **Tools pane** (flex: 1, scrollable) — grouped tool items (Analysis, Verify, Export)

### 4.2 Session Item States

| State | Background | Indicator |
|-------|-----------|-----------|
| Resting | --s1 (transparent) | None |
| Hover | --s2 | None |
| Active | --gold-glow | 2px gold left bar, gold-glow background |

Session metadata: `session-name` (13px, 500 weight) + `session-meta` (10px mono, --t3) showing date, paper count, citation count.

### 4.3 Tool Item States

| State | Background | Text Colour |
|-------|-----------|-------------|
| Resting | Transparent | --t2 |
| Hover | --s2 | --t2 |
| Active | rgba(96,165,250,0.08) | --info (blue) |

Tool groups: **ANALYSIS** (Chat Q&A ⌘1, Deep Extract ⌘2, Compare ⌘3, Gap Analysis ⌘4), **VERIFY** (Fact Check, Confidence Audit), **EXPORT** (Export Report ⌘E, BibTeX Export).

---

## 5. Panel: Chat Interface (flex: 1)

### 5.1 Chat Bar (46px)

```
┌──────────────────────────────────────────────────────────────┐
│  ● 8 papers   ● HAVF active              Expand  Regen  Copy │
│  ↑ context pills (--s2 bg, --b1 border)     ↑ bar buttons    │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 Message Bubbles

**User message:** bg `--s3`, colour `--t2`, padding `16px 20px`, border-radius `8px`.
**Assistant message:** bg `--s2`, colour `--t1`, padding `16px 20px`, border-radius `8px`, line-height `1.75`.

Messages area padding: `28px 44px`.

### 5.3 Cited Sentence (Core Interactive Unit)

The fundamental interactive unit. Wraps any AI response sentence that has a traceable source.

| State | Background | Behaviour |
|-------|-----------|-----------|
| Resting | None (invisible wrapper) | Cursor: default |
| Hover | rgba(201,169,110, 0.07) (subtle gold wash) | Triggers Peek Pane (§7) |
| Active (peek open) | rgba(201,169,110, 0.12) | Class `.peek-active` |

Each cited sentence carries full source metadata as `data-*` attributes:
```html
<span class="cited-sentence"
  data-paper="Full paper title"
  data-authors="Author et al. YEAR"
  data-section="N. Section Title"
  data-subsection="N.M Subsection Title"
  data-page="4"
  data-para="Verbatim paragraph text from source..."
  data-context-before="Paragraph before the cited one..."
  data-context-after="Paragraph after the cited one..."
  data-conf="94"
  data-para-id="p1">
  Chat sentence text<span class="citation" data-source-id="p1">¹</span>.
</span>
```

### 5.4 Citation Superscript (¹²³)

- Colour: `--gold`, size: `0.72em`, font: DM Mono bold, vertical-align: super
- Hover: background `--gold-dim`
- Click: jumps to source paragraph in PDF side panel (opens panel if hidden)

### 5.5 Confidence Bar

Appears at bottom of each assistant message:

```
──────────────────────────────────────────
✓  89% avg confidence  ·  Sources: ¹·²·³ BERT Paper
```

Confidence dot colours: `≥85%` → `--hi` (green), `65–84%` → `--med` (amber), `<65%` → `--low` (red).

### 5.6 Input Area

- Textarea: bg `--s2`, border `--b1`, focus border `rgba(gold, 0.4)`, 14px DM Sans
- Send button: bg `--gold`, colour `--bg`, 600 weight
- Control buttons: `[⚡ HAVF On]` (active = gold-dim bg, gold text), `[🎯 All Papers ▾]`, `[📎 Attach]`

---

## 6. Panel: Right Papers Sidebar (274px)

### 6.1 Tab Bar

Tabs: **Papers** | **Task** | **Gaps** | **Export** — active tab has gold underline + gold text.

### 6.2 Paper Card

```
┌──────────────────────────────────────────┐
│  [N]  Paper Title That Can Wrap        📖 │
│  Author et al. YEAR · ✓ Indexed          │
└──────────────────────────────────────────┘
```

| State | Background | Border | Badge [N] |
|-------|-----------|--------|-----------|
| Resting | Transparent | --b1 | bg --s3, text --t3 |
| Hover | --s2 | --b2 | — |
| Active | --gold-glow | rgba(gold, 0.3) | bg --gold, text --bg |

Paper status indicators: `✓ Indexed` (ready), `⟳ Indexing` (animated spinner), `⚠ Error` (--low colour).

📖 button: opacity 0.55 → 1.0 on hover, scale 1.1 transition.

---

## 7. Feature: Sentence-Level Hover Peek Pane (Signature Feature)

The peek pane allows a researcher to verify the source of any AI-generated sentence without navigating away from the chat. This is the defining interaction of TraceLit v4.

### 7.1 Wireframe

```
╔══════════════════════════════════════════════════════╗
║  ● PAPER [1] · PAGE 4                                ║  ← peek-header (bg --s3)
║  BERT: Pre-training of Deep Bidirectional            ║  ← 13px 600 title
║  Transformers for Language Understanding             ║
║  Devlin et al. 2018                                  ║  ← 11px --t3
║  3. Pre-training BERT  ›  3.1 Masked LM              ║  ← section path
╠══════════════════════════════════════════════════════╣
║  BERT's pre-training uses two unsupervised tasks.    ║  ← context-before (0.5 opacity)
║                                                      ║
║  ─ CITED PASSAGE · §3.1 Masked LM · p.4 ─           ║  ← label (gold mono)
║ ┌────────────────────────────────────────────────┐  ║
║ ▌  We mask 15% of all input tokens at random     │  ║  ← cited paragraph
║ ▌  and train the model to predict the original   │  ║    bg: gold gradient
║ ▌  vocabulary id of the masked word based only   │  ║    left bar: 2px gold
║ ▌  on its context.                               │  ║    key phrase highlighted
║ └────────────────────────────────────────────────┘  ║
║  Although this allows us to obtain a bidirectional   ║  ← context-after (0.5 opacity)
║  pre-trained model, a downside is...                 ║
╠══════════════════════════════════════════════════════╣
║  ● 94% confidence  · HAVF verified     [Open in PDF ↗] ║  ← peek-footer (bg --s3)
╚══════════════════════════════════════════════════════╝
```

**Dimensions:** 430px wide, max 520px height (body scrolls on overflow), border-radius 10px.
**Shadow:** `0 20px 50px rgba(0,0,0,0.7), 0 4px 16px rgba(0,0,0,0.5), 0 0 0 1px rgba(gold,0.08)`.

### 7.2 Positioning Logic

```
PREFERRED:  left = mouse.x + 16px, top = sentence.bottom + 8px
OVERFLOW:   right overflow → flip to left of cursor
            bottom overflow → flip above sentence
            Always clamped 8px from any viewport edge

STAYS OPEN:  Mouse within cited-sentence OR mouse enters peek pane (clears 220ms timer)
CLOSES:      Mouse leaves both sentence + pane → 220ms debounce → hide
```

### 7.3 Confidence Colour Mapping

| Score | Dot Colour | Label |
|-------|-----------|-------|
| ≥ 85% | `#34d399` (green) | "X% confidence" |
| 65–84% | `#fbbf24` (amber) | "X% confidence" |
| < 65% | `#f87171` (red) | "X% confidence (low)" |

---

## 8. Feature: Citation Superscript Tooltip

A lightweight, small tooltip appears when hovering the `¹²³` superscript directly (distinct from the full peek pane triggered by hovering the sentence).

```
┌──────────────────────────────────┐
│  ¹ BERT Paper · §3.1 · p.4      │  ← gold, 600 weight
│  "We mask 15% of all toks…"     │  ← italic --t3
│  Confidence: 94% (high)         │  ← --hi
│  ─────────────────────────────  │
│  Click to jump in PDF →         │  ← 9.5px --t3
└──────────────────────────────────┘
```

Width: max 280px, bg `--s4`, border `--b2`, pointer-events: none, z-index: 1000.

### Tooltip vs Peek Pane

| Hover Target | Result |
|-------------|--------|
| Cited sentence (text) | Peek Pane (large, interactive) |
| Citation superscript (¹) | Small tooltip (non-interactive) |
| Citation click | Jump to PDF + open side panel |

---

## 9. Panel: PDF Side Viewer (580px, conditional)

### 9.1 Structure

```
╔════════════════════════════════════════════════════════╗
║  BERT: Pre-training of Deep...                   📖 × ║  ← pdf-header (54px)
║  Devlin et al. 2018 · 16 pages                         ║
╠════════════════════════════════════════════════════════╣
║  Page 4 / 16                    [←] [→] [−] 100% [+]  ║  ← pdf-nav (38px)
╠════════════════════════════════════════════════════════╣
║  3. Pre-training BERT                                  ║  ← section-title 19px
║  3.1 Masked LM                                         ║  ← subsection 15px
║  paragraph text...                                     ║  ← --t2 body
║ ╔══════════════════════════════════════════════════╗  ║
║ ║ ↓ Citation source                                ║  ║  ← HIGHLIGHTED
║ ║ We mask 15% of all input tokens...              ║  ║    gold gradient bg
║ ╚══════════════════════════════════════════════════╝  ║    animation: para-pulse 2s
╚════════════════════════════════════════════════════════╝
```

Hidden by default (width: 0, overflow: hidden). Opens on: 📖 click, citation click, peek pane "Open in PDF" button. Transition: `0.3s cubic-bezier(0.16, 1, 0.3, 1)`.

### 9.2 Highlighted Paragraph

- Animated gold gradient background + gold border ring
- "↓ Citation source" label (9.5px mono, gold) — slides up + fades out over 2s
- Paragraph pulse animation: bright gold → dim gold over 2s, auto-removes after 2200ms

---

## 10. Component Library

### 10.1 Core Components

| Component | File | Description |
|-----------|------|-------------|
| `CitedSentence` | `chat/CitedSentence.jsx` | Wraps sentences with data-* attributes, triggers peek pane on hover, gold wash on hover |
| `CitationTooltip` | `chat/CitationTooltip.jsx` | Small tooltip on superscript hover: paper, section, preview, confidence |
| `PeekPane` | `chat/PeekPane.jsx` | Full source preview pane on sentence hover: header, cited paragraph, context, confidence footer |
| `ConfidenceBadge` | `common/ConfidenceBadge.jsx` | Inline pill with percentage, colour-coded (green/amber/red) |
| `ChatControls` | `chat/ChatControls.jsx` | HAVF toggle, paper filter, attach button |
| `PDFViewer` | `source/PDFViewer.jsx` | Side panel with paragraph rendering, highlight animation on citation jump |
| `ComparisonTable` | `compare/ComparisonTable.jsx` | Editable table with click-to-source cells |
| `PaperCard` | `papers/PaperCard.jsx` | Right sidebar card with badge, status indicator, PDF open button |
| `PaperUpload` | `papers/PaperUpload.jsx` | Drag-and-drop zone + file picker |
| `ProcessingProgress` | `papers/ProcessingProgress.jsx` | Per-paper progress bar with stage labels |
| `SessionItem` | `layout/SessionItem.jsx` | Left sidebar session entry with gold active bar |
| `MessageSkeleton` | `common/LoadingSkeleton.jsx` | Shimmer loading state for streaming responses |
| `ErrorBoundary` | `common/ErrorBoundary.jsx` | Graceful error fallback for component crashes |

### 10.2 CitedSentence Component

The most important UI component — renders each LLM response sentence with inline attribution:

```jsx
export const CitedSentence = ({ sentence, onHover, onCitationClick }) => {
  return (
    <span
      className="cited-sentence"
      data-paper={sentence.paper}
      data-authors={sentence.authors}
      data-section={sentence.section}
      data-subsection={sentence.subsection}
      data-page={sentence.page}
      data-para={sentence.sourceParagraph}
      data-context-before={sentence.contextBefore}
      data-context-after={sentence.contextAfter}
      data-conf={sentence.confidence}
      data-para-id={sentence.paraId}
      onMouseEnter={(e) => onHover(sentence, e)}
    >
      {sentence.text}
      {sentence.citations.map((cite, i) => (
        <span
          key={i}
          className="citation"
          data-source-id={cite.paraId}
          onClick={(e) => { e.stopPropagation(); onCitationClick(cite); }}
        >
          {cite.displayNumber}
        </span>
      ))}
    </span>
  );
};
```

### 10.3 Key CSS

```css
/* Cited sentence — invisible wrapper, gold wash on hover */
.cited-sentence {
  border-radius: 3px; padding: 1px 2px; margin: 0 -2px;
  transition: background 0.18s; cursor: default;
}
.cited-sentence:hover { background: rgba(201,169,110, 0.07); }
.cited-sentence.peek-active { background: rgba(201,169,110, 0.12); }

/* Citation superscript — gold mono marker */
.citation {
  color: var(--gold); font-size: 0.72em; vertical-align: super;
  cursor: pointer; font-weight: 600; font-family: var(--mono);
  transition: background 0.15s;
}
.citation:hover { background: var(--gold-dim); }

/* PDF paragraph highlight animation */
.pdf-paragraph.highlighted {
  background: linear-gradient(90deg,
    rgba(201,169,110,0) 0%, rgba(201,169,110,0.16) 4%,
    rgba(201,169,110,0.16) 96%, rgba(201,169,110,0) 100%);
  box-shadow: 0 0 0 1px rgba(201,169,110,0.25);
  color: var(--t1);
  animation: para-pulse 2s ease-in-out;
}
@keyframes para-pulse {
  0%   { background-color: rgba(201,169,110,0.3); }
  100% { background-color: rgba(201,169,110,0.12); }
}

/* Peek pane — floating source preview */
.peek-pane {
  position: fixed; width: 430px; max-height: 520px;
  background: var(--s2); border: 1px solid var(--b2);
  border-radius: 10px;
  box-shadow: 0 0 0 1px rgba(201,169,110,0.08),
              0 20px 50px rgba(0,0,0,0.7),
              0 4px 16px rgba(0,0,0,0.5);
  opacity: 0; transform: translateY(8px) scale(0.98);
  pointer-events: none;
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.peek-pane.visible {
  opacity: 1; transform: translateY(0) scale(1);
  pointer-events: auto;
}
```

---

## 11. Interaction Patterns

### 11.1 Primary Attribution Flow (Sentence Hover → Peek Pane)

```
User hovers cited sentence
  → showPeek() reads data-* attributes
  → Populates peek pane header, body (context + cited paragraph), footer
  → Calculates viewport-aware position
  → Adds .visible class (CSS transition: opacity + transform, 200ms)
  → User reads source context
  → "Open in PDF ↗" click → jumpToSource(paraId)
     → Opens PDF panel if hidden
     → Smooth-scrolls to paragraph
     → .highlighted class + 2s pulse animation
```

### 11.2 Citation Click Flow (Superscript → PDF Jump)

```
User clicks ¹ superscript
  → Stops propagation (no sentence hover trigger)
  → Reads data-source-id
  → jumpToSource(paraId)
     → PDF panel: remove .hidden → width 0→580px (0.3s cubic-bezier)
     → scrollIntoView({ behavior: 'smooth', block: 'center' })
     → .highlighted animation, removed after 2200ms
```

### 11.3 Paper Processing Flow

```
UPLOADING → EXTRACTING → EMBEDDING → INDEXED → READY
   ⟳            ⟳            ⟳          ✓        ✓ (queryable)
```

1. User drops PDFs → upload zone shows file list with "(processing...)" badges
2. Progress bar per paper: Extracting → Chunking → Embedding → Indexing
3. Toast: "📄 BERT paper ready!"
4. Paper appears in right sidebar with ✓ Indexed status

### 11.4 Error States

| State | UI |
|-------|-----|
| No papers uploaded | Empty state + "Upload papers to get started" |
| Processing in progress | Skeleton loader + progress bars |
| Query with no ready papers | Disabled input + "Wait for papers to finish processing" |
| LLM rate limited | Yellow banner: "Switching providers..." (auto-recovers) |
| All providers failed | Red banner: "Service unavailable" + Retry button |
| PDF extraction failed | Red badge on paper card + "Extraction failed" tooltip |

---

## 12. State Diagrams

### 12.1 Peek Pane States

```
HIDDEN (default)  →  mouseenter .cited-sentence  →  ENTERING (200ms)  →  VISIBLE
     ↑                                                                      │
     └──── timer fires ←── HIDING (220ms debounce) ←── mouseleave both ────┘
                                           ↑                                │
                                           └── mouseenter peek pane ────────┘
                                                  (clears timer → stays open)
```

### 12.2 PDF Panel States

```
HIDDEN (width:0) → 📖 or citation click → OPENING (0.3s) → OPEN (580px)
     ↑                                                          │
     └────────── CLOSING (0.3s) ←── × click or toggle ──────────┘
```

---

## 13. Responsive Behaviour

TraceLit is **desktop-first**. Panels collapse progressively.

| Breakpoint | Width | Behaviour |
|-----------|-------|-----------|
| Full | ≥ 1400px | All 4 panels visible simultaneously |
| Standard | 1100–1399px | PDF panel hidden by default (toggle only) |
| Compact | 900–1099px | Left sidebar collapses to icon-only (48px) |
| Tablet | 768–899px | Right sidebar hides behind slide-over drawer |
| Mobile | < 768px | Single-panel view, swipe between panels (not recommended) |

### Compact Sidebar (48px)

```
┌──────┐
│  +   │  ← session create
│ ─────│
│  💬  │  ← tools as icon-only
│  🔬  │
│  ⚖️  │
│  🕳️  │
│ ─────│
│  ✅  │
│  📊  │
└──────┘
```

---

## 14. Accessibility

### Keyboard Navigation

| Key | Action |
|-----|--------|
| TAB | Navigate interactive elements |
| ENTER / SPACE | Activate buttons, open peek pane for cited sentence |
| ESCAPE | Close peek pane, close PDF panel |
| ← → | Navigate PDF pages (when focused) |
| ⌘1–4 | Tool shortcuts (Chat, Deep, Compare, Gap) |
| ⌘E | Export report |

### ARIA Roles

| Element | Role / Label |
|---------|-------------|
| `.cited-sentence` | `role="button"`, `aria-label="View source: {paper} §{section}"` |
| `.citation` | `role="button"`, `aria-label="Citation {n}: {paper} page {p}"` |
| `.peek-pane` | `role="dialog"`, `aria-label="Source preview"` |
| `#pdfPanel` | `role="complementary"`, `aria-label="PDF viewer"` |
| `.confidence-bar` | `aria-label="Confidence score: {n}%"` |

### Colour Contrast

| Pair | Values | WCAG |
|------|--------|------|
| --t1 on --s2 | #ececec / #141414 | AAA ✓ |
| --t2 on --s2 | #aaaaaa / #141414 | AA ✓ |
| --gold on --s2 | #c9a96e / #141414 | AA ✓ |
| --hi on --s2 | #34d399 / #141414 | AA ✓ |

- Confidence always paired with text label (not colour alone)
- `prefers-reduced-motion` disables pulse and breathing animations
- Minimum touch target: 44x44px

---

## 15. Animation & Motion Spec

### Transitions

| Element | Property | Duration | Easing |
|---------|----------|----------|--------|
| Peek pane show/hide | opacity, transform | 200ms | ease |
| PDF panel open/close | width | 300ms | cubic-bezier(0.16,1,0.3,1) |
| Cited sentence hover | background | 180ms | ease |
| Citation hover | background | 150ms | ease |
| Paper card hover | background, border | 150ms | ease |
| Tool/session/nav hover | background | 150ms | ease |

### Keyframe Animations

| Name | Duration | Trigger | Effect |
|------|----------|---------|--------|
| `breathe` | 3s infinite | Status dot (always on) | opacity 1 → 0.45 → 1 |
| `para-pulse` | 2s once | PDF paragraph `.highlighted` | gold bg fades out |
| `label-fade` | 2s once | "↓ Citation source" label | slide up + fade out |

### Micro-interactions

- PDF button (📖): hover → scale(1.1), opacity 1.0
- Citation (¹): hover → bg gold-dim
- Avatar: hover → border-color --gold
- Pane-action (+): hover → color --gold
