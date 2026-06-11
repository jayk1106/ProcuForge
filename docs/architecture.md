# ProcuForge — End-to-End Architecture

```mermaid
flowchart TB

    BO["Buyer Organization"]
    FE["Next.js Frontend"]
    API["FastAPI Backend on Cloud Run"]

    subgraph BMA["Buyer Multi-Agent System"]
        B1["Vendor Search Agent"]
        B2["Negotiator Agent"]
        B3["Decision Agent"]
        B4["Purchase Manager Agent"]
        B5["Workflow QA Agent"]
    end

    subgraph A2A["A2A Procurement Protocol"]
        M1["RFQ"]
        M2["Quote"]
        M3["Counter Offer"]
        M4["Purchase Order"]
        M5["GRN"]
        M6["Invoice"]
    end

    subgraph VMA["Vendor Multi-Agent System"]
        V1["Quote Agent"]
        V2["Negotiation Agent"]
        V3["Purchase Agent"]
    end

    VO["Vendor Organizations"]

    subgraph SES["Session Storage"]
        AE["Vertex AI Agent Engine"]
    end

    subgraph DAT["Data Layer"]
        FS["Firestore"]
    end

    subgraph AIL["AI Layer"]
        GEM["Vertex AI / Gemini 2.5 Flash"]
    end

    subgraph MCP["MCP Layer"]
        ML["Mailgun Escalation Mails"]
    end

    BO --> FE
    FE --> API
    API --> BMA
    BMA <--> A2A
    A2A <--> VMA
    VO --> VMA

    BMA --> SES
    VMA --> SES
    BMA --> DAT
    VMA --> DAT
    BMA --> AIL
    VMA --> AIL
    BMA --> MCP
```

## Flow

A buyer creates a procurement request through the Next.js frontend, which hits the FastAPI backend on Cloud Run. The Buyer Multi-Agent System takes over: **Vendor Search** shortlists suppliers, **Negotiator** runs A2A conversations with each, **Decision** picks the winner, and **Purchase Manager** drives the PO → GRN → invoice cycle. The Vendor Multi-Agent System replies through the same A2A protocol with its **Quote**, **Negotiation**, and **Purchase** agents. Both systems share Firestore for business data, Vertex AI Agent Engine for session state, and Vertex AI Gemini 2.5 Flash for inference. When negotiations stall or thresholds are breached, the buyer system pushes an escalation through the MCP layer to deliver emails via Mailgun.
