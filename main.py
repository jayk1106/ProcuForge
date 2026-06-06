import uuid
import asyncio
import os

from dotenv import load_dotenv
from google.adk.runners import Runner
# from google.adk.sessions import InMemorySessionService
from google.adk.sessions import VertexAiSessionService
from google.genai import types
from procu_forge_buyer.agent import root_agent

load_dotenv()

USER_ID = 'user'
SESSION_ID = str(uuid.uuid4())

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GOOGLE_PROJECT_ID")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("GOOGLE_BUCKET_REGION", "us-central1")
REASONING_ENGINE_APP_NAME = os.getenv("BUYER_REASONING_ENGINE")
if not REASONING_ENGINE_APP_NAME:
    raise RuntimeError(
        "BUYER_REASONING_ENGINE env var is required "
        "(see logs/procu-forge-buyer_deployment_metadata.json)"
    )

async def main():
    # session_service_stateful = InMemorySessionService()
    session_service_stateful = VertexAiSessionService(project=PROJECT_ID, location=LOCATION)

    stateful_session = await session_service_stateful.create_session(
        app_name=REASONING_ENGINE_APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID,
        state={},
    )


    runner = Runner(
        agent=root_agent,
        app_name=REASONING_ENGINE_APP_NAME,
        session_service=session_service_stateful
    )

    new_message = types.Content(
        role="user", parts=[types.Part(text="Buy me 10 mackbook air m1")]
    )

    for event in runner.run(
        user_id=USER_ID,
        session_id=SESSION_ID,
        new_message=new_message,
    ):
        print(event.content.parts[0].text)
        if event.is_final_response():
            if event.content and event.content.parts:
                print(f"Final Response: {event.content.parts[0].text}")

asyncio.run(main())