/**
 * CognitionShift AI Gateway — Embeddable Widget
 * 
 * Usage:
 *   <script src="http://YOUR_SERVER:3000/embed.js" 
 *           data-api-url="http://YOUR_SERVER:8000" 
 *           data-api-key="YOUR_API_KEY"
 *           data-theme="dark"
 *           data-position="bottom-right">
 *   </script>
 */
(function() {
  'use strict';

  const script = document.currentScript;
  const apiUrl = script.getAttribute('data-api-url') || 'http://localhost:8000';
  const apiKey = script.getAttribute('data-api-key') || '';
  const theme = script.getAttribute('data-theme') || 'dark';
  const position = script.getAttribute('data-position') || 'bottom-right';

  const colors = theme === 'dark' 
    ? { bg: '#0f172a', bgCard: '#1e293b', border: '#334155', text: '#f1f5f9', textMuted: '#94a3b8', accent: '#3b82f6' }
    : { bg: '#ffffff', bgCard: '#f8fafc', border: '#e2e8f0', text: '#0f172a', textMuted: '#64748b', accent: '#3b82f6' };

  // Inject styles
  const style = document.createElement('style');
  style.textContent = `
    #csgateway-widget-btn {
      position: fixed;
      ${position === 'bottom-left' ? 'left: 20px;' : 'right: 20px;'}
      bottom: 20px;
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: ${colors.accent};
      color: white;
      border: none;
      cursor: pointer;
      font-size: 24px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      z-index: 999999;
      transition: transform 0.2s;
    }
    #csgateway-widget-btn:hover { transform: scale(1.1); }
    #csgateway-widget-panel {
      position: fixed;
      ${position === 'bottom-left' ? 'left: 20px;' : 'right: 20px;'}
      bottom: 88px;
      width: 380px;
      height: 500px;
      background: ${colors.bg};
      border: 1px solid ${colors.border};
      border-radius: 16px;
      z-index: 999999;
      display: none;
      flex-direction: column;
      box-shadow: 0 8px 32px rgba(0,0,0,0.3);
      overflow: hidden;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    #csgateway-widget-panel.open { display: flex; }
    #csgateway-widget-header {
      padding: 12px 16px;
      background: ${colors.bgCard};
      border-bottom: 1px solid ${colors.border};
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    #csgateway-widget-messages {
      flex: 1;
      overflow-y: auto;
      padding: 12px;
    }
    .csw-msg { margin-bottom: 12px; max-width: 85%; }
    .csw-msg-user { margin-left: auto; background: ${colors.accent}; color: white; padding: 8px 12px; border-radius: 12px 12px 2px 12px; font-size: 13px; }
    .csw-msg-ai { background: ${colors.bgCard}; color: ${colors.text}; padding: 8px 12px; border-radius: 12px 12px 12px 2px; font-size: 13px; border: 1px solid ${colors.border}; }
    #csgateway-widget-input-area {
      padding: 12px;
      border-top: 1px solid ${colors.border};
      display: flex;
      gap: 8px;
    }
    #csgateway-widget-input {
      flex: 1;
      padding: 8px 12px;
      border-radius: 8px;
      border: 1px solid ${colors.border};
      background: ${colors.bgCard};
      color: ${colors.text};
      font-size: 13px;
      outline: none;
    }
    #csgateway-widget-send {
      padding: 8px 16px;
      border-radius: 8px;
      background: ${colors.accent};
      color: white;
      border: none;
      cursor: pointer;
      font-size: 13px;
    }
  `;
  document.head.appendChild(style);

  // Create elements
  const btn = document.createElement('button');
  btn.id = 'csgateway-widget-btn';
  btn.textContent = '⚡';
  btn.setAttribute('aria-label', 'Open AI Assistant');

  const panel = document.createElement('div');
  panel.id = 'csgateway-widget-panel';
  panel.innerHTML = `
    <div id="csgateway-widget-header">
      <span style="font-weight:600;font-size:14px;color:${colors.text}">⚡ CognitionShift AI</span>
      <button onclick="document.getElementById('csgateway-widget-panel').classList.remove('open')" 
              style="background:none;border:none;color:${colors.textMuted};cursor:pointer;font-size:18px">✕</button>
    </div>
    <div id="csgateway-widget-messages"></div>
    <div id="csgateway-widget-input-area">
      <input id="csgateway-widget-input" placeholder="Type a message..." />
      <button id="csgateway-widget-send">Send</button>
    </div>
  `;

  document.body.appendChild(btn);
  document.body.appendChild(panel);

  let conversationId = null;
  let token = null;

  btn.addEventListener('click', () => {
    panel.classList.toggle('open');
    if (panel.classList.contains('open')) {
      document.getElementById('csgateway-widget-input').focus();
    }
  });

  function addMessage(role, text) {
    const msgs = document.getElementById('csgateway-widget-messages');
    const div = document.createElement('div');
    div.className = `csw-msg csw-msg-${role === 'user' ? 'user' : 'ai'}`;
    div.textContent = text;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    return div;
  }

  async function sendMessage(content) {
    if (!content.trim()) return;
    addMessage('user', content);

    if (!token && apiKey) {
      token = apiKey;
    }

    try {
      // Create conversation if needed
      if (!conversationId) {
        const convResp = await fetch(`${apiUrl}/api/v1/conversations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
          body: JSON.stringify({}),
        });
        if (convResp.ok) {
          conversationId = (await convResp.json()).id;
        }
      }

      // Send message (non-streaming for simplicity in embed)
      const resp = await fetch(`${apiUrl}/api/v1/conversations/${conversationId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ content, stream: false }),
      });

      if (resp.ok) {
        const data = await resp.json();
        addMessage('ai', data.data?.content || 'No response');
      } else {
        addMessage('ai', 'Error: Could not get response');
      }
    } catch (err) {
      addMessage('ai', 'Error: ' + err.message);
    }
  }

  document.getElementById('csgateway-widget-send').addEventListener('click', () => {
    const input = document.getElementById('csgateway-widget-input');
    sendMessage(input.value);
    input.value = '';
  });

  document.getElementById('csgateway-widget-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const input = document.getElementById('csgateway-widget-input');
      sendMessage(input.value);
      input.value = '';
    }
  });
})();
