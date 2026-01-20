from fastapi import APIRouter, Request, HTTPException, Depends
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain_core.messages import HumanMessage
from fastapi.responses import StreamingResponse
import json
import traceback

from app.api.endpoints.dependencies import get_current_user_id
from app.services.history import upsert_thread, get_user_threads
from app.schemas.chat import ChatRequest
from app.services.graph.graph import build_rag_graph 
from app.services.graph.tools import UserContext

router = APIRouter()

@router.post("/")
async def chat_endpoint(
    request: Request, 
    payload: ChatRequest,
    user_id: str = Depends(get_current_user_id)
):
    pool = request.app.state.pool

    # Save thread metadata
    try:
        chat_title = payload.query[:30] + "..."
        await upsert_thread(pool, payload.thread_id, user_id, chat_title) 
    except Exception as e:
        print(f"Failed to save history: {e}")

    # Setup Graph and Config
    checkpointer = AsyncPostgresSaver(pool)
    app_graph = build_rag_graph(checkpointer)
    
    config = {
        "configurable": {"thread_id": payload.thread_id},
        "metadata": {"chat_title": payload.query[:5]}
    }
    context = UserContext(user_id=user_id)
    input_message = HumanMessage(content=payload.query)

    async def event_stream():
        try:
            in_think_block = False
            
            async for event in app_graph.astream_events(
                {"messages": [input_message]}, 
                config=config, 
                version="v2",
                context=context
            ):
                event_type = event.get("event")
                metadata = event.get("metadata", {})
                current_node = metadata.get("langgraph_node", "")

                # --- 1. CAPTURE WORKFLOW STEPS ---
                if event_type == "on_chain_start":
                    tags = event.get("tags", [])
                    is_node = any(t.startswith("graph:step") for t in tags)
                    if is_node and current_node:
                        display_name = current_node.replace("_", " ").title()
                        yield f"NODE:{display_name}\n"

                # --- 2. STREAM LLM CONTENT & REASONING ---
                elif event_type == "on_chat_model_stream":
                    
                    # Filter out internal nodes (grader/rewriter) if you don't want users seeing them
                    tags = event.get("tags", [])
                    if "internal_grading" in tags:
                        continue
                        
                    INTERNAL_NODES = ["grade_documents", "rewrite_question"]
                    if current_node in INTERNAL_NODES:
                        continue

                    chunk = event["data"].get("chunk")
                    if chunk:
                        # --- EXTRACT REASONING ---
                        # OpenRouter often puts reasoning in 'reasoning' field of extra_body/additional_kwargs
                        reasoning_chunk = ""
                        
                        # Check location 1: standard additional_kwargs (LangChain standard)
                        if hasattr(chunk, "additional_kwargs"):
                            reasoning_chunk = chunk.additional_kwargs.get("reasoning", "")
                        
                        # Check location 2: Sometimes it's directly in the dict if not parsed to object
                        if not reasoning_chunk and isinstance(chunk, dict):
                             reasoning_chunk = chunk.get("reasoning", "")

                        # --- HANDLE THINKING STATE ---
                        if reasoning_chunk:
                            if not in_think_block:
                                yield "THINKING_START\n"
                                in_think_block = True
                            
                            # Clean up newlines if necessary, or just stream raw
                            yield f"THINKING:{reasoning_chunk}\n"

                        # --- EXTRACT CONTENT ---
                        content_chunk = chunk.content
                        
                        # If we get content but we are currently in a think block, close it
                        if content_chunk:
                            if in_think_block:
                                yield "THINKING_END\n"
                                in_think_block = False
                            
                            yield f"CONTENT:{content_chunk}\n"

                # --- 3. HANDLE TOOL CALLS ---
                elif event_type == "on_chat_model_end":
                    # Safety cleanup
                    if in_think_block:
                        yield "THINKING_END\n"
                        in_think_block = False

                    output = event["data"].get("output")
                    if output and hasattr(output, "tool_calls") and output.tool_calls:
                        for tool_call in output.tool_calls:
                            tool_data = {
                                "name": tool_call.get("name"),
                                "args": tool_call.get("args", {}),
                                "id": tool_call.get("id")
                            }
                            yield f"TOOL_CALL:{json.dumps(tool_data)}\n"
                
                # --- 4. TOOL OUTPUTS ---
                elif event_type == "on_tool_end":
                    tool_name = event.get("name", "Tool")
                    raw_output = event["data"].get("output", "")
                    
                    if hasattr(raw_output, "content"):
                        tool_output = raw_output.content
                    else:
                        tool_output = str(raw_output)

                    display_output = tool_output[:200] + "..." if len(tool_output) > 200 else tool_output

                    tool_data = {
                        "name": tool_name,
                        "output": display_output
                    }
                    yield f"TOOL_END:{json.dumps(tool_data)}\n"

        except Exception as e:
            print(f"Stream Error: {e}")
            traceback.print_exc()
            yield f"ERROR:{str(e)}\n"

    return StreamingResponse(event_stream(), media_type="text/plain")

    

@router.get("/history")
async def get_history(
    request: Request,
    user_id: str = Depends(get_current_user_id)
):
    pool = request.app.state.pool
    
    try:
        # Pass the pool to the service
        threads = await get_user_threads(pool, user_id) 
        
        # Clean up data for frontend
        results = []
        for t in threads:
            results.append({
                "id": str(t["thread_id"]),
                "title": t["title"],
                "date": t["created_at"].isoformat()
            })
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

# Add these imports
from langchain_core.messages import HumanMessage, AIMessage

@router.get("/{thread_id}")
async def get_thread_messages(request: Request, thread_id: str):
    """
    Fetches the actual message history for a specific thread to display on the frontend.
    """
    pool = request.app.state.pool
    checkpointer = AsyncPostgresSaver(pool)
    app_graph = build_rag_graph(checkpointer)
    
    config = {"configurable": {"thread_id": thread_id}}
    
    # Get the latest state from LangGraph
    state_snapshot = await app_graph.aget_state(config)
    
    messages = []
    # If state exists, extract messages
    if state_snapshot.values and "messages" in state_snapshot.values:
        for msg in state_snapshot.values["messages"]:
            # Skip tool messages - they should not be displayed
            if msg.type == 'tool':
                continue
                
            # Convert LangChain objects to simple JSON for frontend
            role = "user" if isinstance(msg, HumanMessage) else "bot"
            
            # For AI messages, include tool_calls if present
            msg_dict = {
                "role": role, 
                "content": msg.content,
                "type": msg.type
            }
            
            # Add tool_calls if present
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                msg_dict["tool_calls"] = msg.tool_calls
                
            messages.append(msg_dict)
            
    return {"messages": messages}
