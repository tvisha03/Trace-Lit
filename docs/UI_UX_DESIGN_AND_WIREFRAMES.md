# TraceLit — UI/UX Design & Wireframes

> Design system, component library, wireframes, and interaction patterns.  
> All designs follow academic aesthetics — clean, information-dense, trustworthy.

---

## 1. Design System

### 1.1 Color Palette

```css
:root {
  /* Primary */
  --primary-blue: #1e3a8a;
  --primary-blue-light: #3b82f6;
  --primary-blue-lighter: #eff6ff;

  /* Confidence Colors — CRITICAL for attribution display */
  --confidence-high: #10b981;     /* Green — ≥ 85% confidence */
  --confidence-medium: #f59e0b;   /* Yellow — 65–84% confidence */
  --confidence-low: #ef4444;      /* Red — < 65% confidence */

  /* Neutral */
  --gray-900: #1f2937;
  --gray-600: #6b7280;
  --gray-200: #e5e7eb;
  --gray-50: #f9fafb;

  /* Semantic */
  --success: #10b981;
  --warning: #f59e0b;
  --error: #ef4444;
  --info: #3b82f6;
}
```

### 1.2 Typography

```css
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;

/* Scale */
--text-xs: 12px;    /* Labels, captions */
--text-sm: 14px;    /* Secondary text */
--text-base: 16px;  /* Body text */
--text-lg: 18px;    /* Subheadings */
--text-xl: 20px;    /* Section headers */
--text-2xl: 24px;   /* Page titles */
--text-3xl: 30px;   /* Hero text */

/* Weights */
--font-normal: 400;
--font-medium: 500;
--font-semibold: 600;
--font-bold: 700;
```

### 1.3 Spacing

4px grid system (0.25rem increments):  
`4px | 8px | 12px | 16px | 20px | 24px | 32px | 40px | 48px | 64px`

### 1.4 Border Radius

```css
--rounded-sm: 4px;   /* Badges, small elements */
--rounded-md: 6px;   /* Buttons, inputs */
--rounded-lg: 8px;   /* Cards */
--rounded-xl: 12px;  /* Modals */
```

---

## 2. Layout Architecture

### 2.1 Main Layout

```
┌────────────────────────────────────────────────────────────┐
│  HEADER BAR (h-14, sticky top)                             │
│  ┌──────────┬─────────────────────┬────────────────────┐  │
│  │ TraceLit │  Papers: 5/7 ●●●●●○○│  💾 Save | Export │  │
│  │  logo    │  Session: AI Survey  │  buttons          │  │
│  └──────────┴─────────────────────┴────────────────────┘  │
├────────────────────────────────────────────────────────────┤
│  ┌────────────┬──────────────────────────────────────────┐│
│  │  SIDEBAR   │         MAIN WORKSPACE                   ││
│  │  (w-64)    │                                          ││
│  │            │   ┌────────────────────────────────┐    ││
│  │ 📚 Papers  │   │ TABS:                          │    ││
│  │ ✓ BERT     │   │ Chat │Compare│Review│Gaps     │    ││
│  │ ✓ GPT-2    │   └────────────────────────────────┘    ││
│  │ ✓ Llama    │                                          ││
│  │ ○ T5 ...   │   [Active tab content renders here]     ││
│  │            │                                          ││
│  │ 🔑 Keywords│   • Chat: Split-pane (source + chat)    ││
│  │ • Transform│   • Compare: Auto-generated table       ││
│  │ • Attention│   • Review: Literature review editor     ││
│  │            │   • Gaps: Cluster view (Phase 2)        ││
│  │ ⚙️ Settings│                                          ││
│  │ [Local/Cloud]                                         ││
│  │ Confidence │                                          ││
│  └────────────┴──────────────────────────────────────────┘│
└────────────────────────────────────────────────────────────┘
```

### 2.2 Chat Tab — Split-Pane View

