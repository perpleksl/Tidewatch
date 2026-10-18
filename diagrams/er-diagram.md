# Entity-relationship diagram

Source: ARCHITECTURE.md Section 4; PRD.md 3.2–3.13.

```mermaid
erDiagram
    TOKEN ||--o{ TOKEN_ALIAS : "has"
    TOKEN ||--o{ MARKET_SNAPSHOT : "has"
    TOKEN ||--o{ FUNDAMENTAL_SNAPSHOT : "has"
    TOKEN ||--o{ WALLET_ACTIVITY : "has"
    TOKEN ||--o{ SECURITY_CHECK : "has"
    TOKEN ||--o{ SCORE : "has"
    TOKEN ||--o{ SIGNAL : "has"
    TOKEN ||--o{ NARRATIVE_MEMBER : "belongs to"
    NARRATIVE ||--o{ NARRATIVE_MEMBER : "contains"
    SIGNAL ||--o{ SIGNAL_EVENT : "logs"
    SIGNAL ||--o| OWNER_LABEL : "may have"
    SIGNAL }o--|| SCORE : "first-flag scores"
    X_ACCOUNT ||--o{ SOCIAL_POST : "posts"
    SOCIAL_POST }o--o{ TOKEN : "mentions"
    SOCIAL_POST }o--o{ NARRATIVE : "mentions"
    SETTING ||--o{ SETTING_CHANGE : "logs"
    BACKTEST_RUN ||--o{ BACKTEST_RESULT : "produces"
    BACKTEST_RESULT }o--o| REFERENCE_CASE : "evaluates"
    REFERENCE_CASE }o--|| TOKEN : "is"

    TOKEN {
        uuid id
        string chain
        string contract_address "null for native coins"
        string name
        string ticker "display only, never an identifier"
        string meme_class "meme | not_meme | unclassified"
        bool meme_override
    }
    MARKET_SNAPSHOT {
        decimal price
        decimal market_cap
        decimal fdv
        decimal liquidity
        int holders
        string source
        timestamp observed_at
        timestamp available_at "point-in-time rule"
    }
    FUNDAMENTAL_SNAPSHOT {
        decimal revenue
        decimal fees
        decimal tvl
        decimal hashrate
        int miners
        decimal emissions_per_month
        string source
        timestamp available_at
    }
    SCORE {
        int opportunity "0-100"
        int risk "0-100"
        json factor_breakdown
        json inputs
        timestamp scored_at
    }
    SIGNAL {
        string tab "mispriced | narratives | launches"
        timestamp first_flag_at
        decimal first_flag_price
        string state
        uuid previous_signal_id
    }
    SIGNAL_EVENT {
        string from_state
        string to_state
        decimal price
        string reason
        timestamp at
    }
    NARRATIVE {
        string name
        string status "seed | proposed | accepted | rejected"
        int momentum
    }
    X_ACCOUNT {
        string handle
        string label
        decimal early_call_score
    }
    SETTING {
        string key
        json value
        json default_value
    }
    COST_ENTRY {
        string source
        decimal amount_usd
        timestamp at
    }
    DIGEST_LOG {
        timestamp sent_at
        string status
    }
```

`COST_ENTRY` and `DIGEST_LOG` stand alone; they are referenced only by System Health (PRD 3.12).
