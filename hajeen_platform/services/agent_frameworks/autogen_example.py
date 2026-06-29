import autogen
import logging

logger = logging.getLogger(__name__)

# Configuration for AutoGen agents
config_list = autogen.config_list_from_json(
    "OAI_CONFIG_LIST",
    filter_dict={
        "model": ["gpt-4", "gpt-3.5-turbo"], # Replace with your actual LLM models
    },
)

# Create an assistant agent
assistant = autogen.AssistantAgent(
    name="assistant",
    llm_config={
        "seed": 42,  # Seed for reproducibility
        "config_list": config_list,
        "temperature": 0,
    },
)

# Create a user proxy agent
user_proxy = autogen.UserProxyAgent(
    name="user_proxy",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=10,
    is_termination_msg=lambda x: x.get("content", "").rstrip().endswith("TERMINATE"),
    code_execution_config={
        "work_dir": "coding",
        "use_docker": False, # Set to True if Docker is available
    },
)

# Example of initiating a chat (for demonstration, not runnable without proper LLM setup)
# async def initiate_autogen_chat():
#     await user_proxy.initiate_chat(
#         assistant,
#         message="What is the capital of France?",
#     )

logger.info("AutoGen example created.")
