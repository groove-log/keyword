# ADR-0005: 3D Multi-Label Co-occurrence and Action Triage Engine

## Status
Approved

## Context
Our existing 2D safety matrix architecture successfully isolates physical incident threats (Danger Issues) from social/pressure intentions (External Issues). However, in real-world complaints, two key limitations remain:
1. **Single-Label Restriction**: A customer complaint often contains multiple co-occurring risks (e.g., both `"이물질 상품"` and `"안전사고"` if a foreign object caused a broken tooth and emergency room visit). The current single-label `argmax` logic selects only the highest score, masking other critical risks.
2. **Missing Action SLA Velocity**: The urgency of two identical 2D classifications can vary drastically based on timeline context (e.g., "currently hospitalized in the ER and reporting to media tonight" vs "considering legal action in the future"). There is no formal third dimension measuring escalation velocity (Golden Time) to automate internal alert routing SLAs.

To resolve these, the user approved expanding the 2D matrix into a **3D Multi-Label Co-occurrence and Action Triage Engine**.

## Decision
We will implement the following architectural enhancements:

### 1. Z-Axis: Golden Time & Urgency Classification
- We will define a new dimension, the **Z-Axis (Urgency Level)**, with three states:
  - `IMMEDIATE`: Demands immediate intervention (< 6-hour SLA). Triggered by words like `"당장"`, `"오늘"`, `"즉시"`, `"실시간"`, `"지금"`, `"응급실"`.
  - `SHORT-TERM`: Action required within 48 hours. Triggered by words like `"이번주"`, `"이번 주"`, `"조만간"`, `"며칠"`, `"기한"`, `"데드라인"`.
  - `MONITOR`: Standard monitoring. Default state.
- Urgency will be computed deterministically using a Kiwi-assisted lexicon scanning pipeline on Python memory to keep overhead at zero.

### 2. Multi-Label Co-occurrence Analysis
- We will refactor `classify_danger` and `classify_external` to return lists of all categories that pass their lexicon-relaxed active thresholds:
  - Instead of returning `max(scores, key=scores.get)`, the classifier will yield a sorted list of all active categories (e.g., `["이물질 상품", "안전사고"]`).
  - If no categories pass their active thresholds, it defaults to `["정상 문의"]`.
- In the database, these co-occurring labels will be persisted as comma-separated values (e.g., `"이물질 상품, 안전사고"`). Columns `risk_level` and `external_issue` will be expanded to `VARCHAR(100)` to prevent truncation.

### 3. Integrated Action Triage & Alert Router
- An automatic **Action Triage Router** will calculate the overall crisis level:
  - **🚨 Level 1 (RED ALERT)**: Urgency is `IMMEDIATE` AND at least one Danger AND one External category are active (`ON`). Action: Automated TF team alert, CEO/Executive SMS dispatch, and instant Legal/PR routing.
  - **⚠️ Level 2 (AMBER ALERT)**: Urgency is `SHORT-TERM` AND at least one risk category is active. Action: 24h CS Manager ticketing routing.
  - **🟢 Level 3 (GREEN ALERT)**: Standard monitoring. Action: Regular CRM logging.

### 4. Database Migration
- Add `urgency_level` VARCHAR(50) NOT NULL DEFAULT 'MONITOR' column to `counseling_data`.
- Update `schema.sql` and migration scripts to automate this column creation.

### 5. UI Coherence & Triage Badges
- Modify the dashboard to split comma-separated labels and render **multi-tag glowing badges** side-by-side.
- Add visual indicators for the overall **Action Crisis Level (RED, AMBER, GREEN)** and dynamic dispatch routing destinations.

## Consequences
- **Zero Risk Signal Loss**: Co-occurring risks are fully captured, ending the "signal override" limitation.
- **Workflow Automation Ready**: The addition of the Z-Axis SLA enables the prototype to simulate direct enterprise-level auto-dispatching (Auto-Triage).
- **100% Backward Compatibility**: Comma-separated strings split perfectly on single-label legacy rows, ensuring zero database migration friction.
