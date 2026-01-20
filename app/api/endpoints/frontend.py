from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def serve_chat_interface():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>RAG Chat</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 0; height: 100vh; display: flex; background-color: #f5f5f5; }
            
            /* Sidebar Styles */
            .sidebar { width: 260px; background-color: #202123; color: white; display: flex; flex-direction: column; padding: 10px; flex-shrink: 0; }
            .new-chat-btn { border: 1px solid #565869; background: transparent; color: white; padding: 10px; border-radius: 5px; cursor: pointer; text-align: left; margin-bottom: 20px; transition: background 0.2s; display: flex; align-items: center; gap: 10px; }
            .new-chat-btn:hover { background-color: #2A2B32; }
            .history-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 5px; }
            .history-item { padding: 10px; border-radius: 5px; cursor: pointer; font-size: 0.9em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #ECECF1; }
            .history-item:hover { background-color: #2A2B32; }
            .history-item.active { background-color: #343541; }

            /* Main Chat Area */
            .main-content { flex: 1; display: flex; flex-direction: column; position: relative; }
            .chat-header { background: white; padding: 15px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
            .chat-messages { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 20px; scroll-behavior: smooth; }
            
            .message { max-width: 80%; padding: 15px; border-radius: 10px; line-height: 1.5; position: relative; }
            .user-message { align-self: flex-end; background-color: #007bff; color: white; border-bottom-right-radius: 2px; }
            .bot-message { align-self: flex-start; background-color: white; border: 1px solid #ddd; color: #333; border-bottom-left-radius: 2px; }
            
            .input-area { padding: 20px; background: white; border-top: 1px solid #eee; display: flex; gap: 10px; }
            input[type="text"] { flex: 1; padding: 12px; border: 1px solid #ddd; border-radius: 25px; outline: none; font-size: 16px; }
            button { padding: 10px 25px; background-color: #007bff; color: white; border: none; border-radius: 25px; cursor: pointer; font-weight: bold; }
            button:disabled { background-color: #ccc; }
        </style>
    </head>
    <body>

        <div class="sidebar">
            <button class="new-chat-btn" onclick="startNewChat()">+ New Chat</button>
            <div class="history-list" id="historyList">
                </div>
        </div>

        <div class="main-content">
            <div class="chat-header">
                <span id="header-title">New Chat</span>
                <span style="font-size:0.8em; color:#888" id="thread-display"></span>
            </div>

            <div class="chat-messages" id="messages">
                <div class="message bot-message">Hello! Select a chat from the left or start a new one.</div>
            </div>

            <div class="input-area">
                <input type="text" id="userInput" placeholder="Type your question..." autocomplete="off">
                <button onclick="sendMessage()" id="sendBtn">Send</button>
            </div>
        </div>

        <script>
            let currentThreadId = null;
            // Fake User ID for demo - in real app, get this from login
            const USER_ID = "user_123"; 

            // --- Initialization ---
            document.addEventListener('DOMContentLoaded', () => {
                loadHistory();
                startNewChat(); // Default to new chat
            });

            // --- History Functions ---
            async function loadHistory() {
                try {
                    const response = await fetch('/chat/history', {
                        headers: { 'x-user-id': USER_ID }
                    });
                    const threads = await response.json();
                    
                    const list = document.getElementById('historyList');
                    list.innerHTML = ''; // Clear list

                    threads.forEach(t => {
                        const div = document.createElement('div');
                        div.className = 'history-item';
                        div.textContent = t.title || "Untitled Chat";
                        div.onclick = () => loadThread(t.id, t.title);
                        list.appendChild(div);
                    });
                } catch (e) {
                    console.error("Failed to load history", e);
                }
            }

            function startNewChat() {
                currentThreadId = crypto.randomUUID();
                document.getElementById('messages').innerHTML = '<div class="message bot-message">Hello! Im your RAG assistant. How can I help you?</div>';
                document.getElementById('header-title').innerText = "New Chat";
                document.getElementById('thread-display').innerText = `ID: ${currentThreadId.slice(0,8)}...`;
                
                // Remove active class from sidebar items
                document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
            }

            async function loadThread(threadId, title) {
                currentThreadId = threadId;
                document.getElementById('header-title').innerText = title || "Chat";
                document.getElementById('thread-display').innerText = `ID: ${threadId.slice(0,8)}...`;
                document.getElementById('messages').innerHTML = '<div class="typing-indicator">Loading history...</div>';

                // Highlight active item
                document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
                // (Optional: add logic here to find the clicked element and add 'active' class)

                try {
                    // Fetch old messages
                    const res = await fetch(`/chat/${threadId}`);
                    const data = await res.json();
                    
                    const msgDiv = document.getElementById('messages');
                    msgDiv.innerHTML = ''; // Clear loading

                    if (data.messages.length === 0) {
                        msgDiv.innerHTML = '<div class="message bot-message">No messages found. Start typing!</div>';
                    }

                    data.messages.forEach(msg => {
                        addMessageToUI(msg.content, msg.role);
                    });
                } catch (e) {
                    alert("Error loading thread: " + e.message);
                }
            }

            // --- Chat Functions ---
            const inputField = document.getElementById('userInput');
            
            inputField.addEventListener("keypress", function(event) {
                if (event.key === "Enter") sendMessage();
            });

            function addMessageToUI(text, role) {
                const div = document.createElement('div');
                div.className = `message ${role === 'user' ? 'user-message' : 'bot-message'}`;
                div.textContent = text;
                const container = document.getElementById('messages');
                container.appendChild(div);
                container.scrollTop = container.scrollHeight;
            }

            async function sendMessage() {
                const query = inputField.value.trim();
                if (!query) return;

                addMessageToUI(query, 'user');
                inputField.value = '';
                inputField.disabled = true;

                try {
                    const response = await fetch('/chat/', {
                        method: 'POST',
                        headers: { 
                            'Content-Type': 'application/json',
                            'x-user-id': USER_ID 
                        },
                        body: JSON.stringify({ 
                            query: query, 
                            thread_id: currentThreadId 
                        })
                    });

                    if (!response.ok) throw new Error("Server Error");

                    const data = await response.json();
                    addMessageToUI(data.response, 'bot');
                    
                    // Refresh history list (in case title changed or new chat was created)
                    loadHistory(); 

                } catch (error) {
                    addMessageToUI("Error: " + error.message, 'bot');
                } finally {
                    inputField.disabled = false;
                    inputField.focus();
                }
            }
        </script>
    </body>
    </html>
    """
    return html_content