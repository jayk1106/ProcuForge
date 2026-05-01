from google.adk.agents import Agent


def search_vendors() -> list[str]:
    """
    Search for vendors in the database
    @return: List of vendors
    """
    return [
        "Abc",
        "Def",
        "Ghi",
    ]


vendor_search_agent = Agent(
    name="vendor_search_agent",
    model="gemini-flash-latest",
    description="A agent that searches for vendors",
    instruction="""
    You are a helpful assistant that searches for vendors
    after getting list of the vendors, tranfer it to the master agent
    """,
    tools=[search_vendors],
)