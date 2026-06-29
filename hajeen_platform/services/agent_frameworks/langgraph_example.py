from typing import TypedDict, Annotated, List
import operator
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, END

# Define the state of our graph
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    next: str

# Define a simple agent node
def call_model(state):
    messages = state["messages"]
    # In a real scenario, this would call an LLM
    response = BaseMessage(content=f"LLM response to: {messages[-1].content}")
    return {"messages": [response]}

# Define a tool node
def call_tool(state):
    messages = state["messages"]
    # In a real scenario, this would call a tool
    response = BaseMessage(content=f"Tool response to: {messages[-1].content}")
    return {"messages": [response]}

# Define the graph
workflow = StateGraph(AgentState)

workflow.add_node("agent", call_model)
workflow.add_node("tool", call_tool)

workflow.set_entry_point("agent")

workflow.add_conditional_edges(
    "agent",
    lambda state: state["next"],
    {
        "tool_call": "tool",
        "end": END
    },
)
workflow.add_edge("tool", "agent")

app = workflow.compile()

# Example usage (for demonstration, not runnable without LangGraph setup)
# from langchain_core.messages import HumanMessage
# inputs = {"messages": [HumanMessage(content="hello")], "next": "end"}
# for output in app.stream(inputs):
#     for key, value in output.items():
#         print(f"Output from node '{key}': {value}")

print("LangGraph example created.")
