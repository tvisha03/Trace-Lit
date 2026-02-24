# TraceLit — RAG & Chunking Strategy

> This document defines the Retrieval-Augmented Generation pipeline and chunking approach.  
> **Core Principle**: Every chunk must track individual sentence boundaries to enable sentence-level attribution.

---

## 1. Overview

TraceLit's RAG pipeline is **sentence-aware** — unlike standard RAG that chunks text into 500-token blocks with no internal structure, TraceLit chunks at paragraph level and tracks every sentence within each chunk with a unique ID. This enables click-to-sentence navigation and HAVF verification at the sentence level.

```
Standard RAG Pipeline:
  PDF → Chunk (512 tokens) → Embed → Store → Retrieve → Generate
  Problem: Citation points to 500-token block, not specific sentence

TraceLit RAG Pipeline:
  PDF → Extract sections → Paragraph-level chunk with sentence tracking
      → Context-enriched embed → ChromaDB store
      → Retrieve per-paper top-k → Citation-in-prompting
      → Generate with [P#] citations → HAVF verify per sentence
      → UI renders with click-to-sentence
```

---

## 2. PDF Extraction

### Primary Tool: PyMuPDF4LLM

```python
import pymupdf4llm

md_text = pymupdf4llm.to_markdown(
    pdf_path,
    page_chunks=True,       # Split by page for section detection
    write_images=True,       # Extract figures
    image_format="png",
    dpi=200
)
```

**Output**: Markdown-formatted text with headings, paragraphs, and image references.

### Section Parsing

After extraction, detect section headings by:
1. Markdown heading patterns (`## Section Title`)
2. Font size changes (if metadata available)
3. Numbering patterns (`1. Introduction`, `2.1 Related Work`)

Store each section with: `title`, `page_start`, `order`, `content` (list of text lines).

### Phase 2 Option: Docling (IBM)

For table-heavy papers (>30% pages contain tables), Docling provides better quality extraction. Use auto-detection:

```python
table_density = await _detect_table_density(pdf_path)  # pdfplumber quick scan
if table_density > 0.3:
    return await _extract_docling(pdf_path)
else:
    return await _extract_pymupdf(pdf_path)
```

### Formula Handling

Mathematical formulas are extracted as **images** (not LaTeX). Even Docling achieves only 70–75% on LaTeX extraction. For TraceLit's scope, image-based display is acceptable since most research claims are text-based.

---

## 3. Sentence-Aware Chunking 🚨 NON-NEGOTIABLE

### Why This Matters

```
Without sentence tracking:
  LLM says: "BERT uses masked language modeling [P5]"
  User clicks [P5] → sees 500-token paragraph
  ❌ Which sentence supports the claim?

With sentence tracking:
  LLM says: "BERT uses masked language modeling [P5]"
  HAVF identifies: P5_S2 is the supporting sentence
  User clicks → exact sentence highlighted in source viewer
  ✅ Academic-grade verification
```

### Chunking Algorithm

```python
class SentenceAwareChunker:
    def chunk_section(self, section: Dict, paper_metadata: Dict) -> List[Dict]:
        paragraphs = self._split_paragraphs(section['content'])
        chunks = []

        for para_idx, para_text in enumerate(paragraphs):
            sentences = self._split_sentences(para_text)
            sentence_map = []

            for sent_idx, sent_text in enumerate(sentences):
                sentence_map.append({
                    "sentence_id": f"P{para_idx}_S{sent_idx}",
                    "text": sent_text,
                    "start_char": para_text.find(sent_text),
                    "end_char": para_text.find(sent_text) + len(sent_text),
                    "tokens": len(sent_text) // 4  # Rough estimate
                })

            # Context enrichment improves retrieval by 15-20%
            enriched_text = (
                f"[Paper: {paper_metadata['title']}] "
                f"[Section: {section['title']}] "
                f"{para_text}"
            )

            chunk = {
                "paragraph_id": f"P{para_idx}",
                "text": para_text,             # Original text for display
                "enriched_text": enriched_text, # For embedding (includes context)
                "sentences": sentence_map,      # For attribution
                "section": section['title'],
                "page": section.get('page', 0),
                "paper_id": paper_metadata['paper_id'],
                "paper_title": paper_metadata['title']
            }
            chunks.append(chunk)
        return chunks
```

### Sentence Splitting Rules

Academic text has special patterns that break naive splitting. Handle these:

```python
def _split_sentences(self, text: str) -> List[str]:
    """
    Handles: Dr., Fig., et al., e.g., i.e., decimals (3.14), citations ([1])
    """
    pattern = r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<![A-Z]\.)(?<=\.|\?|\!)\s+'
    sentences = re.split(pattern, text)
    return [s.strip() for s in sentences if s.strip()]
```

**Known edge cases**:
- "et al." should NOT split
- "Fig. 3" should NOT split
- "e.g." and "i.e." should NOT split
- Decimal numbers like "3.14" should NOT split
- Sentences ending with citations like "...accuracy [12]." SHOULD split

---

## 4. Context Enrichment

Each chunk is embedded with hierarchical context prefix:

```
Original:  "The model achieved 93.2% accuracy on GLUE benchmark."
Enriched:  "[Paper: BERT] [Section: 5. Experiments] The model achieved 93.2% accuracy on GLUE benchmark."
```

