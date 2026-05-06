Vendor Data

{
"vendor_id": "VEND-001",
"name": "Apex Office Solutions",
"categories": ["ergonomic_seating", "workstations_desks"],

"performance": {
"rating": 4.3,
"on_time_delivery_rate": 0.94,
"total_orders_completed": 47
},

"compliance": {
"risk_rating": "low",
"certifications": ["BIFMA", "ISO_9001"],
"esg_certified": true
},

"negotiation_persona": {
"pricing_flexibility": "low",
"max_discount_pct": 8,
"style": "premium_quality_focused"
},

"payment_terms_offered": ["NET30", "NET45"],
"typical_lead_time_days": 14,
"a2a_endpoint": "https://procureiq.run.app/vendors/VEND-001/a2a"
}

Purchase Request

{
"request_id": "PR-2026-04-0042",
"created_at": "2026-04-27T10:30:00Z",
"requestor": "Priya Sharma",

"item": {
"category": "ergonomic_seating",
"description": "Ergonomic office chairs with lumbar support and adjustable armrests",
"quantity": 50,
"specifications": {
"warranty_min_years": 3,
"required_certifications": ["BIFMA"]
}
},

"budget": {
"target_unit_price": 280,
"max_unit_price": 320,
"currency": "USD"
},

"delivery": {
"required_by_date": "2026-05-25",
"city": "Bangalore"
},

"compliance_requirements": {
"esg_certified_required": true,
"max_acceptable_risk_rating": "medium"
}
}

Quote
{
"quote_id": "QT-VEND-001-PR-0042-R1",
"rfq_id": "PR-2026-04-0042",
"vendor_id": "VEND-001",
"round": 1,
"submitted_at": "2026-04-27T10:35:42Z",

"pricing": {
"unit_price": 295,
"quantity": 50,
"total": 14750,
"currency": "USD"
},

"terms": {
"delivery_days": 14,
"payment_terms": "NET30",
"warranty_years": 3
},

"vendor_notes": "Premium ergonomic line; 50-unit volume includes free installation",

"compliance_check": {
"passed": true,
"issues": []
}
}

Purchase Order

{
"po_id": "PO-2026-04-1087",
"request_id": "PR-2026-04-0042",
"vendor_id": "VEND-001",
"winning_quote_id": "QT-VEND-001-PR-0042-R3",
"status": "issued",
"created_at": "2026-04-27T10:42:00Z",

"line_item": {
"description": "Ergonomic office chairs with lumbar support",
"quantity": 50,
"unit_price": 275,
"total": 13750,
"currency": "USD"
},

"terms": {
"delivery_by": "2026-05-11",
"payment_terms": "NET30",
"warranty_years": 3
},

"delivery_address": "Bangalore",

"negotiation_summary": {
"initial_quote": 295,
"final_price": 275,
"savings_per_unit": 20,
"rounds": 2
}
}

Goods Receipt Note (GRN)
{
"grn_id": "GRN-2026-05-0445",
"po_id": "PO-2026-04-1087",
"received_at": "2026-05-10T14:30:00Z",
"received_quantity": 50,
"accepted_quantity": 49,
"rejected_quantity": 1,
"rejection_reason": "1 unit damaged in transit"
}

Invoice

{
"invoice_id": "INV-VEND-001-1247",
"po_id": "PO-2026-04-1087",
"vendor_id": "VEND-001",
"submitted_at": "2026-05-12T09:15:00Z",
"attempt": 1,

"line_item": {
"description": "Ergonomic office chairs",
"quantity": 49,
"unit_price": 275,
"total": 13475,
"currency": "USD"
},

"payment_terms": "NET30",
"payment_due_date": "2026-06-11",

"verification_status": "pending"
}

Verification Result

{
"verification_id": "VER-INV-1247-A1",
"invoice_id": "INV-VEND-001-1247",
"po_id": "PO-2026-04-1087",
"verified_at": "2026-05-12T09:18:00Z",
"status": "kicked_back",

"checks": {
"po_match": "passed",
"grn_quantity_match": "failed",
"price_match": "passed",
"total_arithmetic": "passed",
"payment_terms_match": "passed"
},

"discrepancies": [
{
"field": "quantity",
"invoice_value": 50,
"expected_value": 49,
"explanation": "GRN shows 1 unit rejected; please revise invoice quantity to 49"
}
]
}

