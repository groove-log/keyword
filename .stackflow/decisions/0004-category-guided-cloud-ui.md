# ADR-0004: Category-Guided Keyword Weighting and Premium Word Cloud UI

## Status
Approved

## Context
When the document was classified as a specific safety risk (e.g., `"안전사고"`), the extracted top-N keywords displayed in the right panel (e.g., `"강남점 앞"`, `"상자 박스"`, `"보행"`) remained labeled as `"정상"`. This created a semantic discrepancy and user confusion: *"Why is the overall document an accident risk, but all key terms are normal?"*

The root causes were:
1. **Single-word limitations**: Neutral nouns themselves don't carry risk in isolation, whereas the sentence does.
2. **KeyBERT priority**: KeyBERT maximizes context coverage, not risk importance.
3. **Noun-only extraction**: Useful safety action verbs (e.g., `"넘어지다"`, `"침범하다"`) were filtered out.

To solve this, the user approved **Proposal A (Category-Guided Weighting)** and requested a brand-new **interactive Word Cloud UI** to replace the boring linear list, making the risk-aligned words visually dominant and replacing technical jargon (like "similarity", "semantic", "extraction") with simple, intuitive terms.

## Decision
We will implement the following changes:

### 1. Backend: Category-Guided Keyword Weighting
- When the overall document is classified under a danger category (e.g., `doc_risk_level != "정상 문의"`), we will adjust the final sorting score of all keyword candidates using the formula:
  $$\text{Score}_{\text{final}}(c) = \text{Score}_{\text{KeyBERT}}(c) + \beta \times \text{Similarity}(c, \text{Guideline of } doc\_risk\_level)$$
  where $\beta$ is a weighting coefficient (e.g., `0.35`).
- This mathematically guarantees that words aligned with the actual danger category (e.g., `"교통사고"`, `"위험"`, `"넘어짐"`) are elevated into the Top-N keywords list.
- We will expand kiwi candidate extraction slightly to allow nominalized verbs (e.g., `"넘어짐"`, `"부딪힘"`, `"방치"`) to ensure action-oriented hazards are captured.

### 2. Frontend: Premium Glassmorphic Word Cloud UI
- Replace the strict vertical list with a **dynamic, organic Word Cloud** component.
- **Visual Dominance**: 
  - Neutral/normal keywords will appear in subtle cyan/mint glassmorphic badges.
  - Risk-aligned keywords (same category as overall document classification) will be significantly larger, highlighted with high-contrast warm-neon borders (orange/red gradient), and animated with a gentle pulse effect.
- **Simplified Terminology**:
  - Replace technical jargon with human-friendly, plain Korean:
    - `Extraction Score` $\rightarrow$ **`"본문 연관성"`** (How much this word represents the overall conversation topic)
    - `Cosine Similarity` $\rightarrow$ **`"위험 부합도"`** (How much this word relates to the identified risk category)
- **Interactive Micro-animations**: Clicking or hovering on a keyword bubble will reveal an elegant floating tooltip popover detailing these simple indexes with smooth transitions.

## Consequences
- **Improved UX coherence**: Users will immediately see *why* a document is classified as a hazard by looking at the prominent, large danger-labeled keywords in the cloud.
- **Higher engagement**: Changing to an interactive word cloud increases the application's aesthetic value and professional wow-factor.
- **Minimal Performance Impact**: Category similarity only runs on the small pool of extracted keyword candidates, which is extremely lightweight.
