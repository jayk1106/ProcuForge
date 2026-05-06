Collections

1. Category
2. Products
3. Organisation
4. Users
5. Vendors
6. VendorProduct
7. VendorOrgRelations
8. Requisitions
   - inside all the information
   1. Requisitions basic information
   2. current worflow state
   3. negotiations info
   4. purchase order , GRN, invoice related info

Categories

{
"id": "cat_it",

"name": "IT & Electronics",

"description": "Technology related products",

"icon": "laptop",

"active": true,

"metadata": {
"createdAt": "timestamp",
"updatedAt": "timestamp"
}
}

Products

{
"id": "prod_dell_5440",

"categoryId": "cat_it",

"name": "Dell Latitude 5440",

"brand": "Dell",

"type": "physical",

"description": "14-inch business laptop",

"specifications": {
"cpu": "Intel i7",
"ram": "16GB",
"storage": "512GB SSD",
"screenSize": "14 inch"
},

"unitOfMeasure": "piece",

"estimatedPriceRange": {
"currency": "USD",
"min": 950,
"max": 1200
},

"aliases": [
"dell business laptop"
],

"active": true,

"metadata": {
"createdAt": "timestamp",
"updatedAt": "timestamp"
}
}

Organizations

{
"id": "org_001",

"name": "Acme Technologies",

"size": "200-500",

"currency": "USD",

"settings": {
"approvalRequired": true,
"multiVendorQuotesRequired": true,
"defaultPaymentTerms": "Net 30"
},

"address": {
"country": "USA",
"state": "California",
"city": "San Francisco"
},

"active": true,

"metadata": {
"createdAt": "timestamp",
"updatedAt": "timestamp"
}
}

Users

{
"id": "user_001",

"organizationId": "org_001",

"name": "Jay Kaneriya",

"email": "jay@company.com",

"role": "procurement_manager",

"active": true,

"metadata": {
"createdAt": "timestamp",
"updatedAt": "timestamp"
}
}

Vendors

{
"id": "vendor_cdw",

"name": "CDW",

"categories": [
"cat_it"
],

"contact": {
"email": "sales@cdw.com",
"phone": "+1-111-222-3333",
"website": "https://cdw.com"
},

"address": {
"country": "USA",
"state": "Illinois",
"city": "Chicago"
},

"paymentTerms": "Net 30",

"active": true,

"metadata": {
"createdAt": "timestamp",
"updatedAt": "timestamp"
}
}

VendorProducts
{
"id": "vp_001",

"vendorId": "vendor_cdw",

"productId": "prod_dell_5440",

"vendorSku": "DLL5440-I7",

"pricing": {
"currency": "USD",
"unitPrice": 1099,
"minimumOrderQty": 1
},

"leadTimeDays": 5,

"contracted": true,

"availabilityStatus": "in_stock",

"active": true,

"metadata": {
"updatedAt": "timestamp"
}
}

VendorOrgRelations
{
"id": "rel_001",

"organizationId": "org_001",

"vendorId": "vendor_cdw",

"relationshipStatus": "active",

"relationshipStrength": 8.7,

"preferredVendor": true,

"strategicVendor": false,

"metrics": {
"totalOrders": 48,
"totalSpend": 380000,
"averageDeliveryDelayDays": 1.2,
"qualityScore": 4.6,
"negotiationScore": 4.1,
"responseSpeedScore": 4.8
},

"pricingInsights": {
"averageDiscountPercent": 6.5,
"usuallyOffersDiscount": true
},

"riskInsights": {
"riskLevel": "low",
"issuesCount": 2
},

notes: [
"prefer price discount over warranty increase",
"not giving more than 10% discount"
],

"lastTransactionAt": "timestamp",

"active": true,

"metadata": {
"updatedAt": "timestamp"
}
}

Requisitions

{
"id": "req_001",

"organizationId": "org_001",

"title": "Engineering Laptop Procurement",

"description": "Procurement for new engineering hires",

"createdBy": "user_001",

"department": "Engineering",

"priority": "high",

"status": "negotiation",

"budget": {
"currency": "USD",
"estimatedAmount": 5500,
"approvedAmount": 5050
},

"items": [
{
"productId": "prod_dell_5440",

      "productName": "Dell Latitude 5440",

      "quantity": 5,

      "estimatedUnitPrice": 1100,

      "selectedVendorId": "vendor_cdw",

      "finalUnitPrice": 1010
    }

],

"workflowState": {
"currentStage": "vendor_negotiation",

    "completedStages": [
      "draft",
      "manager_approval"
    ],

    "pendingWith": {
      "type": "vendor",
      "id": "vendor_cdw"
    },

    "slaDueAt": "timestamp",

    "lastUpdatedAt": "timestamp"

},

"selectedVendor": {
"preferredVendorId": "vendor_cdw",

    "status": "ongoing",

    "quotedAmount": 5200,

    "finalAmount": 5050,

    "summary":
      "Vendor agreed to 8% discount after negotiation."

},

"nagotiationSteps" : [
{
"vendor": "",
"conversations": [

        ]
    }

],

"purchaseOrder": {
"poNumber": "PO-2026-001",

    "issuedAt": "timestamp",

    "status": "issued",

    "currency": "USD",

    "totalAmount": 5050

},

"grn": {
"status": "partial_received",

    "receivedAt": "timestamp",

    "receivedItems": [
      {
        "productId": "prod_dell_5440",
        "receivedQty": 3
      }
    ]

},

"invoice": {
"invoiceNumber": "INV-7781",

    "status": "pending_payment",

    "amount": 5050,

    "submittedAt": "timestamp",

    "paymentDueAt": "timestamp"

},

"summury" : "long text",
"metadata": {
"createdAt": "timestamp",
"updatedAt": "timestamp"
}
}