```
┌──────────────────┬───────────────────────────────────────┐
│  SOURCE VIEWER   │   CHAT INTERFACE                      │
│  (40% width)     │   (60% width)                         │
│                  │                                       │
│  📄 BERT Paper   │   You: Compare BERT and GPT-2        │
│  ──────────────  │                                       │
│                  │   🤖 TraceLit:                        │
│  1. Introduction │   BERT uses masked language model¹    │
│  The Transformer │   ████████ 94% ✓                      │
│  architecture... │                                       │
│  ═══════════════ │   GPT-2 uses autoregressive...²      │
│  [Highlighted    │   ███████░ 87% ⚠️                     │
│   sentence with  │                                       │
│   blue pulse]    │   Both are transformers³              │
│                  │   ██████░░ 78% ⚠️                     │
│  2. Related Work │                                       │
│  Previous work   │   ─────────────────────               │
│  on...           │   Sources:                            │
│                  │   [1] BERT paper, p.3 (click)         │
│  [Click any      │   [2] GPT-2 paper, p.7 (click)       │
│   citation →     │   [3] Attention paper, p.1            │
│   scroll here]   │                                       │
│                  │   [Toggle: Clean Reading | Full Attr] │
│                  │   Type your question...   [Send]      │
└──────────────────┴───────────────────────────────────────┘
```

### 2.3 Comparison Tab

```
┌──────────────────────────────────────────────────────────┐
│  📊 Paper Comparison   [Generate] [Excel] [LaTeX]       │
├─────────────┬───────────┬───────────┬──────────────────┤
│ Aspect      │ BERT      │ GPT-2     │ Llama            │
├─────────────┼───────────┼───────────┼──────────────────┤
│ Problem     │ Lack of   │ Generic   │ Closed models    │
│ Addressed   │ bidirect. │ LM [P2]   │ [P3]             │
├─────────────┼───────────┼───────────┼──────────────────┤
│ Method      │ Masked LM │ Autoregr. │ Instruct tuning  │
│             │ + NSP     │           │                  │
├─────────────┼───────────┼───────────┼──────────────────┤
│ Dataset     │ Books +   │ WebText   │ Custom mix       │
│             │ Wikipedia │ (8M docs) │ (2T tokens)      │
├─────────────┼───────────┼───────────┼──────────────────┤
│ Key Results │ GLUE 93.2%│ 89.4 F1   │ 82.3% MMLU      │
└─────────────┴───────────┴───────────┴──────────────────┘
│  [Add Custom Row] [Filter Columns] [Edit Mode]         │
└──────────────────────────────────────────────────────────┘
```

### 2.4 Confidence Dashboard (Modal)

```
┌──────────────────────────────────────────────────────┐
│  📊 Response Confidence Analysis               [✕]   │
├──────────────────────────────────────────────────────┤
│  Overall: 87%  ⭐⭐⭐⭐   9/10 verified              │
│                                                      │
│  1. "BERT uses masked LM"                           │
│     ████████ 94% ✓ HIGH                             │
│     Source: Devlin et al., p.3                      │
│                                                      │
│  2. "GPT-2 employs autoregressive..."               │
│     ███████░ 87% ⚠️ MEDIUM                          │
│     Source: Radford et al., p.7                     │
│                                                      │
│  3. "Both use transformers"                          │
│     ██████░░ 78% ⚠️ LOW                             │
│     Warning: Vague statement, verify manually       │
│                                                      │
│  [Export Confidence Report]             [Close]     │
└──────────────────────────────────────────────────────┘
```

---

## 3. Component Library

### 3.1 Core Components

| Component | File | Description |
|-----------|------|-------------|
| `CitedSentence` | `chat/CitedSentence.jsx` | Renders sentence with inline superscript citations and confidence-colored underline on hover |
| `CitationTooltip` | `chat/CitationTooltip.jsx` | Popup: paper title, section, page number, preview text |
| `ConfidenceTooltip` | `common/ConfidenceTooltip.jsx` | Dark tooltip: HIGH/MEDIUM/LOW label + percentage |
| `ConfidenceBadge` | `common/ConfidenceBadge.jsx` | Inline pill with percentage, color-coded |
| `ChatControls` | `chat/ChatControls.jsx` | "Clean Reading" ↔ "Full Attribution" toggle |
| `SourceViewer` | `source/SourceViewer.jsx` | Paper text with section nav, sentence highlighting |
| `SentenceHighlight` | `source/SentenceHighlight.jsx` | Blue pulse animation for highlighted sentences |
| `ComparisonTable` | `compare/ComparisonTable.jsx` | Editable table with click-to-source cells |
| `PaperUpload` | `papers/PaperUpload.jsx` | Drag-and-drop zone + file picker |
| `ProcessingProgress` | `papers/ProcessingProgress.jsx` | Per-paper progress bar with stage labels |
| `MessageSkeleton` | `common/LoadingSkeleton.jsx` | Shimmer loading state for streaming responses |
| `ErrorBoundary` | `common/ErrorBoundary.jsx` | Graceful error fallback for component crashes |

