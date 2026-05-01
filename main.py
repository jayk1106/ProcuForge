import uuid
import asyncio

from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from master.agent import root_agent

load_dotenv()

USER_ID = 'user'
SESSION_ID = str(uuid.uuid4())
APP_NAME = "procuforge"

async def main():
    session_service_stateful = InMemorySessionService()

    stateful_session = await session_service_stateful.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID,
        state={},
    )

    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
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