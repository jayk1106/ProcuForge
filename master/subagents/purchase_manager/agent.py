from google.adk.agents import Agent


def create_purchase_order(vendor: str, product: str, quantity: int) -> str:
    """
    Create a purchase order
    @param vendor: The vendor to create the purchase order
    @param product: The product to create the purchase order
    @param quantity: The quantity to create the purchase order
    @return: The purchase order
    """
    return f"The purchase order for the vendor {vendor} is {product} with quantity {quantity}"

def verify_delivery(purchase_order: str) -> str:
    """
    Verify the delivery of the purchase order
    @param purchase_order: The purchase order to verify the delivery
    @return: The delivery of the purchase order
    """
    return f"The delivery of the purchase order {purchase_order} is verified"

def verify_invoice(purchase_order: str) -> str:
    """
    Verify the invoice of the purchase order
    @param purchase_order: The purchase order to verify the invoice
    @return: The invoice of the purchase order
    """
    return f"The invoice of the purchase order {purchase_order} is verified"

purchase_manager_agent = Agent(
    name="purchase_manager_agent",
    description="A agent that manages the purchase order, verification of the delivery and invices",
    instruction="""
    You are a helpful assistant that manages the purchase
    Steps:
        1. Create a purchase order
        2. Verify the delivery of the purchase order
        3. Verify the invoice
    You have the following tools:
    create_purchase_order, verify_delivery, verify_invoice
    After completing the purchase, tranfer it to the master agent
    """,
    model="gemini-flash-latest",
    tools=[create_purchase_order, verify_delivery, verify_invoice],
)