### 3.2 CitedSentence Component

The most important UI component — renders each LLM response sentence:

```jsx
export const CitedSentence = ({ sentence, showCitations, onCitationClick }) => {
  const confidenceStyle = {
    high:   { borderBottom: '2px solid #10b981' },  // Green
    medium: { borderBottom: '2px dashed #f59e0b' },  // Yellow dashed
    low:    { borderBottom: '2px dotted #ef4444' },  // Red dotted
  };

  return (
    <span style={confidenceStyle[sentence.level]}>
      {sentence.text}
      {showCitations && sentence.citations.map((cite, i) => (
        <sup
          key={i}
          className="cursor-pointer text-blue-600 hover:text-blue-800 ml-0.5"
          onClick={() => onCitationClick(cite)}
        >
          {cite.display_number}
        </sup>
      ))}
    </span>
  );
};
```

### 3.3 Sentence Highlighting CSS

```css
.sentence-highlight {
  background: linear-gradient(90deg,
    rgba(59, 130, 246, 0.2) 0%,
    rgba(59, 130, 246, 0.4) 50%,
    rgba(59, 130, 246, 0.2) 100%
  );
  animation: sentence-pulse 1s ease-in-out;
  border-radius: 4px;
  padding: 2px 4px;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3);
}

@keyframes sentence-pulse {
  0%, 100% { box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3); }
  50%      { box-shadow: 0 0 0 6px rgba(59, 130, 246, 0.1); }
}
```

---

## 4. Interaction Patterns

### 4.1 Citation Click Flow

```
1. User reads response sentence with superscript citation ¹
2. Hovers over ¹ → CitationTooltip appears (paper title, page, preview)
3. Clicks ¹ → Source viewer:
   a. Switches to correct paper tab (if not already showing)
   b. Scrolls to the paragraph containing the cited sentence
   c. Highlights the specific sentence with blue pulse (3 seconds)
4. User can click "Full Attribution" toggle to see all confidence info inline
```

### 4.2 Clean Reading vs Full Attribution Toggle

| Mode | Citations | Confidence | Underlines |
|------|-----------|------------|------------|
| **Clean Reading** | Hidden | Hidden | Hidden |
| **Full Attribution** | Superscript visible | Badge visible | Color-coded underlines |

Default: **Full Attribution** (this is the product's value prop).

### 4.3 Paper Processing Flow

```
1. User drops PDFs onto upload zone (or clicks file picker)
2. Upload area shows file list with size + "(processing...)" badges
3. Progress bar appears per paper: Extracting → Chunking → Embedding → Indexing
4. Toast notification: "📄 BERT paper ready! You can now query it."
5. Paper appears in sidebar with ✓ checkmark
6. Subsequent papers show toast as they complete
```

### 4.4 Error States

| State | UI |
|-------|-----|
| No papers uploaded | Empty state illustration + "Upload papers to get started" |
| Processing in progress | Skeleton loader + progress bars |
| Query with no ready papers | Disabled input + "Wait for papers to finish processing" |
| LLM rate limited | Yellow banner: "Switching providers..." (auto-recovers) |
| All providers failed | Red banner: "Service unavailable" + Retry button |
| Automatic fallback attribution | Yellow banner: "Citations automatically attributed" |
| PDF extraction failed | Red badge on paper in sidebar + "Extraction failed" tooltip |

---

## 5. Responsive Behavior

| Breakpoint | Layout |
|-----------|--------|
| ≥1280px (xl) | Full layout: sidebar + split-pane (source + chat) |
| ≥1024px (lg) | Sidebar collapses to icons, split-pane maintained |
| ≥768px (md) | No sidebar, tabbed view (source / chat as separate tabs) |
| <768px | Not primary target (local desktop app), basic responsive |

---

## 6. Accessibility

- All interactive elements keyboard-navigable
- ARIA labels on citation buttons, tooltips, modals
- Color-coded confidence ALWAYS paired with text label (HIGH/MEDIUM/LOW)
- Focus trap in modals
- `prefers-reduced-motion` disables pulse animations
- Minimum touch target: 44x44px
- Sufficient contrast ratios (WCAG AA)
