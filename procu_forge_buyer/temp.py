from google.cloud import aiplatform

# Initialize the Vertex AI SDK
aiplatform.init(project="ratelx-ai", location="us-central1")

# Create a placeholder Agent Engine resource
agent_engine = aiplatform.ReasoningEngine.create(
    display_name="procuforge-reasoning-engine",
    # ADK uses this resource shell to associate session/memory storage
)

# Extract the ID
reasoning_engine_id = agent_engine.resource_name.split("/")[-1]
print(f"Your Reasoning Engine ID is: {reasoning_engine_id}")
