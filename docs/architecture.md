# ProcuForge — End-to-End Architecture

![ProcuForge architecture](./diagram.png)

```mermaid
flowchart TB
    Buyer["👤 Buyer Organization<br/>Creates Purchase Request"]
    Frontend["🖥️ Next.js Frontend"]
    Backend["⚙️ FastAPI Backend<br/>on Cloud Run"]
    Vendors["🏭 Independent Vendors"]

    Buyer --> Frontend --> Backend

    subgraph BuyerMAS["Buyer Multi-Agent System"]
        direction TB
        VSA["🔍 Vendor Search Agent<br/>Finds & shortlists best-fit vendors"]
        NA["💬 Negotiator Agent<br/>Runs A2A negotiations"]
        DA["⚖️ Decision Agent<br/>Selects optimal vendor"]
        PMA["📦 Purchase Manager Agent<br/>Drives PO → GRN → Invoice"]
        QA["✅ Workflow QA Agent<br/>Validates & enforces policy"]
    end

    subgraph A2A["Agent-to-Agent Procurement Protocol"]
        direction LR
        M1["RFQ"] --- M2["QUOTE"] --- M3["COUNTER_OFFER"] --- M4["PURCHASE_ORDER"] --- M5["GRN"] --- M6["INVOICE"]
    end

    subgraph VendorMAS["Vendor Multi-Agent System"]
        direction TB
        QtA["💰 Quote Agent<br/>Generates competitive quotes"]
        VNA["🤝 Negotiation Agent<br/>Negotiates price, terms, lead time"]
        VPA["📋 Purchase Agent<br/>Confirms orders & fulfillment"]
    end

    Backend --> BuyerMAS
    BuyerMAS <--> A2A
    A2A <--> VendorMAS
    VendorMAS <--> Vendors

    subgraph Lifecycle["Procurement Execution Lifecycle"]
        direction LR
        L1["📄 Purchase Order Issued"] --> L2["📥 Goods Receipt"] --> L3["🧾 Invoice Verification"] --> L4["🎯 Completed Procurement Cycle"]
    end

    PMA -.-> Lifecycle

    subgraph Foundation["Platform Foundation"]
        direction LR
        F1["✨ Vertex AI / Gemini 2.5 Flash<br/>Reasoning & generation"]
        F2["🧠 Vertex AI Agent Engine<br/>Sessions, state, memory"]
        F3["🗄️ Firestore<br/>Business data & audit trails"]
    end

    BuyerMAS -.-> Foundation
    VendorMAS -.-> Foundation

    classDef buyerStyle fill:#e3f2fd,stroke:#1976d2,color:#000
    classDef vendorStyle fill:#fff3e0,stroke:#f57c00,color:#000
    classDef protocolStyle fill:#f3e5f5,stroke:#7b1fa2,color:#000
    classDef lifecycleStyle fill:#e8f5e9,stroke:#388e3c,color:#000
    classDef foundationStyle fill:#fce4ec,stroke:#c2185b,color:#000

    class VSA,NA,DA,PMA,QA buyerStyle
    class QtA,VNA,VPA vendorStyle
    class M1,M2,M3,M4,M5,M6 protocolStyle
    class L1,L2,L3,L4 lifecycleStyle
    class F1,F2,F3 foundationStyle
```

## Flow

A buyer creates a procurement request through the **Next.js frontend**, which hits the **FastAPI backend on Cloud Run**. The **Buyer Multi-Agent System** takes over:

- **Vendor Search Agent** — finds and shortlists best-fit vendors based on requirements and history.
- **Negotiator Agent** — conducts A2A negotiations with each shortlisted vendor to get the best terms and pricing.
- **Decision Agent** — evaluates offers and selects the optimal vendor.
- **Purchase Manager Agent** — drives the PO → GRN → Invoice execution cycle.
- **Workflow QA Agent** — validates each step and ensures policy compliance.

Buyer and vendor sides communicate over the **Agent-to-Agent Procurement Protocol** with six message types: `RFQ`, `QUOTE`, `COUNTER_OFFER`, `PURCHASE_ORDER`, `GRN`, and `INVOICE`. See [`buyer_vendor_communication_reference.md`](./buyer_vendor_communication_reference.md) for the schema.

The **Vendor Multi-Agent System** responds through the same protocol:

- **Quote Agent** — generates competitive quotes based on catalog, inventory, and capacity.
- **Negotiation Agent** — negotiates terms, pricing, lead times, and other conditions.
- **Purchase Agent** — confirms orders, schedules fulfillment, and prepares for delivery.

The **Procurement Execution Lifecycle** runs Purchase Order Issued → Goods Receipt → Invoice Verification → Completed Procurement Cycle.

## Platform foundation

| Layer | Service |
|---|---|
| Reasoning / generation | **Vertex AI / Gemini 2.5 Flash** powers reasoning and generation across all agents. |
| Agent runtime | **Vertex AI Agent Engine** manages agent sessions, state, memory, and long-running conversations. |
| Data | **Firestore** stores all business data — vendors, products, requests, POs, invoices, and audit trails. |
