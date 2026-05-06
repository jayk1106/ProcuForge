from google.adk.agents import Agent

def request_for_quote(vendor: str) -> str:
    """
    Request for quote from the vendor
    @param vendor: The vendor to request for quote
    @return: The quote from the vendor
    """
    return f"The quote from the vendor {vendor} is 1000"

def negotiate_with_vendor(vendor: str, proposed_price: int) -> str:
    """
    Negotiate with the vendor for the best price
    @param vendor: The vendor to negotiate with
    @param proposed_price: The proposed price
    @return: The negotiated price
    """
    return f"The negotiated price with the vendor {vendor} is {proposed_price}"

def follow_up_with_vendor(vendor: str) -> str:
    """
    Follow up with the vendor for the best price
    @param vendor: The vendor to follow up with
    @return: The follow up with the vendor
    """

    follow_up_price = '900' if vendor == 'Ghi' else '950'

    return f"The follow up with the vendor {vendor} is {follow_up_price}"


# def send_message_to_vendor(vendor: str, message: str) -> str:
#     """
#     Send Message to the vendor
#     @param vendor: The vendor to send message to
#     @param message: The message to send to the vendor
#     @return: The message sent to the vendor
#     """
#     return f"The message {message} sent to the vendor {vendor}"


negotiator_agent = Agent(
    name="negotiator_agent",
    model="gemini-flash-latest",
    description="A agent that negotiates with vendors",
    instruction="""
    You are a helpful assistant that negotiates with vendors for better prices. 
    Steps:
        1. Request for quote from the vendor
        2. Negotiate with the vendor based on their response
    You have the following tools: 
    send_message_to_vendor

    After completing the negotiation or sending the message, tranfer it to the master agent
    """,
    tools=[request_for_quote, negotiate_with_vendor, follow_up_with_vendor],
)