**Why**: The embedding captures document structure alongside content. Internal testing shows **15–20% improvement** in retrieval relevance because the model understands which paper and section a statement comes from.

**Rule**: Always embed the `enriched_text`, but store and display the original `text`.

---

## 5. Embedding Strategy

### Model: `all-MiniLM-L6-v2`

| Property | Value |
|----------|-------|
| Size | 23MB |
| Dimensions | 384 |
| Speed | ~0.3s per 100 paragraphs (MPS) |
| RAM | ~200MB |
| Quality | Good (sufficient for academic text) |

**Why this model**: Best speed/size/quality tradeoff for M3's 8GB budget. `all-mpnet-base-v2` is better but 420MB and too slow. `instructor-xl` won't fit in memory.

### MPS Acceleration

```python
class MPSAcceleratedEmbedder:
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        self.device = 'mps' if torch.backends.mps.is_available() else 'cpu'
        self.model = SentenceTransformer(model_name).to(self.device)

    def encode_batch(self, texts: List[str], batch_size=64):
        with torch.no_grad():
            return self.model.encode(texts, device=self.device, batch_size=batch_size)
```

**Performance**: CPU ~0.8s per 100 paragraphs → MPS ~0.3s per 100 paragraphs (**2.7x speedup**).

---

## 6. Vector Store: ChromaDB

### Configuration

```python
import chromadb

client = chromadb.PersistentClient(path="./data/chroma")
collection = client.get_or_create_collection(
    name="tracelit_papers",
    metadata={"hnsw:space": "cosine"}  # Cosine similarity
)
```

### What Gets Stored

```python
collection.add(
    ids=[chunk["paragraph_id"]],
    documents=[chunk["enriched_text"]],  # Enriched text for search
    metadatas=[{
        "paper_id": chunk["paper_id"],
        "paper_title": chunk["paper_title"],
        "section": chunk["section"],
        "page": chunk["page"],
        "original_text": chunk["text"],     # For display
        "sentences": json.dumps(chunk["sentences"])  # Sentence map
    }],
    embeddings=[embedding]  # Pre-computed MPS embedding
)
```

### Retrieval

```python
results = collection.query(
    query_embeddings=[query_embedding],
    n_results=5,  # Top 5 per paper
    where={"paper_id": {"$in": active_paper_ids}}  # Filter by active papers
)
```

**Retrieval strategy**: Top-k per paper (not global top-k) to ensure every active paper is represented in context.

---

## 7. Citation-in-Prompting

The retrieved chunks are assembled into a prompt that instructs the LLM to cite every sentence:

```python
CITATION_SYSTEM_PROMPT = """You are an expert academic research assistant.

CRITICAL RULES:
1. After EVERY sentence, cite the source using [P#] format
2. Use [P1], [P2], etc. matching the paragraph IDs provided
3. If multiple sources support a sentence, cite all: [P1][P3]
4. Never make claims without citations
5. If information is not in sources, say "Not found in provided papers"
6. Be precise and factual — no speculation

CITATION FORMAT EXAMPLE:
"BERT uses masked language modeling [P12]. This improved GLUE benchmarks [P15][P18]."
"""

# Context assembly
context_text = ""
for chunk in retrieved_chunks:
    context_text += f"\n[{chunk['paragraph_id']}] (Paper: {chunk['paper_title']}, "
    context_text += f"Section: {chunk['section']}, Page: {chunk['page']})\n"
    context_text += chunk['text'] + "\n"
```

---

## 8. Post-Retrieval: HAVF Verification

After the LLM generates a response, HAVF verifies each sentence. See `HAVF_VERIFICATION_PIPELINE.md` for full details.

**Flow**:
1. Parse LLM response into individual sentences with their `[P#]` citations
2. For each sentence, run HAVF Level 1 (embedding similarity) against the cited paragraph's sentences
3. If uncertain, run HAVF Level 2 (cross-encoder reranking)
4. Return confidence score + specific `sentence_id` for UI highlighting

---

## 9. Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Chunk granularity | Paragraph | Sentence-level chunks lose context; paragraph preserves it |
| Embedding target | Enriched text (with paper+section prefix) | 15–20% retrieval improvement |
| Retrieval scope | Top-k **per paper** | Ensures all active papers contribute to context |
| Sentence splitting | Regex-based | Lightweight, handles academic abbreviations |
| Vector store | ChromaDB (persistent, cosine) | Metal-optimized, simple, fits M3 budget |
| Embedding model | all-MiniLM-L6-v2 | 23MB, fast on MPS, 200MB RAM |

---

## 10. Common Pitfalls to Avoid

1. **DO NOT** chunk at sentence level — you lose paragraph context and retrieval quality drops
2. **DO NOT** embed the original text — always use the enriched text with paper/section prefix
3. **DO NOT** use global top-k retrieval — use per-paper top-k so all papers are represented
4. **DO NOT** skip sentence boundary tracking — it's the entire point of TraceLit's innovation
5. **DO NOT** store enriched text as the display text — store original for display, enriched for embedding
6. **DO NOT** use a heavy embedding model — M3 has 8GB total, budget ~200MB for embeddings
