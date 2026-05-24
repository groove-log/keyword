# ADR-0003: Guideline Refinement and Safeguards Against Over-Association of Common Nouns

## Context & Problem

In ADR-0002, we introduced a Document-Linked relaxed threshold (`0.45`) to map dilution-prone nouns (like `"벌레"`) to the correct document category. However, this introduced a new side-effect:
- **Over-Association of Common Nouns**: Perfectly harmless, common nouns like `"매장"` (store) or `"불안"` (anxiety) are being flagged as danger categories (e.g., `"폭력 및 폭행"`) simply because their weak similarity score (`0.4898`) exceeds the relaxed `0.45` threshold.
- **Guideline Keyword Saturation**: The term `"매장"` was repeated multiple times in the `"폭력 및 폭행"` guideline as spatial background context, causing the embedding model to falsely associate the word in isolation with physical threat.
- **Implicit Threat Contexts**: Subtle verbal threats or psychological manipulation (e.g., isolating an employee, dragging them into a quiet space) were misclassified as `"폭력 및 폭행"` instead of `"성폭력"` due to a lack of explicit sexual vocabulary in the `"성폭력"` guideline description.

## Proposed Decisions

To solve both issues simultaneously, we decide on a two-pronged solution:

1. **Refining the NLP Guidelines (Solution A)**:
   - Rewrite `"성폭력"` guidelines to explicitly cover psychological coercion, physical isolation, gaslating, and non-explicit grooming/indecent approaches (e.g. pulling someone into a quiet, closed-off space).
   - Rewrite `"폭력 및 폭행"` guidelines to minimize spatial repetition of `"매장"`, focusing strictly on physical harm, equipment damage, and violent language.

2. **Implementing a Keyword Safeguard Minimum (Solution B)**:
   - Introduce a new environment variable `DANGER_KEYWORD_MIN_SAFEGUARD_SCORE=0.52`.
   - Even if the keyword's top category matches the document category, the relaxed linked threshold (`0.45`) is **only** allowed to trigger if the keyword's similarity score is greater than or equal to `DANGER_KEYWORD_MIN_SAFEGUARD_SCORE` (`0.52`).
   - This ensures that only words with a reasonable semantic signal (like `"벌레"` at `0.5540`) get mapped, while extremely diluted words (like `"매장"` at `0.4898` or `"불안"` at `0.4626`) are safely filtered out as `"정상"`.

## Consequences

- **High-Fidelity Classification**: Harmless spatial nouns like `"매장"` are protected and remain `"정상"`.
- **Explainable Evidence**: Only high-signal evidence keywords get mapped contextually.
- **Enhanced NLP Sensitivity**: The system correctly captures modern harassment, grooming, and implicit threats without requiring explicit profanities.
