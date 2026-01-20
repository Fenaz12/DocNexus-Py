from app.services.graph.tools import get_retrievel_tool
from app.core.config import settings
from app.schemas.graph import GradeDocuments 
from app.core.prompts import ROUTER_SYSTEM_PROMPT, GRADE_DOCUMENTS_PROMPT, REWRITE_PROMPT, ANSWER_INSTURCTION

from typing import Literal  

from langchain.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langgraph.graph import MessagesState
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime #--add again evalv
from app.services.graph.tools import UserContext #----add again evalv

response_model = ChatOpenAI(base_url= settings.OPEN_ROUTER_BASE_URL, 
                            model=settings.OPEN_ROUTER_CHAT_LLM, 
                            api_key = settings.OPEN_ROUTER_API,
                            max_tokens=1000
                            )
grader_model = ChatOpenAI(base_url= settings.OPEN_ROUTER_BASE_URL, 
                        model=settings.OPEN_ROUTER_CHAT_LLM,
                        api_key = settings.OPEN_ROUTER_API,
                        temperature=0).with_structured_output(GradeDocuments)

class RAGState(MessagesState):
    """Extended state for RAG"""
    rewritten_question: str = ""
    loop_step: int = 0 

async def generate_query_or_respond(state: RAGState, runtime: Runtime[UserContext]): 
#async def generate_query_or_respond(state: RAGState, config: RunnableConfig): #----add again evalv
    """Call the model to generate a response based on the current state."""

    if state.get("rewritten_question"):
        messages = [
            SystemMessage(content=ROUTER_SYSTEM_PROMPT),
            HumanMessage(content=state["rewritten_question"])
        ]
    else:
        messages = [SystemMessage(content=ROUTER_SYSTEM_PROMPT)] + state["messages"]    
    
    response = await (
        response_model.bind_tools([get_retrievel_tool]).ainvoke(messages)
    )

    # Note: We reset loop_step here IF the model decides NOT to use a tool (i.e. normal chat)
    # But if it uses a tool, we keep the current loop_step.
    return {"messages": [response], "rewritten_question": ""}

async def grade_documents(state: RAGState) -> Literal["generate_answer", "rewrite_question"]:
    """Determine whether the retrieved documents are relevant to the question."""
    
    last_human_msg = [m for m in state["messages"] if m.type == "human"][-1]
    question = last_human_msg.content
    context = state["messages"][-1].content

    # 1. Check Loop Limit
    current_loop = state.get("loop_step", 0)
    MAX_RETRIES = 3 

    if current_loop >= MAX_RETRIES:
        print(f"--- LOOP LIMIT REACHED ({current_loop}) ---")
        return "generate_answer"  

    # 2. Grade Documents
    prompt = GRADE_DOCUMENTS_PROMPT.format(question=question, context=context)
    response = await (grader_model.ainvoke(
        [{"role":"user", "content": prompt,}],
        config={"tags": ["internal_grading"]}
    ))

    score = response.binary_score

    if score == "yes":
        return "generate_answer"
    else:
        return "rewrite_question"

async def rewrite_question(state: RAGState):
    """Rewrite the question based on the loop count."""
    
    last_human_msg = [m for m in state["messages"] if m.type == "human"][-1]
    original_question = last_human_msg.content
    
    # Check how many times we've looped
    loop_step = state.get("loop_step", 0)
    
    # Dynamic Prompting based on desperation
    if loop_step == 0:
        instructions = f"Rewrite this question to be more specific and technical: {original_question}"
    elif loop_step == 1:
        instructions = f"The previous search failed. Convert this question into a list of 3-4 distinct keywords/entities: {original_question}"
    else:
        instructions = f"The previous searches failed. Focus ONLY on the dates or proper nouns in this question: {original_question}"

    response = await response_model.ainvoke([{"role": "user", "content": instructions}])
    
    return {
        "rewritten_question": response.content,
        "loop_step": loop_step + 1
    }

async def generate_answer(state: RAGState):
    """Generate an answer."""
    
    # 1. Extract context (Optional: You can keep this to reinforce context in the system prompt)
    all_tool_msgs = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    context = ""
    if all_tool_msgs:
        context = all_tool_msgs[-1].content
    else:
        context = "No context available."

    # 2. Setup System Prompt
    system_prompt_content = f"""{ANSWER_INSTURCTION}

    background_context:
    {context}
    """
    
    messages_to_send = [SystemMessage(content=system_prompt_content)]

    # 3. Add History
    for msg in state["messages"]:
        if isinstance(msg, (HumanMessage, AIMessage, ToolMessage)): 
            messages_to_send.append(msg)

    # 4. Generate Response
    response = await response_model.ainvoke(messages_to_send)

    return {"messages": [response], "loop_step": 0}