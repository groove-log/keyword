# ADR-0002: Document-Linked Keyword Classification for Cognitive Alignment

## Context & Problem

In ADR-0001, we implemented keyword-level semantic classification. However, a critical cognitive dissonance was identified:
- The overall document (counseling text) was correctly flagged as a danger category (e.g., `이물질 상품` for `"빵에서 벌레가 나왔어요"`).
- However, the crucial evidence keyword (e.g., `"벌레"`) was labeled as `"정상"` because single nouns suffer from "similarity score dilution" (getting around `0.5540`) and fail to meet the strict global/category threshold of `0.60`.
- This causes confusion for administrators who see a document classified as `이물질 상품` but cannot see any corresponding dangerous keywords that explain the classification.

## Proposed Decisions

To bridge this gap and provide an intuitive experience, we implement **Option A: Document-Linked Keyword Classification**:

1. **Document-Linked Logic**:
   - When classifying individual keywords, the system will pass the resolved overall document danger level (`doc_risk_level`) to the keyword classifier.
   - If the keyword's highest-matching category is identical to `doc_risk_level`, we apply a lower, relaxed baseline threshold (`DANGER_KEYWORD_LINKED_THRESHOLD = 0.45`).
   - If the highest-scoring category matches the document category and passes `0.45`, it is mapped to that category (e.g., `"벌레"` gets mapped to `이물질 상품` with score `0.5540`).

2. **Decoupled Fallback**:
   - If the keyword's best category does *not* match the document risk level, or if the document risk level is `"정상 문의"`, the system falls back to the standard category/global thresholds (e.g., `0.58 ~ 0.60`).
   - This ensures that a keyword from an unrelated category (e.g., `"소송"` appearing in a mostly normal or facilities-related text) is not falsely promoted unless it strongly qualifies on its own.

3. **Configurability**:
   - Introduce `DANGER_KEYWORD_LINKED_THRESHOLD=0.45` in `.env` so it can be easily adjusted by operators.

## Consequences

- **Cognitive Consistency**: Administrative users instantly see a direct, logical alignment between the overall document category and the highlighted keywords.
- **Explainability**: Keywords serve as intuitive evidence/justifications for the system's risk decisions.
- **Robust Safeguards**: Unrelated keywords will not be accidentally elevated, maintaining the strictness of the general safety classification.