Workflow State (Session)

{
"workflow_id": "WF-2026-04-1042",
"request_id": "PR-2026-04-0042",
"status": "negotiating", // initiated, searching_vendors, negotiating, deciding, awaiting_acknowledgment, awaiting_invoice, verifying, completed, escalated
"started_at": "2026-04-27T10:30:00Z",

"current_phase": "negotiation_round_2",
"shortlisted_vendor_ids": ["VEND-001", "VEND-002", "VEND-003"],
"vetoed_vendor_ids": ["VEND-002"],

"active_negotiations": [
{
"vendor_id": "VEND-001",
"current_round": 2,
"latest_quote_id": "QT-VEND-001-PR-0042-R2",
"status": "active"
},
{
"vendor_id": "VEND-003",
"current_round": 2,
"latest_quote_id": "QT-VEND-003-PR-0042-R2",
"status": "active"
}
],

"po_id": null,
"audit_events": []
}

Audit Event
{
"event_id": "EVT-2026-04-1042-007",
"workflow_id": "WF-2026-04-1042",
"timestamp": "2026-04-27T10:33:18Z",
"agent": "compliance_agent",
"event_type": "compliance_violation",
"summary": "Vendor VEND-002 vetoed: ESG certification required but vendor not certified",
"data": {
"vendor_id": "VEND-002",
"violation": "esg_certification_missing"
}
}

CATEGORIES = { # Office & Workplace
"ergonomic_seating": {
"parent": "office_workplace",
"display_name": "Ergonomic Seating",
"required_certifications": ["BIFMA"],
"typical_lead_time_days": 14,
"typical_savings_pct": 6.5
},
"workstations_desks": {
"parent": "office_workplace",
"display_name": "Workstations & Desks",
"required_certifications": ["BIFMA"],
"typical_lead_time_days": 21,
"typical_savings_pct": 5.0
},
"office_supplies": {
"parent": "office_workplace",
"display_name": "Office Supplies & Stationery",
"required_certifications": [],
"typical_lead_time_days": 5,
"typical_savings_pct": 8.0
},

    # IT & Technology
    "laptops_workstations": {
        "parent": "it_technology",
        "display_name": "Laptops & Workstations",
        "required_certifications": ["ENERGY_STAR"],
        "typical_lead_time_days": 10,
        "typical_savings_pct": 4.0
    },
    "networking_equipment": {
        "parent": "it_technology",
        "display_name": "Networking Equipment",
        "required_certifications": ["ENERGY_STAR"],
        "typical_lead_time_days": 14,
        "typical_savings_pct": 5.5
    },
    "software_saas": {
        "parent": "it_technology",
        "display_name": "Software & SaaS Licenses",
        "required_certifications": ["SOC2"],
        "typical_lead_time_days": 3,
        "typical_savings_pct": 12.0
    },

    # Professional Services
    "consulting_services": {
        "parent": "professional_services",
        "display_name": "Consulting Services",
        "required_certifications": [],
        "typical_lead_time_days": 7,
        "typical_savings_pct": 10.0
    },
    "marketing_services": {
        "parent": "professional_services",
        "display_name": "Marketing & Creative Services",
        "required_certifications": [],
        "typical_lead_time_days": 7,
        "typical_savings_pct": 8.5
    },

    # Facilities & Operations
    "cleaning_janitorial": {
        "parent": "facilities_operations",
        "display_name": "Cleaning & Janitorial",
        "required_certifications": ["ISO_14001"],
        "typical_lead_time_days": 7,
        "typical_savings_pct": 7.0
    },
    "security_services": {
        "parent": "facilities_operations",
        "display_name": "Security Services",
        "required_certifications": [],
        "typical_lead_time_days": 14,
        "typical_savings_pct": 5.5
    }

}

PARENT_CATEGORIES = {
"office_workplace": "Office & Workplace",
"it_technology": "IT & Technology",
"professional_services": "Professional Services",
"facilities_operations": "Facilities & Operations"
}
