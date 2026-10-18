# Infrastructure and environments

Source: ARCHITECTURE.md Sections 2, 7, 8.

```mermaid
flowchart TB
    subgraph GitHub
        PR[Pull request] --> CI[GitHub Actions<br/>lint · types · tests · e2e]
        CI -->|all green + Owner approval| Main[main branch]
    end

    PR -->|auto| Preview[Vercel preview<br/>dashboard per PR]

    Main -->|auto deploy| Staging
    Staging -->|Owner promotes| Production

    subgraph Staging
        SW[Vercel web] --- SA[Render API] --- SK[Render worker] --- SD[(Postgres)]
    end

    subgraph Production
        PWb[Vercel web] --- PA[Render API] --- PK[Render worker] --- PD[(Postgres)]
    end

    Secrets[[Secrets in Render + Vercel settings<br/>never in repo]] -.-> Staging & Production
```

**Rules**
- Agents work locally and through preview only. They never hold staging or production credentials.
- Each environment has its own database, API keys and Clerk instance.
- Staging digests carry a "[STAGING]" subject prefix.
