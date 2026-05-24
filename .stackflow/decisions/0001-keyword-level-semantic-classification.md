# ADR-0001: Keyword-Level Semantic Classification and Enhanced Danger Guidelines

## Context & Problem

The user has defined five distinct danger guidelines (폭력 및 폭행, 성폭력, 이물질 상품, 안전사고, 법적 이슈) via `keyword.md`. 
Additionally, they want to analyze not just the entire counseling text as a single context, but also **individual extracted keywords** to determine which specific danger category they map to, and report this in both the API response and the visual web dashboard.

## Proposed Decisions

1. **Update Danger Guidelines**:
   Replace the default 4 danger categories with the newly provided 5 categories defined in `keyword.md`:
   - `폭력 및 폭행 (물리적 위협 및 난동)`
   - `성폭력 (언어적 성희롱 및 실제 성범죄)`
   - `이물질 상품 (식품 및 취급 상품 오염)`
   - `안전사고 (매장 내외부 시설 관련 상해)`
   - `법적 이슈 (고소, 고발 및 외부 기관 민원)`

2. **Keyword-Level Classification**:
   Extend the keyword extraction flow to calculate cosine similarity for *each individual recommended keyword* against the five category embeddings.
   - If a keyword's maximum similarity score exceeds the threshold (`DANGER_THRESHOLD`, e.g., `0.60`), map that keyword to the matching category.
   - If it doesn't exceed the threshold, the keyword is mapped as `"정상"`.

3. **Database Schema Extension**:
   - In PostgreSQL, the `keywords` column currently stores a comma-separated string (e.g. `"환불 조치, 환불, 배송"`).
   - To capture the mapping, we will store keywords and their mapped danger classifications as a JSON structure in the database (or serialize a structured string if we want to preserve backwards compatibility). 
   - A highly robust way to keep backward compatibility while offering structured metadata is to save the structured data as a JSON string, or append mapped categories: `키워드 (카테고리명:유사도)` 형태로 포맷팅하여 저장할 수 있습니다. 
   - To deliver the absolute best visual representation, we will update the JSON API outputs so that the UI can parse each keyword's specific classification, while maintaining simple text rendering for general logs.

4. **UI Adaptation**:
   - Render the mapped danger category right next to each keyword card in the visual layout using modern, glassmorphic labels.

## Consequences

- Increased HTTP requests to the embedding server during synchronous API calls (since each of the `top_n` keywords requires an embedding fetch). However, since `llama.cpp` handles fast CPU/GPU embedding queries under ~10-30ms, the overall synchronous overhead remains minimal.
- Highly granular risk identification: Administrators can instantly see *why* a customer inquiry was flagged (e.g., flagging "고소장" as "법적 이슈" and "식중독" as "이물질 상품").
