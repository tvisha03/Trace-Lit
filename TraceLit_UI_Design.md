# TraceLit — UI/UX Design Specification
### Intelligent Academic Literature Assistant with Sentence-Level Verified Attribution
**Version:** 4.0 | **Date:** February 2026 | **Platform:** Web (Desktop-first)

---

## Table of Contents

1. [Design Philosophy](#1-design-philosophy)
2. [Design Tokens & Visual Language](#2-design-tokens--visual-language)
3. [Typography System](#3-typography-system)
4. [Component Library](#4-component-library)
5. [Application Shell](#5-application-shell)
6. [Wireframe — Full Workspace Layout](#6-wireframe--full-workspace-layout)
7. [Panel: Left Sidebar](#7-panel-left-sidebar)
8. [Panel: Chat Interface](#8-panel-chat-interface)
9. [Panel: Right Papers Sidebar](#9-panel-right-papers-sidebar)
10. [Panel: PDF Side Viewer](#10-panel-pdf-side-viewer)
11. [Feature: Sentence-Level Hover Peek Pane](#11-feature-sentence-level-hover-peek-pane)
12. [Feature: Citation Superscript Tooltip](#12-feature-citation-superscript-tooltip)
13. [Interaction Flow Diagrams](#13-interaction-flow-diagrams)
14. [State Diagrams](#14-state-diagrams)
15. [Responsive Behaviour](#15-responsive-behaviour)
16. [Accessibility Notes](#16-accessibility-notes)
17. [Animation & Motion Spec](#17-animation--motion-spec)

---

## 1. Design Philosophy

TraceLit is built around a single north star: **trust through traceability**. Every pixel of the UI is in service of one promise — *you can verify where every claim came from, instantly, without breaking your reading flow.*

### Core Principles

**1. Zero-interrupt attribution**
A researcher should be able to scan an AI response and verify any sentence without opening a new tab, scrolling, or leaving the conversation. The hover peek pane delivers full source context *in place*, without navigation.

**2. Academic visual language**
The aesthetic borrows from high-quality academic typesetting — serif headings, mono accents for metadata, restrained gold for citation markers. The dark theme reduces eye strain during long literature review sessions.

**3. Progressive disclosure**
Information is layered. A glance shows the claim. A hover shows the source paragraph. A click opens the full PDF at the exact paragraph. Nothing is buried, nothing is overwhelming by default.

**4. Honest confidence**
Confidence scores are colour-coded and prominent. Low confidence is never hidden. The system never pretends to be more certain than it is.

**5. Local-first privacy**
The UI reflects this with no cloud sync indicators, no "uploading" language, and on-device model status shown permanently in the topbar.

---

## 2. Design Tokens & Visual Language

### 2.1 Colour Palette

```
BACKGROUNDS (darkest → lightest)
────────────────────────────────────────────────────
--bg       #080808   Base page background
--s1       #0f0f0f   Primary panel background
--s2       #141414   Message bubbles, input fields
--s3       #1a1a1a   User message bubbles, active states
--s4       #212121   Tooltips, elevated surfaces
--s5       #2a2a2a   Scrollbar thumbs, deep accents

BORDERS
────────────────────────────────────────────────────
--b1       #222222   Default dividers, card borders
--b2       #2e2e2e   Hover border states
--b3       #3a3a3a   Focus rings, strong separators

TEXT
────────────────────────────────────────────────────
--t1       #ececec   Primary text
--t2       #aaaaaa   Secondary text, body copy
--t3       #666666   Tertiary text, timestamps, metadata
--t4       #444444   Disabled text, placeholder labels

ACCENT — Gold
────────────────────────────────────────────────────
--gold          #c9a96e   Citation markers, active states
--gold-dim      rgba(201,169,110, 0.12)   Gold tint background
--gold-glow     rgba(201,169,110, 0.06)   Subtle gold wash

SEMANTIC
────────────────────────────────────────────────────
--hi       #34d399   High confidence, success, active dot
--hi-dim   rgba(52,211,153, 0.12)   High confidence tint
--med      #fbbf24   Medium confidence, warnings
--low      #f87171   Low confidence, errors
--info     #60a5fa   Active tool highlight, info states
```

### 2.2 Spacing Scale

```
4px    xs   — icon gaps, tight padding
6px    sm   — button internal, pill padding
8px    md   — card gaps, component spacing
12px   lg   — section padding internal
16px   xl   — panel padding standard
24px   2xl  — chat message padding, section gaps
28px   3xl  — message bottom margin
```

### 2.3 Border Radius

```
3px    micro   — badges, tags, inline elements
6px    default — buttons, cards, inputs, panels
8px    chat    — message bubbles
10px   pane    — peek pane floating card
50%    circle  — avatars, status dots, pills
```

---

## 3. Typography System

```
FONTS USED
────────────────────────────────────────────────────
DM Serif Display   Headings, logo, paper titles in PDF
DM Mono            Metadata, citations, badges, keys, timestamps
DM Sans            All body text, UI labels, messages
```

### Type Scale

```
ROLE                SIZE   WEIGHT   FONT         COLOUR
──────────────────────────────────────────────────────────────
App logo            17px   400      DM Serif     --t1
Section heading     20px   700      DM Sans      --t1
PDF section title   19px   700      DM Sans      --t1
PDF subsection      15px   600      DM Sans      --t2
Paper title (card)  12.5px 500      DM Sans      --t1
Message body        14px   400      DM Sans      --t1 / --t2
Message author      12.5px 600      DM Sans      --t1
UI labels           13px   400/500  DM Sans      --t2
Tool names          12.5px 400      DM Sans      --t2
Mono badges         9–11px 400/500  DM Mono      --t3 / --gold
Timestamps          10px   400      DM Mono      --t3
Citation sup        0.72em 600      DM Mono      --gold
Confidence text     11.5px 500      DM Sans      --hi/--med/--low
```

---

## 4. Component Library

### 4.1 Cited Sentence

The fundamental interactive unit of the chat interface. Wraps any AI response sentence that has a traceable source.

```
RESTING STATE:
┌────────────────────────────────────────────────────────────┐
│  Masked language modeling is a pre-training technique       │
│  where random tokens are masked in the input sequence¹      │
└────────────────────────────────────────────────────────────┘
  • No background, invisible wrapper
  • Cursor: default (not pointer — sentence is readable)
  • ¹ citation in --gold, superscript, DM Mono

HOVER STATE (triggers Peek Pane):
┌────────────────────────────────────────────────────────────┐
│ ░░Masked language modeling is a pre-training technique░░░  │
│ ░░where random tokens are masked in the input sequence¹░░  │
└────────────────────────────────────────────────────────────┘
  • background: rgba(201,169,110, 0.07)  (very subtle gold wash)
  • border-radius: 3px
  • transition: background 0.18s
  • Peek Pane appears (see §11)

ACTIVE STATE (peek pane open):
  • background: rgba(201,169,110, 0.12)
  • class: .peek-active
```

### 4.2 Citation Superscript (¹²³)

```
┌─────────────────────────────────────┐
│  ...based on its context¹           │
│                         ↑           │
│                    [gold, 0.72em,   │
│                     DM Mono bold,   │
│                     superscript]    │
└─────────────────────────────────────┘

HOVER: background --gold-dim, scale 1.05
CLICK: jumps to source paragraph in PDF side panel
       + opens PDF panel if hidden
```

### 4.3 Paper Card (Right Panel)

```
RESTING:
┌──────────────────────────────────────────┐
│  [1]  BERT: Pre-training of Deep          📖 │
│       Bidirectional Transformers              │
│  Devlin et al. 2018 · ✓ Indexed              │
└──────────────────────────────────────────┘
  border: 1px solid --b1

HOVER:
  background: --s2
  border: 1px solid --b2

ACTIVE:
┌──────────────────────────────────────────┐
│▌ [1] ▸ BERT: Pre-training of Deep        📖 │
│         Bidirectional Transformers             │
│   Devlin et al. 2018 · ✓ Indexed               │
└──────────────────────────────────────────┘
  background: rgba(201,169,110, 0.06)
  border: 1px solid rgba(201,169,110, 0.3)
  [1] badge: background --gold, color --bg
```

### 4.4 Confidence Bar

```
┌──────────────────────────────────────────────────────────┐
│  ─────────────────────────────────────────────────────   │
│  ✓  89% avg confidence  ·  Sources: ¹·²·³ BERT Paper     │
└──────────────────────────────────────────────────────────┘

Confidence dot colours:
  ≥ 85%  →  --hi     #34d399   green
  65–84% →  --med    #fbbf24   amber
  < 65%  →  --low    #f87171   red
```

### 4.5 Control Button

```
DEFAULT:          │ ⚡ HAVF On │    bg --s2, border --b1, text --t2
HOVER:            │ ⚡ HAVF On │    bg --s3
ACTIVE:           │ ⚡ HAVF On │    bg gold-dim, border gold×0.35, text --gold
```

### 4.6 Context Pill

```
  ● 8 papers       ● HAVF active
  ╰───────────╯   ╰─────────────╯
  bg --s2, border --b1, 4px pill-dot in --hi
```

---

## 5. Application Shell

### 5.1 Layout Grid

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

**Widths:**
- Left sidebar: `224px` fixed
- Chat panel: `flex: 1` (fills remaining space, min `400px`)
- Right sidebar: `274px` fixed
- PDF viewer: `580px` fixed, hidden by default (width → 0 when closed)

**Heights:**
- Topbar: `50px`
- Workspace: `calc(100vh - 50px)`, all panels `height: 100%`

---

## 6. Wireframe — Full Workspace Layout

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
║   Report   ║                                    ║            ║                  ║
║   BibTeX   ║  ┌────────────────────────────┐    ║            ║                  ║
║            ║  │ Ask a question across...   │ →  ║            ║                  ║
║            ║  └────────────────────────────┘    ║            ║                  ║
║            ║  [⚡ HAVF On] [🎯 All Papers▾] [📎] ║            ║                  ║
╚═══════════╩════════════════════════════════════╩══════════╩══════════════════╝
```

---

## 7. Panel: Left Sidebar

### 7.1 Structure

```
╔═══════════════════════╗
║  SESSIONS        [+]  ║  ← pane-header (11px mono label, pane-action +)
╠═══════════════════════╣
║▌ Transformer Arch.    ║  ← active session (gold left-bar, gold-glow bg)
║  Today · 8p · 47c     ║    session-name 13px / session-meta 10px mono
║───────────────────────║
║  BERT vs GPT          ║  ← resting session
║  Yesterday · 5p       ║
║───────────────────────║
║  LoRA Fine-tuning     ║
║  Feb 22 · 12p         ║
║───────────────────────║
║  Diffusion Survey     ║
║  Feb 18 · 9p          ║
╠═══════════════════════╣  ← sessions-pane bottom border (265px fixed height)
║  TOOLS                ║  ← tools-pane begins (flex: 1, scrollable)
╠═══════════════════════╣
║  ANALYSIS             ║  ← tool-group-label (9px mono, --t4)
║  ▸ 💬 Chat Q&A   ⌘1  ║  ← active: info-blue bg, blue text
║    🔬 Deep Ext   ⌘2  ║
║    ⚖️  Compare   ⌘3  ║
║    🕳️  Gap Anal  ⌘4  ║
╠═══════════════════════╣
║  VERIFY               ║
║    ✅ Fact Check       ║
║    📊 Confidence Audit ║
╠═══════════════════════╣
║  EXPORT               ║
║    📄 Export Report ⌘E║
║    📚 BibTeX Export    ║
╚═══════════════════════╝
   224px wide
```

### 7.2 Session Item States

```
RESTING          HOVER            ACTIVE
─────────────   ─────────────   ─────────────
 Session Name    Session Name   ▌Session Name
 meta text       meta text      meta text
 bg: --s1        bg: --s2        bg: gold-glow
                                 left: 2px gold bar
```

### 7.3 Tool Item States

```
RESTING          HOVER            ACTIVE
─────────────   ─────────────   ─────────────
 🔬 Tool Name    🔬 Tool Name    ▸ 💬 Tool Name
 --t2 text       --s2 bg          --info text
                                  rgba(info,0.08) bg
```

---

## 8. Panel: Chat Interface

### 8.1 Structure

```
╔═══════════════════════════════════════════════════╗
║  ● 8 papers   ● HAVF active         Expand Regen Copy ║  ← chat-bar (46px)
╠═══════════════════════════════════════════════════╣
║                                                   ║
║  [You]  10:23                                     ║
║  ┌─────────────────────────────────────────────┐  ║
║  │ What is masked language modeling and how    │  ║  ← user bubble
║  │ does it differ from traditional LMs?        │  ║    bg --s3
║  └─────────────────────────────────────────────┘  ║
║                                                   ║
║  [TraceLit]  10:23                                ║
║  ┌─────────────────────────────────────────────┐  ║
║  │                                             │  ║
║  │ ┄Masked language modeling (MLM) is a pre-  │  ║  ← cited sentence ①
║  │ ┄training technique where random tokens are │  ║    hover → Peek Pane
║  │ ┄masked in the input sequence, and the      │  ║
║  │ ┄model learns to predict them based on      │  ║
║  │ ┄bidirectional context¹.┄ ┄Unlike           │  ║  ← cited sentence ②
║  │ ┄traditional left-to-right LMs that only   │  ║
║  │ ┄see previous tokens, MLM enables the model│  ║
║  │ ┄to simultaneously utilize both left and   │  ║
║  │ ┄right context².┄                           │  ║
║  │                                             │  ║
║  │ ┄The key innovation is that 15% of tokens  │  ║  ← cited sentence ③
║  │ ┄are randomly selected for masking¹.┄       │  ║
║  │ ┄Inspired by the classic Cloze task, BERT   │  ║  ← cited sentence ④
║  │ ┄learns deeper bidirectional                │  ║
║  │ ┄representations³.┄                         │  ║
║  │                                             │  ║
║  │  ─────────────────────────────────────────  │  ║
║  │  ✓ 89% avg confidence · ¹·²·³ BERT Paper   │  ║  ← confidence bar
║  └─────────────────────────────────────────────┘  ║
║                                                   ║
╠═══════════════════════════════════════════════════╣
║  ┌────────────────────────────────────┐  [Send →] ║
║  │ Ask a question across your papers..│           ║  ← input area
║  └────────────────────────────────────┘           ║
║  [⚡ HAVF On]  [🎯 All Papers ▾]  [📎 Attach]    ║
╚═══════════════════════════════════════════════════╝

padding: 28px 44px (messages area)
padding: 14px 24px (input area)
```

### 8.2 Message Bubble Anatomy

```
USER MESSAGE
────────────
[You]   10:23
         ↑      ← message-author (13px, 600 weight)
                ← message-time (10px mono, --t3)
┌──────────────────────────────────────────┐
│ What is masked language modeling...?     │  bg: --s3
│                                          │  padding: 16px 20px
└──────────────────────────────────────────┘  border-radius: 8px
                                              color: --t2

ASSISTANT MESSAGE
──────────────────
[TraceLit]   10:23

┌──────────────────────────────────────────┐
│ [paragraph with cited sentences]         │  bg: --s2
│                                          │  color: --t1
│ ─────────────────────────────────────── │
│ ✓ 89% avg confidence · Sources: ¹·²·³   │  confidence bar
└──────────────────────────────────────────┘  line-height: 1.75
```

### 8.3 Cited Sentence Rendering

```
NORMAL TEXT (no source):
  color --t1, no background, cursor default

CITED SENTENCE (has source, resting):
  color --t1, no background, cursor default
  ┄ denotes invisible .cited-sentence wrapper ┄

CITED SENTENCE (hovered):
  background: rgba(201,169,110, 0.07)
  border-radius: 3px

CITATION SUPERSCRIPT hover:
  background: rgba(201,169,110, 0.12)
  Small tooltip appears below
```

### 8.4 Input Area

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│  ┌────────────────────────────────────┐  ┌────────┐  │
│  │ Ask a question across your        │  │ Send → │  │
│  │ papers...                          │  │  gold  │  │
│  └────────────────────────────────────┘  └────────┘  │
│  bg --s2, border --b1, 14px sans        bg --gold    │
│  focus: border rgba(gold,0.4)           color --bg    │
│                                                      │
│  [⚡ HAVF On]  [🎯 All Papers ▾]  [📎 Attach]        │
│   active=gold  resting=--s2/b1    resting=--s2/b1    │
└──────────────────────────────────────────────────────┘
```

---

## 9. Panel: Right Papers Sidebar

### 9.1 Structure

```
╔═══════════════════════════════╗
║  Papers  │ Task │ Gaps │Export║  ← tab-bar
║  ──────   active: gold underline
╠═══════════════════════════════╣
║                               ║
║ ┌─────────────────────────┐   ║  ← ACTIVE paper card
║ │ [1]  BERT: Pre-training  📖 │   ║    bg: gold-glow
║ │      of Deep Bidirectional  │   ║    border: gold×0.3
║ │ Devlin et al. 2018 · ✓ Indexed│   ║    [1] badge: gold bg
║ └─────────────────────────┘   ║
║                               ║
║ ┌─────────────────────────┐   ║  ← resting paper card
║ │ [2]  Attention Is All    📖 │   ║    border: --b1
║ │      You Need               │   ║
║ │ Vaswani et al. 2017 · ✓ Indexed│   ║
║ └─────────────────────────┘   ║
║                               ║
║ ┌─────────────────────────┐   ║
║ │ [3]  Language Models    📖  │   ║
║ │      are Few-Shot Learners  │   ║
║ │ Brown et al. 2020 · ✓ Indexed│   ║
║ └─────────────────────────┘   ║
║                               ║
║ ┌─────────────────────────┐   ║
║ │ [4]  LoRA: Low-Rank     📖  │   ║
║ │      Adaptation             │   ║
║ │ Hu et al. 2021 · ✓ Indexed  │   ║
║ └─────────────────────────┘   ║
║                               ║
╚═══════════════════════════════╝
   274px wide
```

### 9.2 Paper Card Anatomy

```
┌──────────────────────────────────────────┐
│  ┌───┐  Paper Title That Can Wrap To     │
│  │[N]│  Multiple Lines Here           📖 │
│  └───┘                                   │
│  Author et al. YEAR · ✓ Indexed          │
└──────────────────────────────────────────┘

[N]  = paper-num badge (9.5px mono)
       resting: bg --s3, color --t3
       active:  bg --gold, color --bg

📖   = pdf-btn
       opacity 0.55 resting → 1.0 hover, scale 1.1

✓ Indexed = processed and embedded, ready to query
⟳ Indexing = currently being embedded (animated spinner)
⚠ Error   = extraction failed (--low colour)
```

---

## 10. Panel: PDF Side Viewer

### 10.1 Structure

```
╔════════════════════════════════════════════════════════╗
║  BERT: Pre-training of Deep Bidirectional...     📖  × ║  ← pdf-header (54px)
║  Devlin et al. 2018 · 16 pages                         ║
╠════════════════════════════════════════════════════════╣
║  Page 4 / 16                    [←] [→] [−] 100% [+]  ║  ← pdf-nav (38px)
╠════════════════════════════════════════════════════════╣
║                                                        ║
║  3. Pre-training BERT                                  ║  ← section-title 19px 700
║                                                        ║
║  3.1 Masked LM                                         ║  ← section-subtitle 15px 600
║                                                        ║
║  BERT's pre-training uses two unsupervised tasks.      ║  ← pdf-paragraph
║  The first is Masked Language Modeling (MLM)...        ║    color --t2
║                                                        ║
║ ╔══════════════════════════════════════════════════╗  ║
║ ║ ↓ Citation source                                ║  ║  ← HIGHLIGHTED PARAGRAPH
║ ║ We mask 15% of all input tokens at random and    ║  ║    (on jump-to / click)
║ ║ train the model to predict the original          ║  ║    bg: gold gradient
║ ║ vocabulary id of the masked word based only      ║  ║    border: gold×0.25
║ ║ on its context. Unlike traditional left-to-      ║  ║    color: --t1
║ ║ right LM pre-training, the MLM objective         ║  ║    animation: para-pulse
║ ╚══════════════════════════════════════════════════╝  ║
║                                                        ║
║  In contrast to denoising auto-encoders, we only       ║
║  predict the masked words rather than reconstructing   ║
║  the entire input...                                   ║
║                                                        ║
║  3.2 MLM Inspiration                                   ║
║                                                        ║
║  The MLM approach was inspired by the Cloze task...    ║
║                                                        ║
╚════════════════════════════════════════════════════════╝
  580px wide
  hidden by default (width: 0, overflow: hidden)
  opens on: 📖 click, citation click, peek pane jump
```

### 10.2 Highlighted Paragraph States

```
RESTING:
┌─────────────────────────────────────────────┐
│  paragraph text here...                     │  bg: transparent
└─────────────────────────────────────────────┘

HIGHLIGHTED (active citation target):
┌─────────────────────────────────────────────┐
│ ↓ Citation source   ← animated label        │
│                                             │
│  paragraph text here...                     │  gradient gold bg
│                                             │  gold border ring
└─────────────────────────────────────────────┘
  animation: 2s ease-in-out, fades out after

Label animation: slides up + fades out over 2s
Paragraph animation: bright gold → dim gold over 2s
```

---

## 11. Feature: Sentence-Level Hover Peek Pane

This is the signature feature of TraceLit v4. It allows a researcher to verify the source of any AI-generated sentence without navigating away from the chat.

### 11.1 Full Wireframe

```
╔══════════════════════════════════════════════════════╗
║  ● PAPER [1] · PAGE 4                                ║  ← peek-header (bg --s3)
║                                                      ║
║  BERT: Pre-training of Deep Bidirectional            ║  ← peek-title  13px 600
║  Transformers for Language Understanding             ║
║  Devlin et al. 2018                                  ║  ← peek-authors 11px --t3
║                                                      ║
║  3. Pre-training BERT  ›  3.1 Masked LM              ║  ← section path
╠══════════════════════════════════════════════════════╣
║                                                      ║  ← peek-body (scrollable)
║  BERT's pre-training uses two unsupervised tasks.    ║  ← context-before
║  The first is Masked Language Modeling (MLM)...      ║    opacity 0.5, 12px
║                                                      ║
║  ─ CITED PASSAGE · §3.1 Masked LM · p.4 ─           ║  ← peek-cited-label
║                                                      ║
║ ┌────────────────────────────────────────────────┐  ║
║ ▌  We mask ██████% of all input tokens at random  │  ║  ← cited paragraph
║ ▌  and train the model to predict the original   │  ║    bg: gold gradient
║ ▌  vocabulary id of the masked word based only   │  ║    border: gold×0.22
║ ▌  on its context. Unlike traditional left-to-   │  ║    left bar: 2px gold
║ ▌  right LM pre-training, the MLM objective      │  ║
║ ▌  enables the representation to fuse the left   │  ║    ██████ = highlighted
║ ▌  and right context.                            │  ║    phrase matching
║ └────────────────────────────────────────────────┘  ║    chat sentence
║                                                      ║
║  Although this allows us to obtain a bidirectional   ║  ← context-after
║  pre-trained model, a downside is that we are        ║    opacity 0.5, 12px
║  creating a mismatch between pre-training and...     ║
║                                                      ║
╠══════════════════════════════════════════════════════╣
║  ● 94% confidence  · HAVF verified     [Open in PDF ↗] ║  ← peek-footer (bg --s3)
╚══════════════════════════════════════════════════════╝

Width:      430px fixed
Max-height: 520px (body scrolls if overflow)
Border-radius: 10px
Shadow:     0 20px 50px rgba(0,0,0,0.7)
            0 4px  16px rgba(0,0,0,0.5)
            0 0 0 1px rgba(gold,0.08)
```

### 11.2 Positioning Logic

```
PREFERRED POSITION:
  left:  mouse.x + 16px
  top:   sentence.bottom + 8px

OVERFLOW CORRECTIONS:
  right overflow:  left = mouse.x - 430px - 12px  (flip to left of cursor)
  bottom overflow: top  = sentence.top - 520px - 8px  (flip above sentence)
  always clamped: 8px from any viewport edge

STAYS OPEN WHEN:
  • Mouse moves within the cited-sentence area
  • Mouse enters the peek pane itself
  • (both mouseleave events cancel a 220ms hide timer)

CLOSES WHEN:
  • Mouse leaves cited-sentence AND peek pane
  • 220ms debounce (allows mouse travel between sentence and pane)
  • Immediately on peek-pane mouseleave if sentence also left
```

### 11.3 Content Sections of Peek Pane

```
┌─────────────────────────────────────────────────────────┐
│ HEADER                                                  │
│   • Paper tag: "PAPER [N] · PAGE X"  (gold mono, dot)  │
│   • Paper full title  (13px 600)                        │
│   • Authors + year   (11px --t3)                        │
│   • Section path: "Section Title  ›  Subsection"       │
├─────────────────────────────────────────────────────────┤
│ BODY (scrollable)                                       │
│   • [optional] Context-before paragraph  (0.5 opacity) │
│   • Label: "CITED PASSAGE · §subsection · p.N"         │
│   • Cited paragraph (gold highlight, key phrase bolded) │
│   • [optional] Context-after paragraph  (0.5 opacity)  │
├─────────────────────────────────────────────────────────┤
│ FOOTER                                                  │
│   • Confidence dot (green/amber/red by score)          │
│   • "XX% confidence · HAVF verified"                   │
│   • "Open in PDF ↗" button → jump + open side panel    │
└─────────────────────────────────────────────────────────┘
```

### 11.4 Confidence Colour Mapping

```
SCORE ≥ 85%   dot: #34d399 (green)   label: "X% confidence"
SCORE 65–84%  dot: #fbbf24 (amber)   label: "X% confidence"
SCORE < 65%   dot: #f87171 (red)     label: "X% confidence (low)"
```

### 11.5 In-paragraph Key Phrase Highlighting

The peek pane attempts to highlight the key phrase from the chat sentence inside the cited paragraph:

```
Chat sentence:   "...based on bidirectional context"
Cited paragraph: "...the MLM objective enables the representation
                  to fuse the left and right context, which allows
                  us to pretrain a deep bidirectional Transformer."

Result in peek:
  "...to fuse the left and right context, which allows us to
   pretrain a deep ██████████████ Transformer."
                   bidirectional
                   ↑ highlighted span, rgba(gold,0.2)
```

---

## 12. Feature: Citation Superscript Tooltip

A lightweight, small tooltip appears when hovering the `¹²³` superscript markers directly (as opposed to hovering the full sentence, which triggers the peek pane).

### 12.1 Wireframe

```
                           ↑  Citation ¹ in gold
┌──────────────────────────────┐
│  ¹ BERT Paper · §3.1 · p.4  │  ← tooltip-paper (gold, 600)
│  "We mask 15% of all toks…" │  ← tooltip-preview (italic --t3)
│  Confidence: 94% (high)     │  ← tooltip-conf (--hi)
│  ─────────────────────────  │
│  Click to jump in PDF →     │  ← tooltip-hint (9.5px --t3)
└──────────────────────────────┘
  Width: max 280px
  bg: --s4, border: --b2
  box-shadow: 0 4px 12px rgba(0,0,0,0.5)
  pointer-events: none  (cannot be hovered)
  z-index: 1000 (above peek pane)

  Positioned: left = citation.left, top = citation.bottom + 7px
```

### 12.2 Tooltip vs Peek Pane Relationship

```
HOVER TARGET          INTERACTION            RESULT
──────────────────────────────────────────────────────────────
Cited sentence        hover                 Peek Pane (large)
Cited sentence        —                     —
Citation superscript  hover (stops bubble)  Small tooltip only
Citation superscript  click                 Jump to PDF + open panel
```

---

## 13. Interaction Flow Diagrams

### 13.1 Primary Attribution Flow

```
User hovers cited sentence
         │
         ▼
   cited-sentence mouseover
         │
         ▼
   showPeek() called
    │
    ├─ Reads data-* attributes from sentence element
    │    data-paper, data-authors, data-section
    │    data-subsection, data-page, data-para
    │    data-context-before, data-context-after
    │    data-conf, data-para-id
    │
    ├─ Populates peek pane header, body, footer
    │
    ├─ Calculates smart position (viewport-aware)
    │
    └─ Adds .visible class → CSS transition animates in
              opacity: 0 → 1
              transform: translateY(8px) scale(0.98) → translateY(0) scale(1)
              duration: 0.2s ease
         │
         ▼
   User reads source context in peek pane
         │
    ┌────┴─────────────────────────────┐
    │                                  │
    ▼                                  ▼
User clicks "Open in PDF ↗"    User moves mouse away
         │                             │
         ▼                             ▼
  jumpToSource(paraId)         220ms debounce timer
         │                             │
         ├─ Opens PDF panel            ▼
         │  if hidden              hidePeek()
         │                             │
         ├─ Scrolls to paragraph       └─ removes .visible
         │  (smooth scroll,               removes .peek-active
         │   block: center)               from sentence
         │
         └─ Adds .highlighted class
            → pulse animation 2s
```

### 13.2 Citation Click Flow

```
User clicks ¹ superscript
         │
         ▼
   citation click handler
         │
         ├─ Stops propagation (no sentence hover trigger)
         │
         ├─ Reads data-source-id (paragraph ID)
         │
         └─ jumpToSource(paraId)
                   │
                   ├─ PDF panel: remove .hidden if present
                   │   → width: 0 → 580px (0.3s cubic-bezier)
                   │
                   ├─ Remove .highlighted from all paragraphs
                   │
                   ├─ document.getElementById(paraId).scrollIntoView()
                   │   behavior: 'smooth', block: 'center'
                   │
                   └─ Add .highlighted → pulse animation
                      Remove .highlighted after 2200ms
```

### 13.3 PDF Panel Toggle Flow

```
User clicks 📖 button (paper card or PDF header)
         │
         ▼
  togglePDF()
         │
         ├─ If panel has .hidden:
         │    remove .hidden
         │    → width: 580px (CSS transition 0.3s)
         │
         └─ If panel visible:
              add .hidden
              → width: 0 (CSS transition 0.3s)
```

---

## 14. State Diagrams

### 14.1 Application View States

```
                     ┌─────────────────────────────────────────┐
                     │          WORKSPACE (default)            │
                     │  Left + Chat + Right  (PDF hidden)      │
                     └──────────────┬──────────────────────────┘
                                    │
              ┌─────────────────────┼──────────────────────┐
              │                     │                      │
              ▼                     ▼                      ▼
  ┌─────────────────────┐  ┌──────────────┐  ┌────────────────────────┐
  │  WORKSPACE + PDF    │  │   LIBRARY    │  │   ANALYTICS / SETTINGS │
  │  Left+Chat+Right    │  │  (nav tab)   │  │      (nav tabs)        │
  │  + PDF side panel   │  └──────────────┘  └────────────────────────┘
  └─────────────────────┘
```

### 14.2 Peek Pane States

```
HIDDEN (default)
  opacity: 0, pointer-events: none
  transform: translateY(8px) scale(0.98)
       │
       │  mouseenter .cited-sentence
       ▼
ENTERING (transition)
  opacity: 0 → 1
  transform: → translateY(0) scale(1)
  duration: 0.2s ease
       │
       │  transition complete
       ▼
VISIBLE
  opacity: 1, pointer-events: auto
  can be read, scrolled, clicked
       │
       ├──────────────────────────┐
       │                          │
       │  mouseleave sentence     │  mouseenter peek pane
       │  (220ms debounce)        │  (clears timer → stays open)
       ▼                          │
HIDING (debounce)                 │
  220ms timer                     │  mouseleave peek pane
       │                          │  (immediate)
       │  timer fires             │
       ▼                          ▼
HIDDEN ←─────────────────── HIDING (immediate)
```

### 14.3 PDF Panel States

```
HIDDEN (default)
  width: 0, border: none, overflow: hidden
       │  📖 click / citation click
       ▼
OPENING (transition)
  width: 0 → 580px
  transition: 0.3s cubic-bezier(0.16, 1, 0.3, 1)
       │  transition complete
       ▼
OPEN
  width: 580px
  paragraph can be: resting / highlighted
       │  📖 click / × click
       ▼
CLOSING (transition)
  width: 580px → 0
       │
       ▼
HIDDEN
```

### 14.4 Paper Indexing States

```
UPLOADING →  EXTRACTING →  EMBEDDING →  INDEXED  →  READY
   ⟳               ⟳            ⟳          ✓          ✓
(progress)    (progress)   (progress)   (static)  (queryable)
```

---

## 15. Responsive Behaviour

TraceLit is desktop-first. Panels collapse progressively at smaller viewports.

### 15.1 Breakpoints

```
BREAKPOINT    WIDTH         BEHAVIOUR
──────────────────────────────────────────────────────────────
Full          ≥ 1400px      All 4 panels visible simultaneously
Standard      1100–1399px   PDF panel hidden by default (toggle only)
Compact       900–1099px    Left sidebar collapses to icon-only (48px)
Tablet        768–899px     Right sidebar hides behind slide-over drawer
Mobile        < 768px       Single-panel view, swipe between panels
                            (not recommended for active research)
```

### 15.2 Left Sidebar Collapse (Compact mode)

```
FULL (224px):             ICON-ONLY (48px):
┌────────────────────┐   ┌──────┐
│  SESSIONS    [+]   │   │  +   │
│ ▌ Transformer Arch │   │ ─────│
│   BERT vs GPT      │   │  💬  │  ← tools as icon-only
│                    │   │  🔬  │
│  TOOLS             │   │  ⚖️  │
│  💬 Chat Q&A  ⌘1   │   │  🕳️  │
│  🔬 Deep Ext  ⌘2   │   │ ─────│
│  ...               │   │  ✅  │
└────────────────────┘   │  📊  │
                         └──────┘
```

---

## 16. Accessibility Notes

### Keyboard Navigation

```
TAB               Navigate between interactive elements
ENTER / SPACE     Activate buttons, open peek pane for cited sentence
ESCAPE            Close peek pane, close PDF panel
←  →              Navigate PDF pages (when PDF panel focused)
⌘1–4              Tool shortcuts (Chat, Deep, Compare, Gap)
⌘E                Export report
```

### ARIA Roles and Labels

```
ELEMENT                     ROLE / LABEL
──────────────────────────────────────────────────────
.cited-sentence             role="button", aria-label="View source: {paper} §{section}"
.citation                   role="button", aria-label="Citation {n}: {paper} page {p}"
.peek-pane                  role="dialog", aria-label="Source preview"
#pdfPanel                   role="complementary", aria-label="PDF viewer"
.confidence-bar             aria-label="Confidence score: {n}%"
.send-btn                   aria-label="Send message"
```

### Colour Contrast

```
--t1  on  --s2    #ececec / #141414   WCAG AAA  ✓
--t2  on  --s2    #aaaaaa / #141414   WCAG AA   ✓
--gold on --s2    #c9a96e / #141414   WCAG AA   ✓
--hi  on  --s2    #34d399 / #141414   WCAG AA   ✓
```

---

## 17. Animation & Motion Spec

### 17.1 Transitions

```
ELEMENT                     PROPERTY          DURATION   EASING
────────────────────────────────────────────────────────────────────
Peek pane show/hide         opacity           200ms      ease
                            transform         200ms      ease
PDF panel open/close        width             300ms      cubic-bezier(0.16,1,0.3,1)
Cited sentence hover bg     background        180ms      ease
Citation hover              background        150ms      ease
Paper card hover            background,border 150ms      ease
Tool item hover             background        150ms      ease
Session item hover          background        150ms      ease
Session active bar          opacity,height    150ms      ease
Nav tab hover/active        all               150ms      ease
Send button hover           opacity           150ms      ease
```

### 17.2 Keyframe Animations

```
NAME              DURATION   TRIGGER                     EFFECT
────────────────────────────────────────────────────────────────────
breathe           3s inf     Status dot (always on)      opacity 1 → 0.45 → 1
para-pulse        2s once    PDF paragraph .highlighted  gold bg fades out
label-fade        2s once    "↓ Citation source" label   slide up + fade out
```

### 17.3 Micro-interactions

```
PDF button (📖):      hover → scale(1.1), opacity 1.0
Citation (¹):         hover → scale(1.05), bg gold-dim
Avatar:               hover → border-color --gold
Pane-action (+):      hover → color --gold
Control button:       active state → immediate, no delay
```

---

## Appendix A: Data Attributes on `.cited-sentence`

Every cited sentence carries a complete set of source metadata as HTML data attributes, enabling zero-fetch peek pane rendering:

```html
<span class="cited-sentence"
  data-paper="Full paper title"
  data-authors="Author et al. YEAR"
  data-section="N. Section Title"
  data-subsection="N.M Subsection Title"
  data-page="4"
  data-para="The full verbatim paragraph text from the source..."
  data-context-before="The paragraph that appears before the cited one..."
  data-context-after="The paragraph that appears after the cited one..."
  data-conf="94"
  data-para-id="p1">
  Chat sentence text goes here<span class="citation" data-source-id="p1">¹</span>.
</span>
```

---

## Appendix B: CSS Custom Properties Reference

```css
/* Backgrounds */
--bg, --s1, --s2, --s3, --s4, --s5

/* Borders */
--b1, --b2, --b3

/* Text */
--t1, --t2, --t3, --t4

/* Accent */
--gold, --gold-dim, --gold-glow

/* Semantic */
--hi, --hi-dim, --med, --low, --info

/* Fonts */
--serif, --mono, --sans

/* Radius */
--r  (6px default)
```

---

## Appendix C: File & Component Map

```
tracelit.html
├── <style>
│   ├── Design tokens (:root)
│   ├── App shell (.app, .topbar, .workspace)
│   ├── Panel base (.panel)
│   ├── Left sidebar (.panel-left, .sessions-pane, .tools-pane)
│   ├── Chat panel (.panel-chat, .messages, .message, .chat-input)
│   ├── Cited sentence & citation (.cited-sentence, .citation)
│   ├── Confidence bar (.confidence-bar)
│   ├── Right sidebar (.panel-right, .paper-card)
│   ├── PDF viewer (.panel-pdf, .pdf-paragraph, .highlighted)
│   ├── Peek pane (.peek-pane, .peek-header, .peek-body, .peek-footer)
│   └── Tooltip (.tooltip)
│
├── <body>
│   ├── .topbar (logo, nav-tabs, topbar-right)
│   ├── .workspace
│   │   ├── .panel-left
│   │   │   ├── .sessions-pane
│   │   │   └── .tools-pane
│   │   ├── .panel-chat
│   │   │   ├── .chat-bar
│   │   │   ├── .messages (cited-sentence + citation elements)
│   │   │   └── .chat-input
│   │   ├── .panel-right (paper-cards)
│   │   └── .panel-pdf (pdf-content with paragraphs)
│   ├── #peekPane (floating, position:fixed)
│   └── #tooltip (floating, position:fixed)
│
└── <script>
    ├── togglePDF()
    ├── jumpToSource(paraId)
    ├── showPeek(sentence, event)
    ├── hidePeek(immediately)
    ├── cited-sentence event listeners (mouseenter/mousemove/mouseleave)
    ├── peek-pane hover persistence (mouseenter/mouseleave)
    └── citation event listeners (click → jump, hover → tooltip)
```

---

*TraceLit UI Design Specification v4.0 — February 2026*
*Every sentence cited. Every source verified.*
