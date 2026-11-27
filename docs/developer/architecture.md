# Architecture and data model

28 November 2026 · Release evidence for GOV-04 and AT-20 · Drawn from the code on the release-candidate branch

This page shows the system as built. The planning diagrams in the
[master plan](../implementation/MASTER_PLAN.md) and the
[contracts](../implementation/CONTRACTS.md) record the design. Where they
differ, the code and this page win. Design decisions are in the
[ADRs](../adr/).

## Components

```mermaid
flowchart LR
    client["MCP client<br/>(Codex Desktop, Claude Code)"]
    subgraph server["yt_intel (local Python 3.13 process, stdio)"]
        mcp["mcp/<br/>tool and resource handlers"]
        services["services/<br/>discovery, recommendations, planning,<br/>library, analysis, workflows,<br/>creation, recovery"]
        domain["domain/ and analytics/<br/>pure ranking, profiles, constraints,<br/>proposals, summaries, periods"]
        presentation["presentation/<br/>escaped text previews and reports"]
        approval["approval/<br/>native dialog helper and grants"]
        auth["auth/<br/>OAuth, account lifecycle, vault"]
        providers["providers/<br/>YouTube read and write adapters,<br/>fixture dispatch"]
        http["infrastructure/http.py<br/>allowlisted, quota-accounted executor"]
        quota["infrastructure/quota.py<br/>persistent ledger"]
        db[("SQLite<br/>per-user app data")]
    end
    vault[("OS-protected vault<br/>Windows Credential Manager")]
    dialog["Native approval dialog<br/>(human only)"]
    google["Official YouTube Data API v3<br/>and Google OAuth"]
    cli["yt-intel CLI<br/>auth / disconnect / serve"]

    client -- "JSON-RPC over stdio" --> mcp
    mcp --> services
    services --> domain
    services --> presentation
    services --> approval
    approval --> dialog
    services --> providers
    services --> auth
    providers --> http
    auth --> http
    http --> quota
    quota --> db
    services --> db
    auth --> vault
    http -- "HTTPS, exact route allowlist" --> google
    cli --> auth
    cli --> mcp
```

- **Pure core.** `domain/` and `analytics/` have no I/O.
- **One network path.** Only `AccountedHttpExecutor` reaches the network.
  It debits the ledger before every attempt.
- **Fixture mode.** The fixture provider puts an `httpx.MockTransport` behind
  the same executor. Fixture runs therefore exercise the real accounting,
  retry and error-translation code.
- **Approval.** Approval grants are created only from the native dialog's
  decision, and only inside the server.

## Composed video-to-playlist workflow

```mermaid
sequenceDiagram
    participant C as MCP client
    participant S as Server handlers
    participant L as Quota ledger
    participant P as Provider via executor
    participant H as Native dialog (human)
    participant D as SQLite
    C->>S: begin_workflow(video)
    S->>L: reserve worst case for every stage
    L-->>S: reservation or QUOTA_INSUFFICIENT (zero calls)
    C->>S: get_video, find_similar_videos (workflow_id)
    S->>P: reads inside the reservation
    S->>D: candidate set
    C->>S: propose_playlist(candidate_set_id, constraints)
    S->>D: immutable proposal v1 and digest
    S-->>C: exact preview and resource link
    C->>S: prepare_creation(proposal ref)
    S->>D: operation intent and cost
    C->>S: create_playlist(operation_id)
    S->>H: show the complete stored proposal
    H-->>S: approve or reject
    S->>S: grant bound to account, digest, version and operation (10 min, one use)
    S->>P: playlists.insert, then playlistItems.insert (one attempt each)
    S->>D: remote IDs and per-item outcome before the next item
    S-->>C: completed, partial, unknown or rejected
    S->>L: release unused capacity
```

## Data model

These tables come from the migrations in
[`database.py`](../../src/yt_intel/infrastructure/database.py).
`payload` columns hold validated contract JSON.

```mermaid
erDiagram
    accounts ||--o{ snapshots : owns
    accounts ||--o{ proposals : owns
    accounts ||--o{ cache_entries : owns
    accounts ||--o{ operations : owns
    accounts |o--o{ quota_reservations : "binding (set null on delete)"
    quota_reservations ||--o{ quota_endpoint_ceilings : bounds
    quota_reservations ||--o{ quota_reservation_buckets : reserves
    quota_reservations ||--o{ quota_attempts : records
    quota_reservations ||--o{ quota_calls : records
    fixture_remote_playlists ||--o{ fixture_remote_items : contains

    accounts {
        text binding_key PK
        text installation_id
        text credential_binding_id
        text channel_id
        text mode "fixture or live"
    }
    snapshots {
        text snapshot_id PK
        text binding_key FK
        text fetched_at
        text retained_until "30-day ceiling"
        text payload
    }
    proposals {
        text proposal_id PK
        int version PK
        text binding_key FK
        text digest
        text state
        text expires_at "10 minutes"
        text retained_until
        text payload
    }
    cache_entries {
        text binding_key PK
        text cache_key PK
        text expires_at "24-hour TTL"
        text retained_until
        blob payload
    }
    operations {
        text operation_id PK
        text binding_key FK
        text digest
        text state
        int revision
        text retained_until
        text payload
    }
    operation_tombstones {
        text operation_id PK
        text digest
        text expired_at
        text status
    }
    quota_project_profiles {
        text project_id PK
        text reference_date
        text profile_digest
    }
    quota_reservations {
        text reservation_id PK
        text project_id
        text quota_day "Pacific day"
        text deadline
        text binding_key FK
        int released
    }
    quota_endpoint_ceilings {
        text reservation_id PK
        text endpoint PK
        int attempts
        int calls
        int attempts_per_call
    }
    quota_reservation_buckets {
        text reservation_id PK
        text bucket PK
        int remaining
        int spent
    }
    quota_attempts {
        text reservation_id PK
        text attempt_id PK
        text endpoint
    }
    quota_calls {
        text reservation_id PK
        text call_id PK
        text endpoint
        int attempts
    }
    quota_exhausted_buckets {
        text project_id PK
        text quota_day PK
        text bucket PK
    }
    fixture_remote_playlists {
        text playlist_id PK
        text channel_id
        text body
    }
    fixture_remote_items {
        text playlist_id PK
        int position PK
        text payload
    }
```

- **Disconnect.** Deleting an `accounts` row cascades to its snapshots,
  proposals, cache entries and operations.
- **What survives disconnect.** Quota reservations keep their spend, with
  `binding_key` set to null. `operation_tombstones` also stay, so
  disconnecting cannot restore quota or allow a replay.
- **Fixture-only tables.** `fixture_remote_*` holds the simulated remote
  playlists for fixture runs only.
- **Secrets.** Tokens never appear in any table. They live only in the OS
  vault.
