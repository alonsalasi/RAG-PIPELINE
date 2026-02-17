# Chat History Feature - GUI Implementation

## Changes Required in index.html

### 1. Add Chat History Sidebar CSS (add to <style> section):

```css
.chat-history-sidebar { width:280px; background:#fff; border-left:1px solid #dee2e6; padding:15px; overflow-y:auto; display:flex; flex-direction:column; gap:10px; }
.chat-history-header { font-weight:600; font-size:1.1em; margin-bottom:10px; display:flex; justify-content:space-between; align-items:center; }
.chat-item { padding:10px; background:#f8f9fa; border-radius:8px; cursor:pointer; transition:all 0.2s; border:1px solid #e0e0e0; }
.chat-item:hover { background:#e9ecef; transform:translateX(-2px); }
.chat-item.active { background:#007bff; color:white; border-color:#007bff; }
.chat-item-title { font-size:0.9em; font-weight:500; margin-bottom:4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.chat-item-time { font-size:0.75em; opacity:0.7; }
.chat-item-delete { float:right; color:#dc3545; font-size:0.9em; padding:2px 6px; }
.chat-item-delete:hover { background:#dc3545; color:white; border-radius:4px; }
.new-chat-btn { width:100%; padding:8px; background:#28a745; color:white; border:none; border-radius:6px; cursor:pointer; font-weight:600; margin-bottom:10px; }
.new-chat-btn:hover { background:#218838; }
</style>
```

### 2. Update body.logged-in structure:

Change from:
```html
<div id="app">
<div class="sidebar">...</div>
<div class="container">...</div>
</div>
```

To:
```html
<div id="app">
<div class="sidebar">...</div>
<div class="container">...</div>
<div class="chat-history-sidebar" id="chat-history-sidebar">
  <button class="new-chat-btn" onclick="newChat()">+ New Chat</button>
  <div class="chat-history-header">
    <span>💬 Chat History</span>
  </div>
  <div id="chat-list"></div>
</div>
</div>
```

### 3. Add JavaScript functions (add before </script>):

```javascript
let currentChatId = null;
let chatMessages = [];

async function loadChatHistory() {
  try {
    const res = await fetch(`${API_GATEWAY_URL}/chat/list`, { headers: getAuthHeaders() });
    const data = await res.json();
    renderChatList(data.chats || []);
  } catch(e) {
    console.error('Failed to load chat history:', e);
  }
}

function renderChatList(chats) {
  const list = document.getElementById('chat-list');
  list.innerHTML = '';
  chats.forEach(chat => {
    const div = document.createElement('div');
    div.className = 'chat-item' + (chat.chatId === currentChatId ? ' active' : '');
    const date = new Date(chat.timestamp * 1000);
    div.innerHTML = `
      <div class="chat-item-title">${chat.title}</div>
      <div class="chat-item-time">${date.toLocaleDateString()} ${date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</div>
      <span class="chat-item-delete" onclick="deleteChat('${chat.chatId}', event)">🗑️</span>
    `;
    div.onclick = () => loadChat(chat.chatId);
    list.appendChild(div);
  });
}

async function saveCurrentChat() {
  if (chatMessages.length === 0) return;
  const title = chatMessages[0].content.substring(0, 50) + (chatMessages[0].content.length > 50 ? '...' : '');
  try {
    await fetch(`${API_GATEWAY_URL}/chat/save`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ chatId: currentChatId, title, messages: chatMessages })
    });
    loadChatHistory();
  } catch(e) {
    console.error('Failed to save chat:', e);
  }
}

async function loadChat(chatId) {
  try {
    const res = await fetch(`${API_GATEWAY_URL}/chat/load?chatId=${chatId}`, { headers: getAuthHeaders() });
    const data = await res.json();
    currentChatId = chatId;
    chatMessages = data.messages || [];
    CHAT_LOG.innerHTML = '';
    chatMessages.forEach(msg => {
      if (msg.role === 'user') {
        appendMessage('user', msg.content);
      } else {
        const div = document.createElement('div');
        div.className = 'message assistant-message';
        div.innerHTML = marked.parse(msg.content);
        CHAT_LOG.appendChild(div);
      }
    });
    renderChatList((await (await fetch(`${API_GATEWAY_URL}/chat/list`, { headers: getAuthHeaders() })).json()).chats || []);
  } catch(e) {
    console.error('Failed to load chat:', e);
  }
}

async function deleteChat(chatId, event) {
  event.stopPropagation();
  if (!confirm('Delete this chat?')) return;
  try {
    await fetch(`${API_GATEWAY_URL}/chat/delete?chatId=${chatId}`, { method: 'DELETE', headers: getAuthHeaders() });
    if (chatId === currentChatId) newChat();
    loadChatHistory();
  } catch(e) {
    console.error('Failed to delete chat:', e);
  }
}

function newChat() {
  currentChatId = `chat_${Date.now()}`;
  chatMessages = [];
  clearChat();
  renderChatList([]);
  loadChatHistory();
}

// Update appendMessage to track messages
const originalAppendMessage = appendMessage;
appendMessage = function(role, content, sources, isError, images) {
  originalAppendMessage(role, content, sources, isError, images);
  if (!isError) {
    chatMessages.push({ role, content, timestamp: Date.now() });
    if (chatMessages.length % 2 === 0) saveCurrentChat(); // Save after each Q&A pair
  }
};

// Load chat history on login
const originalCheckExistingSession = checkExistingSession;
checkExistingSession = function() {
  originalCheckExistingSession();
  setTimeout(() => {
    if (document.getElementById('app').style.display === 'flex') {
      loadChatHistory();
      newChat();
    }
  }, 1000);
};
```

### 4. Update clearChat function:

```javascript
function clearChat() {
  CHAT_LOG.innerHTML = '';
  sessionId = generateSessionId();
  chatMessages = [];
  appendMessage('assistant', 'Hello! I\\'m your conversational AI assistant. I can remember our conversation and help analyze your documents in Hebrew, English, and Turkish.');
}
```

## Deployment

After updating index.html:
1. Upload to S3: `aws s3 cp index.html s3://your-bucket/index.html`
2. Invalidate CloudFront cache
3. Redeploy agent Lambda with new endpoints

The chat history will:
- Auto-save after each Q&A pair
- Show last 10 chats
- Allow loading previous chats
- Allow deleting chats
- Create new chats with "+ New Chat" button
