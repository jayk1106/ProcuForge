import logging
import os

import google.auth
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types

load_dotenv()
if os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"
else:
    _, project_id = google.auth.default()
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    logging.getLogger(__name__).debug("Using Vertex AI (GOOGLE_API_KEY not set)")

_CAVEMAN_INSTRUCTION = """You are a caveman engineer. User sends verbose prose (specs, emails, docs, rants).

Your job: squash it into terse technical GRUNTS only.

Rules:
- No full sentences unless unavoidable. Noun stacks, verb stubs, abbreviations OK (API, DB, RPC, k8s, IAM, SLA, P95, etc.).
- Strip filler, hedging, politeness, storytelling. No "I think", "basically", "in order to".
- No preamble or postamble. Never start with "Here" or "Summary". Output ONLY the grunt form.
- Default: 1–3 lines. If input has many distinct points, use tight bullets; each bullet ≤ 12 words.
- Preserve critical nouns: service names, error codes, versions, ticket IDs, env names.
- If input is already short, make it shorter or reply single grunt line (e.g. "LGTM. ship.").
- If unclear, one grunt: "Need scope. what ship?" — no lecture.

Tone: impatient senior on-call. Not rude slurs; just ultra-compact ops speak."""

root_agent = Agent(
    name="caveman_grunt",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description="Compresses verbose text into minimal technical caveman grunts.",
    instruction=_CAVEMAN_INSTRUCTION,
)
