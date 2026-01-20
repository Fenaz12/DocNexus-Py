from langgraph.graph import StateGraph, START, END,MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.services.graph.nodes import RAGState
from app.services.graph.tools import get_retrievel_tool
from app.services.graph.nodes import (
    generate_answer,
    generate_query_or_respond, 
    rewrite_question,
    grade_documents)

from app.services.graph.tools import UserContext

def build_rag_graph(checkpointer: AsyncPostgresSaver):
    workflow = StateGraph(RAGState, context_schema=UserContext)

    # Define the nodes we will cycle between
    workflow.add_node(generate_query_or_respond)
    workflow.add_node("retrieve", ToolNode([get_retrievel_tool]))
    workflow.add_node(rewrite_question)
    workflow.add_node(generate_answer)

    workflow.add_edge(START, "generate_query_or_respond")

    # Decide whether to retrieve
    workflow.add_conditional_edges(
        "generate_query_or_respond",
        # Assess LLM decision (call `retriever_tool` tool or respond to the user)
        tools_condition,
        {
            # Translate the condition outputs to nodes in our graph
            "tools": "retrieve",
            END: END,
        },
    )

    # Edges taken after the `action` node is called.
    workflow.add_conditional_edges(
        "retrieve",
        # Assess agent decision
        grade_documents,

    )
    workflow.add_edge("generate_answer", END)
    workflow.add_edge("rewrite_question", "generate_query_or_respond")

    return workflow.compile(checkpointer=checkpointer)