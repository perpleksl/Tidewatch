# Flow: from raw data to signal

Source: PRD.md 3.2–3.7; VISION.md (AI funnel); ARCHITECTURE.md Section 2 (AI).

```mermaid
flowchart TD
    A[New or updated token data] --> B{Chain + contract<br/>resolved?}
    B -- no --> B1[Excluded; logged as<br/>'unresolved' in System Health]
    B -- yes --> C{Meme<br/>classification}
    C -- meme --> C1[Excluded from all tabs<br/>visible in 'Show excluded memes']
    C -- unclassified --> C2[Held until classified]
    C -- not meme --> D{Hard stops<br/>security checks}
    D -- fails --> D1[Status 'Avoid'<br/>visible via 'Show avoided']
    D -- passes --> E[Code computes factors<br/>opportunity + risk]
    E --> F[Haiku triage<br/>worth a closer look?]
    F -- no --> G[Code-only scores]
    F -- yes, shortlist --> H[Sonnet deep dive<br/>judgment factors + rationale]
    H --> I[Final scores with breakdown]
    G --> I
    I --> J{Meets a tab's<br/>inclusion criteria?}
    J -- no --> K[Stored, not shown]
    J -- yes --> L[Signal created or updated<br/>in Mispriced / Narratives / Launches]
    L --> M[Lifecycle + 10:00 digest]
```

Budget guard: if AI spend reaches the monthly ceiling, step H pauses and tokens keep code-only scores (PRD 3.12).
