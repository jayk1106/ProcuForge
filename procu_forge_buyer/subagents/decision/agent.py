from google.adk.agents import Agent
from pydantic import BaseModel, Field


class DecisionOutput(BaseModel):
    vendor: str = Field(description="The best vendor for our usecase")


decision_agent = Agent(
    name="decision_agent",
    description="A agent that makes decisions",
    instruction="""
    You are a helpful assistant that makes decisions regarding the who is the best vendor for our usecase
    After getting final vendor decision, tranfer it to the master agent
    """,
    model="gemini-flash-latest",
    output_schema=DecisionOutput
)