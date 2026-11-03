# Dashboard System Design

## Overview

This document describes the system architecture for the Dashboard application, including data flow, component interactions, and deployment topology.

## High-Level Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        Browser[Web Browser]
        Mobile[Mobile App]
    end

    subgraph "Edge Layer"
        CF[Cloudflare CDN]
        WAF[WAF / Bot Management]
        Turnstile[Turnstile Verification]
    end

    subgraph "Application Layer"
        Worker[Cloudflare Worker]
        Auth[Auth Service]
        API[API Gateway]
    end

    subgraph "Data Layer"
        D1[(D1 Database)]
        KV[(KV Store)]
        R2[(R2 Object Storage)]
        Queue[Queues]
    end

    subgraph "External Services"
        AI[Workers AI]
        Email[Email Service]
        Analytics[Analytics Engine]
    end

    Browser --> CF
    Mobile --> CF
    CF --> WAF
    WAF --> Turnstile
    Turnstile --> Worker
    Worker --> Auth
    Worker --> API
    API --> D1
    API --> KV
    API --> R2
    API --> Queue
    Worker --> AI
    Worker --> Email
    Worker --> Analytics
```

## Data Flow - Dashboard Load

```mermaid
sequenceDiagram
    participant U as User
    participant B as Browser
    participant CF as Cloudflare Edge
    participant W as Worker
    participant KV as KV Cache
    participant D1 as D1 Database
    participant Q as Queue

    U->>B: Navigate to /dashboard
    B->>CF: GET /dashboard
    CF->>W: Forward request
    W->>KV: Check cached layout
    alt Cache Hit
        KV-->>W: Return cached config
    else Cache Miss
        W->>D1: Query user preferences
        D1-->>W: Return preferences
        W->>KV: Cache layout config
    end
    W->>D1: Query dashboard widgets
    D1-->>W: Return widget data
    W->>Q: Enqueue analytics event
    W-->>B: Return HTML/JSON
    B-->>U: Render dashboard
```

## Widget Data Pipeline

```mermaid
graph LR
    subgraph "Data Sources"
        DS1[PostgreSQL]
        DS2[External API]
        DS3[Event Stream]
        DS4[File Upload]
    end

    subgraph "Ingestion"
        Prefect[Prefect Flows]
        Queue[Cloudflare Queues]
    end

    subgraph "Processing"
        Worker1[ETL Worker]
        Worker2[Transform Worker]
        Worker3[Aggregate Worker]
    end

    subgraph "Storage"
        D1[(D1 - Widget Data)]
        KV[(KV - Real-time)]
        R2[(R2 - Raw Files)]
    end

    subgraph "Serving"
        API[Dashboard API]
        WS[WebSocket Push]
    end

    DS1 --> Prefect
    DS2 --> Prefect
    DS3 --> Queue
    DS4 --> R2

    Prefect --> Queue
    Queue --> Worker1
    Worker1 --> Worker2
    Worker2 --> Worker3
    Worker3 --> D1
    Worker3 --> KV
    D1 --> API
    KV --> WS
    API --> WS
```

## Authentication & Authorization

```mermaid
stateDiagram-v2
    [*] --> Unauthenticated
    Unauthenticated --> Challenge: Turnstile
    Challenge --> Authenticated: Valid Token
    Challenge --> Unauthenticated: Failed
    Authenticated --> Authorized: Check Permissions
    Authorized --> Admin: Role = Admin
    Authorized --> User: Role = User
    Authorized --> Viewer: Role = Viewer
    Admin --> [*]: Full Access
    User --> [*]: Read/Write Own
    Viewer --> [*]: Read Only
    Authenticated --> Expired: Token Expired
    Expired --> Unauthenticated: Refresh Failed
    Expired --> Authenticated: Refresh Success
```

## Real-time Updates

```mermaid
graph TB
    subgraph "Server"
        DO["Durable Object<br/>Room: dashboard-{id}"]
        DOStorage[(DO Storage<br/>SQLite)]
        WSHandler[WebSocket Handler]
    end

    subgraph "Clients"
        C1[Client 1]
        C2[Client 2]
        C3[Client N]
    end

    subgraph "Events"
        Queue[Queues]
        Worker[Worker]
    end

    C1 <--> WSHandler
    C2 <--> WSHandler
    C3 <--> WSHandler
    WSHandler <--> DO
    DO <--> DOStorage
    Queue --> Worker
    Worker -->|Broadcast Update| DO
