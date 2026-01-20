from langchain.tools import tool, ToolRuntime
from app.services.vector_store import vector_store_service
from dataclasses import dataclass

@dataclass
class UserContext:
    user_id: str


@tool
def get_retrievel_tool(query: str, runtime: ToolRuntime[UserContext]) -> str:
    """
    Search and return information about the uploaded documents.
    This tool automatically filters by the current user's ID.
    """
    # Access user_id from runtime context
    user_id = runtime.context.user_id
    
    print(f"🔍 Tool Execution: Searching docs for User {user_id}...")
    
    retriever = vector_store_service.get_retreiver(user_id)
    docs = retriever.invoke(query)
    
    if not docs:
        return "No relevant documents found."
    
    formatted_docs = "\n\n---\n\n".join([doc.page_content for doc in docs])
    return formatted_docs