```

## Deployment Pipeline

```mermaid
graph LR
    subgraph "CI"
        Push[Git Push]
        Lint[Lint & Typecheck]
        Test[Unit Tests]
        Build[Build Assets]
    end

    subgraph "Staging"
        DeployS[Deploy Preview]
        Smoke[Smoke Tests]
        E2E[E2E Tests]
    end

    subgraph "Production"
        DeployP[Deploy Production]
        Canary[Canary Release]
        Monitor[Monitor Metrics]
        Rollback[Auto Rollback]
    end

    Push --> Lint
    Lint --> Test
    Test --> Build
    Build --> DeployS
    DeployS --> Smoke
    Smoke --> E2E
    E2E --> DeployP
    DeployP --> Canary
    Canary --> Monitor
    Monitor -->|Failure| Rollback
    Monitor -->|Success| Complete[Complete]
```

## Component Responsibilities

| Component | Responsibility | Technology |
|-----------|---------------|------------|
| Cloudflare Worker | Request routing, auth, API aggregation | TypeScript, Hono |
| Durable Objects | Real-time state, WebSocket coordination | TypeScript, SQLite |
| D1 Database | Persistent relational data | SQLite |
| KV Store | Cached configs, session data | Key-Value |
| R2 Storage | File uploads, exports | S3-compatible |
| Queues | Async processing, analytics | Message Queue |
| Workers AI | ML inference, embeddings | Llama, Embeddings |
| Prefect | Scheduled ETL, data pipelines | Python |

## Scaling Considerations

```mermaid
graph TD
    Load[Incoming Load] --> CF[Cloudflare Edge<br/>Auto-scales]
    CF --> Worker[Workers<br/>Per-request isolate]
    Worker --> DO[Durable Objects<br/>Per-room scaling]
    Worker --> D1[D1<br/>Read replicas]
    Worker --> KV[KV<br/>Global replication]
    Worker --> Queue[Queues<br/>Backpressure handling]

    style CF fill:#f9f,stroke:#333
    style Worker fill:#bbf,stroke:#333
    style DO fill:#bfb,stroke:#333
```

## Monitoring & Observability

```mermaid
graph LR
    subgraph "Metrics"
        WMetrics[Worker Metrics]
        DOMetrics[DO Metrics]
        D1Metrics[D1 Metrics]
        QMetrics[Queue Metrics]
    end

    subgraph "Logs"
        WLogs[Worker Logs]
        Tail[Tail Workers]
    end

    subgraph "Tracing"
        Trace[Distributed Traces]
    end

    subgraph "Alerting"
        Alert[Alert Rules]
        Pager[PagerDuty / Slack]
    end

    WMetrics --> Alert
    DOMetrics --> Alert
    D1Metrics --> Alert
    QMetrics --> Alert
    WLogs --> Tail
    Tail --> Trace
    Trace --> Alert
    Alert --> Pager
```

## Security Boundaries

```mermaid
graph TB
    subgraph "Public Internet"
        Attacker[🌐 Attacker]
        User[👤 User]
    end

    subgraph "DMZ - Cloudflare Edge"
        WAF[WAF Rules]
        RateLimit[Rate Limiting]
        BotMgmt[Bot Management]
    end

    subgraph "Application Zone"
        Worker[Worker<br/>Zero Trust]
        Auth[Auth Validation]
    end

    subgraph "Data Zone"
        D1[(D1<br/>Private Network)]
        KV[(KV<br/>Encrypted)]
        R2[(R2<br/>Signed URLs)]
    end

    User --> WAF
    Attacker -.->|Blocked| WAF
    WAF --> RateLimit
    RateLimit --> BotMgmt
    BotMgmt --> Worker
    Worker --> Auth
    Auth --> D1
    Auth --> KV
    Auth --> R2
```

## Environment Configuration

```mermaid
graph LR
    subgraph "Development"
        DevWorker[Worker Dev]
        DevD1[D1 Local]
        DevKV[KV Local]
    end

    subgraph "Staging"
        StagingWorker[Worker Preview]
        StagingD1[D1 Staging]
        StagingKV[KV Staging]
    end

    subgraph "Production"
        ProdWorker[Worker Prod]
        ProdD1[D1 Prod]
        ProdKV[KV Prod]
    end

    DevWorker --> DevD1
    DevWorker --> DevKV
    StagingWorker --> StagingD1
    StagingWorker --> StagingKV
    ProdWorker --> ProdD1
    ProdWorker --> ProdKV
```

---

*Generated with Mermaid.js - View in any Markdown renderer with Mermaid support (GitHub, GitLab, VS Code, Notion, Obsidian)*