const App = {
  currentUser: null,
  activeTab: "chats",
  activeChat: null,
  chats: [],
  contacts: [],
  onlineUsers: new Set(),
  typingTimeout: null,
  mediaRecorder: null,
  audioChunks: [],
  recordingInterval: null,
  recordingSeconds: 0,
  isRecording: false,
  isAttachmentMenuOpen: false,
  isEmojiPickerOpen: false,
  isChatMenuOpen: false,
  activeChatBlockStatus: { is_blocked_by_me: false, am_i_blocked: false },
  unreadCounts: {},
  async init() {
    const savedTheme = localStorage.getItem("fechat_theme") || "dark";
    document.documentElement.setAttribute("data-theme", savedTheme);
    applyTranslations();
    await FechatAPI.initShieldHandshake();
    if ("Notification" in window && Notification.permission === "default") {
      setTimeout(() => {
        Notification.requestPermission().catch(() => {});
      }, 4e3);
    }
    socketClient.on("message", (msg) => this.handleIncomingMessage(msg));
    socketClient.on("presence", (data) => this.handlePresenceUpdate(data));
    socketClient.on("typing", (data) => this.handleTypingUpdate(data));
    socketClient.on("read", (data) => this.handleReadReceipt(data));
    socketClient.on("block", (data) => this.handleBlockUpdate(data));
    socketClient.on("call_signal", (data) =>
      this.handleIncomingCallSignal(data),
    );
    document.addEventListener("click", (e) => {
      if (
        !e.target.closest("#attachment-btn") &&
        !e.target.closest("#attachment-popover")
      ) {
        this.closeAttachmentMenu();
      }
      if (
        !e.target.closest("#emoji-btn") &&
        !e.target.closest("#emoji-popover")
      ) {
        this.closeEmojiPicker();
      }
      if (
        !e.target.closest("#chat-more-btn") &&
        !e.target.closest("#chat-menu-dropdown")
      ) {
        this.closeChatMenu();
      }
      if (!e.target.closest("#chat-context-menu")) {
        this.closeChatContextMenu();
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        const modalContainer = document.getElementById("modal-container");
        if (modalContainer && modalContainer.innerHTML.trim() !== "") {
          this.closeModal();
          return;
        }
        if (
          this.isAttachmentMenuOpen ||
          this.isEmojiPickerOpen ||
          this.isChatMenuOpen ||
          document.getElementById("chat-context-menu")
        ) {
          this.closeAttachmentMenu();
          this.closeEmojiPicker();
          this.closeChatMenu();
          this.closeChatContextMenu();
          return;
        }
        if (this.activeChat) {
          this.closeActiveChat();
          return;
        }
      }
      if (
        (e.ctrlKey || e.metaKey) &&
        (e.key === "k" || e.key === "K" || e.key === "/")
      ) {
        e.preventDefault();
        const searchInput =
          document.getElementById("search-input") ||
          document.getElementById("contacts-search");
        if (searchInput) {
          searchInput.focus();
          searchInput.select();
        }
      }
    });
    window.addEventListener("paste", async (e) => {
      if (!this.activeChat) return;
      const items = (e.clipboardData || e.originalEvent?.clipboardData)?.items;
      if (!items) return;
      for (let item of items) {
        if (item.kind === "file") {
          const file = item.getAsFile();
          if (file) {
            e.preventDefault();
            this.showToast("Enviando arquivo colado...", "info");
            await this.handleMediaUpload(
              file,
              file.type.startsWith("image/") ? "image" : "file",
            );
            break;
          }
        }
      }
    });
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        if (window.socketClient) socketClient.ensureConnected();
        this.syncChatsInBackground();
      }
    });
    window.addEventListener("focus", () => {
      if (window.socketClient) socketClient.ensureConnected();
      this.syncChatsInBackground();
    });
    window.addEventListener("online", () => {
      if (window.socketClient) socketClient.ensureConnected();
      this.syncChatsInBackground();
    });
    if (window.Notification && Notification.permission === "default") {
      try {
        Notification.requestPermission().catch(() => {});
      } catch (_) {}
    }
    if (!this._bgSyncInterval) {
      this._bgSyncInterval = setInterval(() => {
        if (this.currentUser) {
          this.syncChatsInBackground();
        }
      }, 3500);
    }
    window.addEventListener("hashchange", () => this.checkUrlInviteHash());
    const token = FechatAPI.getToken();
    this.initSocketListeners();
    if (token) {
      try {
        this.currentUser = await FechatAPI.getMe();
        if (this.currentUser.language) setLanguage(this.currentUser.language);
        if (this.currentUser.theme) this.setTheme(this.currentUser.theme);
        this.renderApp();
        socketClient.connect(token);
        await this.loadData();
        this.checkUrlInviteHash();
      } catch (err) {
        FechatAPI.clearToken();
        this.renderAuth();
      }
    } else {
      this.renderAuth();
    }
  },
  initSocketListeners() {
    if (this._socketListenersInitialized) return;
    this._socketListenersInitialized = true;
    socketClient.on("onMessage", async (msg) => {
      if (!msg) return;
      let chat = (this.chats || []).find((c) => c.id === msg.chat_id);
      if (!chat) {
        await this.loadData();
        chat = (this.chats || []).find((c) => c.id === msg.chat_id);
      }
      if (chat) {
        chat.last_message = msg;
        chat.updated_at = msg.created_at || new Date().toISOString();
        this.chats.sort(
          (a, b) =>
            new Date(b.updated_at || b.created_at) -
            new Date(a.updated_at || a.created_at),
        );
      }
      if (this.activeChat && this.activeChat.id === msg.chat_id) {
        await this.appendMessageToDOM(msg);
        this.scrollToBottom();
        if (window.FechatAudio) FechatAudio.playReceived();
        FechatAPI.markAsRead(msg.chat_id).catch(() => {});
      } else {
        if (window.FechatAudio) FechatAudio.playReceived();
        this.unreadCounts[msg.chat_id] =
          (this.unreadCounts[msg.chat_id] || 0) + 1;
        this.updateUnreadBadges();
        let senderName =
          (msg.sender && msg.sender.full_name) ||
          (chat && chat.title) ||
          "Novo contato";
        let preview = "Mensagem criptografada";
        if (chat && chat.aes_channel_key) {
          try {
            preview = await FechatCrypto.decrypt(
              msg.ciphertext,
              msg.iv,
              msg.tag,
              chat.aes_channel_key,
            );
            if (["[VOICE]", "[Áudio de voz]"].includes(preview))
              preview = "🎙️ Mensagem de voz";
            else if (["[IMAGE]"].includes(preview)) preview = "📷 Foto";
            else if (["[VIDEO]"].includes(preview)) preview = "🎥 Vídeo";
            else if (["[FILE]"].includes(preview)) preview = "📁 Documento";
          } catch (_) {}
        }
        this.showToast(`📩 ${senderName}: ${preview.slice(0, 45)}`, "info");
        if (
          window.Notification &&
          Notification.permission === "granted" &&
          document.visibilityState !== "visible"
        ) {
          try {
            new Notification(`Fechat: ${senderName}`, {
              body: preview,
              icon: (msg.sender && msg.sender.avatar_url) || "/favicon.ico",
              tag: `chat-${msg.chat_id}`,
            });
          } catch (_) {}
        }
      }
      this.renderSidebarList();
    });
    socketClient.on("onPresence", (data) => {
      if (!data) return;
      const userId = data.user_id;
      const isOnline = data.is_online;
      if (isOnline) {
        this.onlineUsers.add(userId);
      } else {
        this.onlineUsers.delete(userId);
      }
      this.renderSidebarList();
      if (this.activeChat && !this.activeChat.is_group) {
        const members = this.activeChat.members || [];
        const other = members.find((m) => m.user_id === userId);
        if (other) {
          const statusEl = document.getElementById("chat-header-status");
          if (statusEl) {
            statusEl.innerHTML = isOnline
              ? `<span class="online-status-text" style="color:var(--online);">● ${t("online_status")}</span>`
              : `<span class="offline-status-text">${t("offline_status")}</span>`;
          }
        }
      }
    });
    socketClient.on("onTyping", (data) => {
      if (!data) return;
      if (
        this.activeChat &&
        this.activeChat.id === data.chat_id &&
        data.user_id !== this.currentUser.id
      ) {
        const statusEl = document.getElementById("chat-active-status");
        if (statusEl) {
          if (data.is_typing) {
            statusEl.innerHTML =
              '<span class="status-typing-text">● digitando<span class="typing-dots">...</span></span>';
          } else {
            let isRex = this.activeChat.members?.some(
              (m) =>
                m.user?.numeric_id === "100000000003" ||
                m.user?.username === "rexhenrique",
            );
            let isOnline = this.onlineUsers.has(data.user_id) || isRex;
            statusEl.innerHTML = isRex
              ? '<span style="color:#10b981; font-weight:600;">● Online • Amigo IA</span>'
              : isOnline
                ? `<span class="online-status-text" style="color:var(--online);">● ${t("online_status")}</span>`
                : `<span class="offline-status-text">${t("offline_status")}</span>`;
          }
        }
        const container = document.getElementById("messages-container");
        if (container) {
          let bubble = document.getElementById("chat-typing-bubble");
          if (data.is_typing) {
            if (!bubble) {
              bubble = document.createElement("div");
              bubble.id = "chat-typing-bubble";
              bubble.className = "message-row received";
              bubble.innerHTML = `\n                <div class="message-bubble typing-bubble">\n                  <div class="typing-indicator-dots">\n                    <span></span><span></span><span></span>\n                  </div>\n                </div>\n              `;
              container.appendChild(bubble);
            }
            bubble.style.display = "flex";
            this.scrollToBottom();
          } else {
            if (bubble) {
              bubble.remove();
            }
          }
        }
      }
    });
    socketClient.on("onMessagesRead", (data) => {
      if (!data) return;
      if (this.activeChat && this.activeChat.id === data.chat_id) {
        document
          .querySelectorAll(".message-row.sent .tick-icon")
          .forEach((tick) => {
            tick.className = "tick-icon tick-read";
            tick.title = "Lido";
            tick.textContent = "✓✓";
          });
      }
    });
    socketClient.on("onGroupUpdate", async (data) => {
      if (!data) return;
      await this.loadData();
      if (this.activeChat && this.activeChat.id === data.chat_id) {
        const fresh = (this.chats || []).find((c) => c.id === data.chat_id);
        if (fresh) {
          this.activeChat = fresh;
          const titleEl = document.querySelector(".chat-header-details h3");
          if (titleEl && data.title) {
            titleEl.textContent = data.title;
          }
          const membersCountEl = document.getElementById("chat-active-status");
          if (membersCountEl && fresh.members) {
            membersCountEl.textContent = `${fresh.members.length} participantes`;
          }
        }
      }
    });
    socketClient.on("onMessagePinned", async (data) => {
      if (!data) return;
      if (this.activeChat && this.activeChat.id === data.chat_id) {
        this.activeChat.pinned_message_id = data.pinned_message_id;
        this.updatePinnedMessageBanner(data.chat_id, data.pinned_message_id);
      }
    });
    socketClient.on("onMessageDeleted", (data) => {
      if (!data) return;
      const row = document.querySelector(
        `.message-row[data-msg-id="${data.message_id}"]`,
      );
      if (row) {
        const bubble = row.querySelector(".message-bubble");
        if (bubble) {
          bubble.innerHTML = `\n            <div class="msg-text" style="font-style:italic; opacity:0.65; color:var(--text-muted);">\n              🚫 Esta mensagem foi apagada\n            </div>\n            <div class="msg-meta">\n              <span>${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>\n            </div>\n          `;
        }
        const actionBtn = row.querySelector(".message-action-trigger");
        if (actionBtn) actionBtn.remove();
        const reportBtn = row.querySelector(".msg-menu-btn");
        if (reportBtn) reportBtn.remove();
      }
    });
    socketClient.on("onGroupSuspended", (data) => {
      if (!data) return;
      if (this.activeChat && this.activeChat.id === data.chat_id) {
        this.activeChat.is_suspended = true;
        this.activeChat.suspension_reason = data.suspension_reason;
        this.renderChatArea();
      }
      const ch = (this.chats || []).find((c) => c.id === data.chat_id);
      if (ch) {
        ch.is_suspended = true;
        ch.suspension_reason = data.suspension_reason;
        this.renderSidebarList();
      }
      this.showToast(
        "Este grupo foi suspenso por infração dos Termos de Uso.",
        "danger",
      );
    });
  },
  async syncChatsInBackground() {
    if (!this.currentUser) return;
    try {
      const freshChats = await FechatAPI.getChats();
      if (!Array.isArray(freshChats)) return;
      let shouldUpdateSidebar = false;
      if (!this.chats || this.chats.length !== freshChats.length) {
        shouldUpdateSidebar = true;
      }
      for (const fc of freshChats) {
        const local = (this.chats || []).find((c) => c.id === fc.id);
        if (!local) {
          shouldUpdateSidebar = true;
          break;
        }
        if (
          fc.last_message &&
          (!local.last_message || local.last_message.id !== fc.last_message.id)
        ) {
          shouldUpdateSidebar = true;
          local.last_message = fc.last_message;
          local.updated_at = fc.updated_at || fc.last_message.created_at;
          if (this.activeChat && this.activeChat.id === fc.id) {
            const container = document.getElementById("messages-container");
            const exists = container
              ? container.querySelector(
                  `.message-row[data-msg-id="${fc.last_message.id}"]`,
                )
              : null;
            if (!exists) {
              await this.appendMessageToDOM(fc.last_message);
              this.scrollToBottom();
              if (window.FechatAudio) FechatAudio.playReceived();
              FechatAPI.markAsRead(fc.id).catch(() => {});
            }
          }
        }
      }
      if (shouldUpdateSidebar) {
        this.chats = freshChats;
        this.chats.sort(
          (a, b) =>
            new Date(b.updated_at || b.created_at) -
            new Date(a.updated_at || a.created_at),
        );
        this.renderSidebarList();
      }
    } catch (_) {}
  },
  closeModal() {
    const modal = document.getElementById("modal-container");
    if (modal) modal.innerHTML = "";
  },
  closeActiveChat() {
    this.activeChat = null;
    this.activeChatBlockStatus = {
      is_blocked_by_me: false,
      am_i_blocked: false,
    };
    const workspaceEl = document.getElementById("chat-workspace");
    if (workspaceEl) {
      workspaceEl.innerHTML = this.renderActiveWorkspace();
      this.refreshIcons();
    }
    document
      .querySelectorAll(".chat-card.active")
      .forEach((c) => c.classList.remove("active"));
  },
  refreshIcons() {
    setTimeout(() => {
      if (window.lucide) {
        window.lucide.createIcons();
      }
    }, 10);
  },
  setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("fechat_theme", theme);
  },
  showToast(message, type = "info") {
    const modalAlertBox =
      document.getElementById("modal-alert-box") ||
      document.getElementById("auth-alert-box");
    if (modalAlertBox) {
      const alertIcon =
        type === "danger"
          ? "alert-circle"
          : type === "success"
            ? "check-circle"
            : type === "warning"
              ? "alert-triangle"
              : "info";
      modalAlertBox.innerHTML = `\n        <div class="modal-alert-banner ${type}">\n          <i data-lucide="${alertIcon}" style="width:18px; height:18px; flex-shrink:0;"></i>\n          <span>${this.escapeHTML(message)}</span>\n        </div>\n      `;
      this.refreshIcons();
    }
    if (window.Swal) {
      const Toast = Swal.mixin({
        toast: true,
        position: "top",
        showConfirmButton: false,
        timer: 3500,
        timerProgressBar: true,
        background: "#131b2e",
        color: "#f8fafc",
        didOpen: (toast) => {
          toast.addEventListener("mouseenter", Swal.stopTimer);
          toast.addEventListener("mouseleave", Swal.resumeTimer);
        },
      });
      const iconType =
        type === "success"
          ? "success"
          : type === "danger"
            ? "error"
            : type === "warning"
              ? "warning"
              : "info";
      Toast.fire({ icon: iconType, title: message });
      return;
    }
    const container = document.getElementById("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    const icon =
      type === "success"
        ? "check-circle"
        : type === "danger"
          ? "alert-triangle"
          : "message-square";
    toast.innerHTML = `<i data-lucide="${icon}"></i><span>${this.escapeHTML(message)}</span>`;
    container.appendChild(toast);
    this.refreshIcons();
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(-15px)";
      toast.style.transition = "all 0.3s";
      setTimeout(() => toast.remove(), 300);
    }, 3800);
  },
  escapeHTML(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  },
  formatMessageText(plaintext) {
    if (!plaintext) return "";
    const emojiOnlyRegex = /^(\p{Extended_Pictographic}|\s)+$/u;
    const trimmed = plaintext.trim();
    const charCount = Array.from(trimmed.replace(/\s+/g, "")).length;
    if (charCount >= 1 && charCount <= 3 && emojiOnlyRegex.test(trimmed)) {
      return `<div class="msg-text big-emoji">${this.escapeHTML(trimmed)}</div>`;
    }
    const codeBlocks = [];
    let text = plaintext.replace(
      /```([a-zA-Z0-9_\-\.\+]*)\r?\n?([\s\S]*?)```/g,
      (match, lang, code) => {
        const id = `___CODE_BLOCK_${codeBlocks.length}___`;
        const cleanLang = (lang || "code").trim().toLowerCase();
        codeBlocks.push({
          id: id,
          lang: cleanLang,
          code: code.replace(/\r\n/g, "\n").replace(/^\n+|\n+$/g, ""),
        });
        return id;
      },
    );
    const inlineCodes = [];
    text = text.replace(/`([^`\n]+)`/g, (match, inline) => {
      const id = `___INLINE_CODE_${inlineCodes.length}___`;
      inlineCodes.push({ id: id, code: inline });
      return id;
    });
    text = this.escapeHTML(text);
    const urlPattern = /(https?:\/\/[^\s<]+)/g;
    text = text.replace(
      urlPattern,
      '<a href="$1" target="_blank" rel="noopener noreferrer" class="msg-link">$1</a>',
    );
    text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    text = text.replace(
      /(^|[^\w*])\*([^*\s][^*]*[^*\s]|[^*\s])\*(?=[^\w*]|$)/g,
      "$1<strong>$2</strong>",
    );
    text = text.replace(
      /(^|[^\w_])_([^_\s][^_]*[^_\s]|[^_\s])_(?=[^\w_]|$)/g,
      "$1<em>$2</em>",
    );
    text = text.replace(/~~([^~]+)~~/g, "<del>$1</del>");
    text = text.replace(
      /(^|[^\w~])~([^~\s][^~]*[^~\s]|[^~\s])~(?=[^\w~]|$)/g,
      "$1<del>$2</del>",
    );
    const lines = text.split("\n");
    const formattedLines = [];
    let inBlockquote = false;
    let blockquoteBuffer = [];
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (line.startsWith("&gt; ") || line.startsWith("&gt;")) {
        const content = line.replace(/^&gt;\s?/, "");
        blockquoteBuffer.push(content);
        inBlockquote = true;
      } else {
        if (inBlockquote) {
          formattedLines.push(
            `<div class="msg-blockquote">${blockquoteBuffer.join("<br>")}</div>`,
          );
          blockquoteBuffer = [];
          inBlockquote = false;
        }
        formattedLines.push(line);
      }
    }
    if (inBlockquote) {
      formattedLines.push(
        `<div class="msg-blockquote">${blockquoteBuffer.join("<br>")}</div>`,
      );
    }
    text = formattedLines.join("\n");
    text = text.replace(/\n/g, "<br>");
    for (const item of inlineCodes) {
      const safeCode = this.escapeHTML(item.code);
      text = text.replace(
        item.id,
        `<code class="msg-inline-code">${safeCode}</code>`,
      );
    }
    for (const item of codeBlocks) {
      const safeCode = this.escapeHTML(item.code);
      const safeLang = this.escapeHTML(item.lang);
      const blockHTML = `\n        <div class="msg-code-container">\n          <div class="msg-code-header">\n            <span class="msg-code-lang">${safeLang || "código"}</span>\n            <button type="button" class="msg-code-copy-btn" onclick="App.copyCodeBlock(this)" title="Copiar código">\n              <i data-lucide="copy" style="width:12px; height:12px;"></i>\n              <span>Copiar</span>\n            </button>\n          </div>\n          <pre class="msg-code-block"><code>${safeCode}</code></pre>\n        </div>\n      `;
      text = text.replace(item.id, blockHTML);
    }
    return `<div class="msg-text">${text}</div>`;
  },
  copyCodeBlock(btn) {
    if (!btn) return;
    const container = btn.closest(".msg-code-container");
    const codeEl = container ? container.querySelector("code") : null;
    if (!codeEl) return;
    const textToCopy = codeEl.textContent;
    navigator.clipboard
      .writeText(textToCopy)
      .then(() => {
        const span = btn.querySelector("span");
        if (span) span.textContent = "Copiado!";
        btn.style.borderColor = "#10b981";
        btn.style.color = "#10b981";
        if (window.FechatAudio) FechatAudio.playTick();
        setTimeout(() => {
          if (span) span.textContent = "Copiar";
          btn.style.borderColor = "";
          btn.style.color = "";
        }, 2e3);
      })
      .catch(() => {
        App.showToast(
          "Código copiado para a área de transferência!",
          "success",
        );
      });
  },
  getAuthorColor(userId, userName) {
    const colors = [
      "#38bdf8",
      "#818cf8",
      "#a855f7",
      "#ec4899",
      "#f43f5e",
      "#fb923c",
      "#facc15",
      "#4ade80",
      "#2dd4bf",
      "#22d3ee",
      "#60a5fa",
      "#c084fc",
    ];
    const key = String(userId || userName || "user");
    let hash = 0;
    for (let i = 0; i < key.length; i++) {
      hash = key.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
  },
  renderTicksHTML(status) {
    if (status === "read") {
      return '<span class="tick-icon tick-read" title="Lido">✓✓</span>';
    }
    if (status === "delivered") {
      return '<span class="tick-icon" title="Entregue">✓✓</span>';
    }
    return '<span class="tick-icon" title="Enviado">✓</span>';
  },
  renderChatArea() {
    if (!this.activeChat) return;
    const workspace = document.getElementById("primary-workspace");
    if (workspace) {
      workspace.innerHTML = this.renderChatWindowHTML();
      this.refreshIcons();
    }
  },
  formatId(idStr) {
    if (!idStr) return "";
    const clean = String(idStr).replace(/\D/g, "");
    if (clean.length === 12) {
      return `${clean.slice(0, 4)}-${clean.slice(4, 8)}-${clean.slice(8, 12)}`;
    }
    return idStr;
  },
  async loadData() {
    try {
      this.chats = await FechatAPI.getChats();
      this.contacts = await FechatAPI.getContacts();
      this.renderSidebarList();
    } catch (e) {
      console.error("Erro ao carregar dados:", e);
    }
  },
  async loadInitialData() {
    return this.loadData();
  },
  renderAuth(isRegister = false) {
    const root = document.getElementById("app-root");
    root.innerHTML = `\n      <div style="display:flex; align-items:center; justify-content:center; width:100%; height:100vh; padding:20px;">\n        <div class="modal-content" style="max-width:440px; transform:none; opacity:1;">\n          <div style="text-align:center; margin-bottom:10px;">\n            <div class="brand-logo" style="margin:0 auto 14px; width:56px; height:56px;">\n              <i data-lucide="message-circle" style="width:28px; height:28px;"></i>\n            </div>\n            <h2 style="font-size:22px; font-weight:800; font-family:var(--font-heading);">${isRegister ? t("register_title") : t("login_title")}</h2>\n            <p style="color:var(--text-muted); font-size:13px; margin-top:4px;">${isRegister ? t("register_desc") : t("tagline")}</p>\n          </div>\n\n          <div id="auth-alert-box"></div>\n\n          <form id="auth-form" onsubmit="App.handleAuthSubmit(event, ${isRegister})" style="display:flex; flex-direction:column; gap:14px;">\n            ${isRegister ? `\n              <div class="form-group">\n                <label class="form-label">${t("full_name_label")}</label>\n                <input type="text" id="auth-fullname" class="form-input" placeholder="Ex: Carlos Silva" required />\n              </div>\n              <div class="form-group">\n                <label class="form-label">${t("username_label")}</label>\n                <input type="text" id="auth-username" class="form-input" placeholder="carlos_silva" required />\n              </div>\n            ` : ""}\n\n            <div class="form-group">\n              <label class="form-label">${isRegister ? t("email_label") : t("identifier_input_label")}</label>\n              <input type="text" id="auth-login" class="form-input" placeholder="${isRegister ? "seu@email.com" : "ID, @usuario ou e-mail"}" required />\n            </div>\n\n            <div class="form-group">\n              <label class="form-label">${t("password_label")}</label>\n              <input type="password" id="auth-password" class="form-input" placeholder="Sua senha" required />\n            </div>\n\n            <button type="submit" class="btn-primary" style="margin-top:6px;">\n              ${isRegister ? t("register_btn") : t("login_btn")}\n            </button>\n\n            <div style="text-align:center; font-size:13px; margin-top:8px;">\n              <a href="#" onclick="App.renderAuth(${!isRegister}); return false;" style="color:var(--primary); text-decoration:none; font-weight:500;">\n                ${isRegister ? t("already_have_account") : t("dont_have_account")}\n              </a>\n            </div>\n          </form>\n\n          <div style="display:flex; justify-content:center; gap:12px; margin-top:10px; border-top:1px solid var(--border-glass); padding-top:14px;">\n            <button onclick="setLanguage('pt_BR'); App.renderAuth(${isRegister})" style="background:none; border:none; color:var(--text-muted); cursor:pointer; font-size:12px;">🇧🇷 Português</button>\n            <span style="color:var(--border-glass)">|</span>\n            <button onclick="setLanguage('en_US'); App.renderAuth(${isRegister})" style="background:none; border:none; color:var(--text-muted); cursor:pointer; font-size:12px;">🇺🇸 English</button>\n          </div>\n        </div>\n      </div>\n    `;
    this.refreshIcons();
  },
  async handleAuthSubmit(e, isRegister) {
    e.preventDefault();
    try {
      if (isRegister) {
        const fullName = document.getElementById("auth-fullname").value;
        const username = document.getElementById("auth-username").value;
        const email = document.getElementById("auth-login").value;
        const password = document.getElementById("auth-password").value;
        const res = await FechatAPI.register(
          fullName,
          username,
          email,
          password,
        );
        FechatAPI.setToken(res.access_token);
        this.currentUser = res.user;
        this.showToast(
          `Bem-vindo(a), ${res.user.full_name}! Seu ID único é: ${this.formatId(res.user.numeric_id)}`,
          "success",
        );
      } else {
        const loginId = document.getElementById("auth-login").value;
        const password = document.getElementById("auth-password").value;
        const res = await FechatAPI.login(loginId, password);
        FechatAPI.setToken(res.access_token);
        this.currentUser = res.user;
        this.showToast(`Olá novamente, ${res.user.full_name}!`, "success");
      }
      this.renderApp();
      socketClient.connect(FechatAPI.getToken());
      await this.loadData();
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  async logout() {
    if (window.Swal) {
      const result = await Swal.fire({
        title: "Sair da Conta?",
        text: "Deseja encerrar sua sessão segura no Fechat?",
        icon: "question",
        showCancelButton: true,
        confirmButtonColor: "#6366f1",
        cancelButtonColor: "#475569",
        confirmButtonText: "Sim, Sair",
        cancelButtonText: "Cancelar",
      });
      if (!result.isConfirmed) return;
    }
    FechatAPI.clearToken();
    this.currentUser = null;
    this.chats = [];
    this.contacts = [];
    this.activeChat = null;
    socketClient.stopPing();
    this.renderAuth();
  },
  updateUnreadBadges() {
    const totalUnread = Object.values(this.unreadCounts).reduce(
      (a, b) => a + b,
      0,
    );
    if (totalUnread > 0) {
      document.title = `(${totalUnread}) Fechat - Comunicação Segura`;
    } else {
      document.title = `Fechat - Comunicação Segura`;
    }
    const badgeEl = document.getElementById("nav-chats-badge");
    if (badgeEl) {
      badgeEl.style.display = totalUnread > 0 ? "flex" : "none";
      badgeEl.textContent = totalUnread > 99 ? "99+" : totalUnread;
    }
  },
  renderApp() {
    const root = document.getElementById("app-root");
    const isAdmin = this.currentUser && this.currentUser.is_admin;
    const avatarUrl =
      this.currentUser.avatar_url ||
      `https://api.dicebear.com/7.x/bottts/svg?seed=${this.currentUser.username}`;
    const totalUnread = Object.values(this.unreadCounts).reduce(
      (a, b) => a + b,
      0,
    );
    root.innerHTML = `\n      \x3c!-- BARRA DE NAVEGAÇÃO LATERAL --\x3e\n      <nav class="sidebar-nav">\n        <div class="brand-logo" onclick="App.switchTab('chats')" title="Fechat">\n          <i data-lucide="message-circle" style="width:24px; height:24px;"></i>\n        </div>\n        \n        <div class="nav-tabs">\n          <button class="nav-tab-btn ${this.activeTab === "chats" ? "active" : ""}" onclick="App.switchTab('chats')" title="${t("nav_chats")}" style="position:relative;">\n            <i data-lucide="message-square"></i>\n            <span id="nav-chats-badge" class="nav-tab-badge" style="display:${totalUnread > 0 ? "flex" : "none"};">\n              ${totalUnread > 99 ? "99+" : totalUnread}\n            </span>\n          </button>\n          <button class="nav-tab-btn ${this.activeTab === "contacts" ? "active" : ""}" onclick="App.switchTab('contacts')" title="${t("nav_contacts")}">\n            <i data-lucide="users"></i>\n          </button>\n          <button class="nav-tab-btn ${this.activeTab === "groups" ? "active" : ""}" onclick="App.switchTab('groups')" title="${t("nav_groups")}">\n            <i data-lucide="hash"></i>\n          </button>\n          <button class="nav-tab-btn ${this.activeTab === "profile" ? "active" : ""}" onclick="App.switchTab('profile')" title="${t("nav_profile")}">\n            <i data-lucide="user"></i>\n          </button>\n          <button class="nav-tab-btn ${this.activeTab === "settings" ? "active" : ""}" onclick="App.switchTab('settings')" title="${t("nav_settings")}">\n            <i data-lucide="settings"></i>\n          </button>\n          \n          ${isAdmin ? `\n            <button class="nav-tab-btn ${this.activeTab === "compliance" ? "active" : ""}" onclick="App.switchTab('compliance')" title="${t("nav_compliance")}" style="color:var(--danger);">\n              <i data-lucide="scale"></i>\n            </button>\n          ` : ""}\n        </div>\n\n        <div class="sidebar-bottom">\n          <img src="${avatarUrl}" class="avatar-nav" onclick="App.switchTab('profile')" title="${this.currentUser.full_name}" />\n        </div>\n      </nav>\n\n      \x3c!-- CONTAINER PRINCIPAL --\x3e\n      ${(() => {
      const isWorkspaceActive = Boolean(
        this.activeChat ||
        this.activeTab === "profile" ||
        this.activeTab === "settings" ||
        this.activeTab === "compliance",
      );
      return `\n          <div class="app-container ${isWorkspaceActive ? "workspace-active" : "sidebar-active"}" id="main-content-container">\n            \x3c!-- COLUNA SECUNDÁRIA --\x3e\n            <aside class="panel-sidebar" id="panel-sidebar">\n              <div class="panel-header">\n                <div class="panel-title-bar">\n                  <h2 class="panel-title" id="panel-title-heading">${t("nav_" + this.activeTab)}</h2>\n                  <div id="panel-action-btn-container"></div>\n                </div>\n                <div class="search-wrapper">\n                  <span class="search-icon"><i data-lucide="search" style="width:16px; height:16px;"></i></span>\n                  <input type="text" id="panel-search-input" class="search-input" placeholder="${t("search_placeholder")}" oninput="App.handleSearch(this.value)" />\n                </div>\n              </div>\n\n              <div class="items-scroll" id="sidebar-items-list">\n                \x3c!-- Itens dinâmicos --\x3e\n              </div>\n            </aside>\n\n            \x3c!-- ÁREA PRINCIPAL --\x3e\n            <main class="chat-main-panel" id="primary-workspace">\n              ${this.renderActiveWorkspace()}\n            </main>\n          </div>\n        `;
    })()}\n\n      \x3c!-- MODAIS E POPUPS --\x3e\n      <div id="modal-container"></div>\n      <div class="toast-container" id="toast-container"></div>\n    `;
    this.refreshIcons();
    this.renderSidebarList();
  },
  switchTab(tabKey) {
    this.activeTab = tabKey;
    document
      .querySelectorAll(".nav-tab-btn")
      .forEach((btn) => btn.classList.remove("active"));
    this.renderApp();
  },
  async renderSidebarList() {
    const listEl = document.getElementById("sidebar-items-list");
    const actionContainer = document.getElementById(
      "panel-action-btn-container",
    );
    const heading = document.getElementById("panel-title-heading");
    if (!listEl) return;
    listEl.innerHTML = "";
    if (heading) heading.textContent = t("nav_" + this.activeTab);
    if (this.activeTab === "chats") {
      actionContainer.innerHTML = `\n        <button class="btn-icon" onclick="App.openNewChatModal()" title="${t("new_chat_btn")}">\n          <i data-lucide="plus"></i>\n        </button>\n      `;
      if (this.chats.length === 0) {
        listEl.innerHTML = `\n          <div class="empty-state">\n            <div class="empty-state-icon"><i data-lucide="message-square" style="width:40px; height:40px;"></i></div>\n            <p style="font-size:13px;">Nenhuma conversa aberta.<br>Inicie uma nova conversa!</p>\n            <button class="btn-primary" onclick="App.openNewChatModal()" style="font-size:12px; padding:8px 14px;">${t("new_chat_btn")}</button>\n          </div>\n        `;
        this.refreshIcons();
        return;
      }
      for (const chat of this.chats) {
        const card = document.createElement("div");
        const isActive = this.activeChat && this.activeChat.id === chat.id;
        card.className = `chat-card ${isActive ? "active" : ""}`;
        let chatTitle = chat.title;
        let avatarUrl =
          chat.avatar_url ||
          `https://api.dicebear.com/7.x/bottts/svg?seed=${chat.title || "group"}`;
        let isOnline = false;
        let isVerified = false;
        let isBot = false;
        let isRexCompanion = false;
        let isReadOnlyBot = false;
        let isSuspended = false;
        if (!chat.is_group) {
          const members = chat.members || [];
          const otherMember = members.find(
            (m) => m.user_id !== this.currentUser.id,
          );
          if (otherMember && otherMember.user) {
            chatTitle = otherMember.user.full_name;
            avatarUrl =
              otherMember.user.avatar_url ||
              `https://api.dicebear.com/7.x/bottts/svg?seed=${otherMember.user.username}`;
            isOnline = this.onlineUsers.has(otherMember.user_id);
            isVerified = Boolean(otherMember.user.is_verified);
            isBot = Boolean(otherMember.user.is_bot);
            isSuspended = Boolean(
              otherMember.user.is_suspended ||
              otherMember.user.is_active === false,
            );
            if (
              otherMember.user.numeric_id === "100000000003" ||
              otherMember.user.username === "rexhenrique"
            ) {
              isRexCompanion = true;
              isOnline = true;
            } else if (
              otherMember.user.numeric_id === "100000000000" ||
              otherMember.user.numeric_id === "100000000002" ||
              otherMember.user.username === "fechat_oficial" ||
              otherMember.user.username === "fechat_compliance"
            ) {
              isReadOnlyBot = true;
            }
          }
        } else {
          if (chat.is_suspended) {
            isSuspended = true;
          }
        }
        let previewText = "Conversa criptografada com AES-256";
        if (isSuspended) {
          previewText = chat.is_group
            ? '<span style="color:#ef4444; font-weight:500;">🚫 Grupo suspenso por infração aos termos</span>'
            : '<span style="color:#ef4444; font-weight:500;">🚫 Conta suspensa por infração aos termos</span>';
        } else if (chat.last_message) {
          if (chat.last_message.message_type === "image") {
            previewText = "📷 Foto";
          } else if (chat.last_message.message_type === "video") {
            previewText = "🎥 Vídeo";
          } else if (chat.last_message.message_type === "voice") {
            previewText = "🎙️ Áudio de voz";
          } else if (chat.last_message.message_type === "audio") {
            previewText = "🎵 Música / Áudio";
          } else if (chat.last_message.message_type === "file") {
            previewText = `📁 ${chat.last_message.media_name || "Arquivo"}`;
          } else {
            try {
              previewText = await FechatCrypto.decrypt(
                chat.last_message.ciphertext,
                chat.last_message.iv,
                chat.last_message.tag,
                chat.aes_channel_key,
              );
              if (previewText && previewText.startsWith("CALL_LOG:")) {
                try {
                  const logData = JSON.parse(
                    previewText.replace("CALL_LOG:", ""),
                  );
                  const status = logData.call_status || "ended";
                  const durSecs = logData.duration || 0;
                  const mins = String(Math.floor(durSecs / 60)).padStart(
                    2,
                    "0",
                  );
                  const secs = String(durSecs % 60).padStart(2, "0");
                  if (status === "ended") {
                    previewText =
                      durSecs > 0
                        ? `📞 Chamada de voz (${mins}:${secs})`
                        : `📞 Chamada de voz finalizada`;
                  } else if (status === "missed") {
                    previewText = `📵 Chamada perdida`;
                  } else if (status === "rejected") {
                    previewText = `📵 Chamada recusada`;
                  } else {
                    previewText = `📞 Chamada de voz`;
                  }
                } catch (_) {
                  previewText = `📞 Chamada de voz`;
                }
              }
            } catch {
              previewText = "🔒 Mensagem criptografada";
            }
          }
        }
        const unread = this.unreadCounts[chat.id] || 0;
        card.onclick = () => App.openChat(chat);
        card.oncontextmenu = (e) => {
          e.preventDefault();
          App.openChatContextMenu(e, chat);
        };
        card.innerHTML = `\n          <div class="avatar-wrapper">\n            <img src="${avatarUrl}" class="avatar-img" />\n            <div class="${isSuspended ? "blocked-dot" : isOnline ? "online-dot" : "offline-dot"}"></div>\n          </div>\n          <div class="chat-card-info">\n            <div class="chat-card-top">\n              <span class="chat-card-name">\n                ${chatTitle}\n                ${isSuspended ? '<span class="bot-tag" style="background:rgba(239, 68, 68, 0.2); color:#fca5a5; border-color:rgba(239, 68, 68, 0.4);">SUSPENSO</span>' : ""}\n                ${!isSuspended && isVerified ? '<span class="verified-badge" title="Verificado Oficial"><i data-lucide="badge-check"></i></span>' : ""}\n                ${!isSuspended && isRexCompanion ? '<span class="bot-tag" style="background:rgba(99, 102, 241, 0.2); color:#a5b4fc; border-color:rgba(99, 102, 241, 0.4);">AMIGO IA</span>' : !isSuspended && isReadOnlyBot ? '<span class="bot-tag">OFICIAL</span>' : ""}\n              </span>\n              <div style="display:flex; align-items:center; gap:5px;">\n                ${chat.is_pinned ? '<span title="Conversa Fixada" style="font-size:12px;">📌</span>' : ""}\n                ${chat.is_muted ? '<span title="Notificações Silenciadas" style="font-size:12px;">🔕</span>' : ""}\n                ${chat.is_archived ? '<span title="Conversa Arquivada" style="font-size:12px;">📁</span>' : ""}\n                ${unread > 0 ? `<span class="unread-badge">${unread}</span>` : ""}\n                <span style="font-size:11px; color:var(--text-dim);">${chat.is_group ? "📢" : "🔒"}</span>\n              </div>\n            </div>\n            <div class="chat-card-preview">\n              ${previewText}\n            </div>\n          </div>\n        `;
        listEl.appendChild(card);
      }
    } else if (this.activeTab === "contacts") {
      actionContainer.innerHTML = `\n        <button class="btn-icon" onclick="App.openAddContactModal()" title="${t("add_contact_btn")}">\n          <i data-lucide="user-plus"></i>\n        </button>\n      `;
      if (this.contacts.length === 0) {
        listEl.innerHTML = `\n          <div class="empty-state">\n            <div class="empty-state-icon"><i data-lucide="users" style="width:40px; height:40px;"></i></div>\n            <p style="font-size:13px;">Sua lista de contatos está vazia.<br>Adicione pessoas pelo ID de 12 dígitos!</p>\n            <button class="btn-primary" onclick="App.openAddContactModal()" style="font-size:12px; padding:8px 14px;">${t("add_contact_btn")}</button>\n          </div>\n        `;
        this.refreshIcons();
        return;
      }
      this.contacts.forEach((contact) => {
        const card = document.createElement("div");
        card.className = "chat-card";
        const isSuspended = Boolean(
          contact.contact_user.is_suspended ||
          contact.contact_user.is_active === false,
        );
        const isOnline = this.onlineUsers.has(contact.contact_user.id);
        const displayName = contact.nickname || contact.contact_user.full_name;
        const avatarUrl =
          contact.contact_user.avatar_url ||
          `https://api.dicebear.com/7.x/bottts/svg?seed=${contact.contact_user.username}`;
        const isVerified = Boolean(contact.contact_user.is_verified);
        const isBot = Boolean(contact.contact_user.is_bot);
        card.innerHTML = `\n          <div class="avatar-wrapper">\n            <img src="${avatarUrl}" class="avatar-img" />\n            <div class="${isSuspended ? "blocked-dot" : isOnline ? "online-dot" : "offline-dot"}"></div>\n          </div>\n          <div class="chat-card-info">\n            <div class="chat-card-top">\n              <span class="chat-card-name">\n                ${displayName}\n                ${isSuspended ? '<span class="bot-tag" style="background:rgba(239, 68, 68, 0.2); color:#fca5a5; border-color:rgba(239, 68, 68, 0.4);">SUSPENSO</span>' : ""}\n                ${!isSuspended && isVerified ? '<span class="verified-badge" title="Verificado Oficial"><i data-lucide="badge-check"></i></span>' : ""}\n                ${!isSuspended && isBot ? '<span class="bot-tag">OFICIAL</span>' : ""}\n              </span>\n              <span class="id-badge">${this.formatId(contact.contact_user.numeric_id)}</span>\n            </div>\n            <div class="chat-card-preview" style="font-size:11.5px;">\n              ${isSuspended ? '<span style="color:#ef4444; font-weight:500;">🚫 Conta suspensa por infração aos termos</span>' : contact.is_blocked ? '<span style="color:#ef4444; font-weight:600;">🚫 Bloqueado</span>' : `@${contact.contact_user.username} • ${formatLastSeen(contact.contact_user.last_seen, isOnline)}`}\n            </div>\n          </div>\n        `;
        if (isSuspended) {
          card.onclick = () =>
            App.showToast(
              "Esta conta foi suspensa por infração aos termos de uso.",
              "danger",
            );
        } else {
          card.onclick = () => App.startDirectChatWith(contact.contact_user.id);
        }
        listEl.appendChild(card);
      });
    } else if (this.activeTab === "groups") {
      actionContainer.innerHTML = `\n        <button class="btn-icon" onclick="App.openCreateGroupModal()" title="${t("new_group_btn")}">\n          <i data-lucide="plus"></i>\n        </button>\n      `;
      const groupChats = this.chats.filter((c) => c.is_group);
      if (groupChats.length === 0) {
        listEl.innerHTML = `\n          <div class="empty-state">\n            <div class="empty-state-icon"><i data-lucide="hash" style="width:40px; height:40px;"></i></div>\n            <p style="font-size:13px;">Você ainda não participa de grupos.<br>Crie um grupo protegido agora!</p>\n            <button class="btn-primary" onclick="App.openCreateGroupModal()" style="font-size:12px; padding:8px 14px;">${t("new_group_btn")}</button>\n          </div>\n        `;
        this.refreshIcons();
        return;
      }
      groupChats.forEach((grp) => {
        const card = document.createElement("div");
        const isActive = this.activeChat && this.activeChat.id === grp.id;
        card.className = `chat-card ${isActive ? "active" : ""}`;
        card.onclick = () => App.openChat(grp);
        card.innerHTML = `\n          <div class="avatar-wrapper">\n            <img src="${grp.avatar_url || "https://api.dicebear.com/7.x/bottts/svg?seed=" + grp.title}" class="avatar-img" />\n          </div>\n          <div class="chat-card-info">\n            <div class="chat-card-top">\n              <span class="chat-card-name">${grp.title}</span>\n              <span class="id-badge">📢 Grupo</span>\n            </div>\n            <div class="chat-card-preview">\n              ${grp.description || "Grupo privado protegido"}\n            </div>\n          </div>\n        `;
        listEl.appendChild(card);
      });
    } else {
      actionContainer.innerHTML = "";
      listEl.innerHTML = `\n        <div style="padding:16px; color:var(--text-muted); font-size:13px;">\n          Selecione uma opção na tela principal.\n        </div>\n      `;
    }
    this.refreshIcons();
  },
  closeActiveChat() {
    this.activeChat = null;
    this.activeTab = "chats";
    this.renderApp();
  },
  goBack() {
    this.activeChat = null;
    this.activeTab = "chats";
    this.renderApp();
  },
  renderActiveWorkspace() {
    if (this.activeTab === "profile") return this.renderProfileView();
    if (this.activeTab === "settings") return this.renderSettingsView();
    if (this.activeTab === "compliance") return this.renderComplianceView();
    if (this.activeChat) {
      return this.renderChatWindowHTML();
    }
    return `\n      <div class="empty-state">\n        <div class="brand-logo" style="width:72px; height:72px; margin-bottom:10px;">\n          <i data-lucide="message-circle" style="width:36px; height:36px;"></i>\n        </div>\n        <h2 style="font-size:24px; font-weight:700; font-family:var(--font-heading);">Fechat Web</h2>\n        <p style="color:var(--text-muted); max-width:440px; font-size:14px; line-height:1.5;">\n          ${t("e2ee_notice")}\n        </p>\n        <div style="margin-top:16px; display:flex; gap:12px;">\n          <button class="btn-primary" onclick="App.openNewChatModal()">${t("new_chat_btn")}</button>\n          <button class="btn-secondary" onclick="App.openAddContactModal()">${t("add_contact_btn")}</button>\n        </div>\n      </div>\n    `;
  },
  renderChatWindowHTML() {
    let chatTitle = this.activeChat.title;
    let avatarUrl =
      this.activeChat.avatar_url ||
      `https://api.dicebear.com/7.x/bottts/svg?seed=${this.activeChat.title || "group"}`;
    let isOnline = false;
    let targetNumericId = "";
    let otherUser = null;
    let isVerified = false;
    let isBot = false;
    let isRexCompanion = false;
    let isReadOnlyBot = false;
    if (!this.activeChat.is_group) {
      const members = this.activeChat.members || [];
      const other = members.find((m) => m.user_id !== this.currentUser.id);
      if (other && other.user) {
        otherUser = other.user;
        chatTitle = other.user.full_name;
        avatarUrl =
          other.user.avatar_url ||
          `https://api.dicebear.com/7.x/bottts/svg?seed=${other.user.username}`;
        isOnline = this.onlineUsers.has(other.user.id);
        targetNumericId = other.user.numeric_id;
        isVerified = Boolean(other.user.is_verified);
        isBot = Boolean(other.user.is_bot);
        if (
          other.user.numeric_id === "100000000003" ||
          other.user.username === "rexhenrique"
        ) {
          isRexCompanion = true;
          isOnline = true;
        } else if (
          other.user.numeric_id === "100000000000" ||
          other.user.numeric_id === "100000000002" ||
          other.user.username === "fechat_oficial" ||
          other.user.username === "fechat_compliance"
        ) {
          isReadOnlyBot = true;
        }
      }
    }
    const isBlockedByMe =
      this.activeChatBlockStatus && this.activeChatBlockStatus.is_blocked_by_me;
    const amIBlocked =
      this.activeChatBlockStatus && this.activeChatBlockStatus.am_i_blocked;
    const isGroupSuspended = Boolean(
      this.activeChat.is_group && this.activeChat.is_suspended,
    );
    const isTargetSuspended =
      (this.activeChatBlockStatus &&
        this.activeChatBlockStatus.is_target_suspended) ||
      (otherUser && (otherUser.is_suspended || otherUser.is_active === false));
    let statusText = "";
    if (isGroupSuspended) {
      statusText = `<span style="color:#ef4444; font-weight:700;">🚫 Grupo Suspenso por Infração</span>`;
    } else if (this.activeChat.is_group) {
      const members = this.activeChat.members || [];
      statusText = `${members.length} participantes`;
    } else if (isTargetSuspended) {
      statusText = `<span style="color:#ef4444; font-weight:700;">🚫 Conta Suspensa por Infração</span>`;
    } else if (isRexCompanion) {
      statusText = `<span style="color:#10b981; font-weight:600;">● Online • Amigo IA</span>`;
    } else if (isReadOnlyBot) {
      statusText = `<span style="color:#38bdf8; font-weight:600;">🛡️ Canal Oficial e Informativo</span>`;
    } else if (amIBlocked) {
      statusText = `<span style="color:#ef4444; font-weight:600;">⚠️ Bloqueado</span>`;
    } else if (isBlockedByMe) {
      statusText = `<span style="color:#f59e0b; font-weight:600;">🚫 Contato Bloqueado por você</span>`;
    } else {
      statusText = formatLastSeen(
        otherUser ? otherUser.last_seen : null,
        isOnline,
      );
    }
    const isProtected =
      isReadOnlyBot ||
      isVerified ||
      isTargetSuspended ||
      isGroupSuspended ||
      (otherUser && otherUser.is_admin);
    const isGroupOnlyAdminsSend = Boolean(
      this.activeChat.is_group &&
      this.activeChat.only_admins_send_messages &&
      this.activeChat.my_role !== "admin",
    );
    return `\n      \x3c!-- CABEÇALHO DO CHAT --\x3e\n      <div class="chat-top-header">\n        <div class="chat-header-user" onclick="App.handleChatHeaderClick()" style="cursor:${this.activeChat.is_group ? "pointer" : "default"};">\n          <button class="btn-icon mobile-back-btn" onclick="event.stopPropagation(); App.closeActiveChat()" title="Voltar para conversas">\n            <i data-lucide="arrow-left"></i>\n          </button>\n          <div class="avatar-wrapper" style="width:42px; height:42px;">\n            <img src="${avatarUrl}" class="avatar-img" />\n            ${!this.activeChat.is_group && !amIBlocked && !isReadOnlyBot && !isTargetSuspended ? `<div class="${isOnline ? "online-dot" : "offline-dot"}"></div>` : ""}\n            ${isTargetSuspended || isGroupSuspended ? `<div class="blocked-dot"></div>` : ""}\n          </div>\n          <div class="chat-header-details">\n            <h3>\n              ${chatTitle}\n              ${isTargetSuspended || isGroupSuspended ? '<span class="bot-tag" style="background:rgba(239, 68, 68, 0.2); color:#fca5a5; border-color:rgba(239, 68, 68, 0.4);">SUSPENSO</span>' : ""}\n              ${!isTargetSuspended && !isGroupSuspended && isVerified ? '<span class="verified-badge" title="Verificado Oficial"><i data-lucide="badge-check"></i></span>' : ""}\n              ${!isTargetSuspended && !isGroupSuspended && isRexCompanion ? '<span class="bot-tag" style="background:rgba(99, 102, 241, 0.2); color:#a5b4fc; border-color:rgba(99, 102, 241, 0.4);">AMIGO IA</span>' : !isTargetSuspended && !isGroupSuspended && isReadOnlyBot ? '<span class="bot-tag">OFICIAL</span>' : ""}\n              ${targetNumericId ? `<span class="id-badge">${this.formatId(targetNumericId)}</span>` : ""}\n              ${this.activeChat.is_group ? '<span class="id-badge" style="background:rgba(99, 102, 241, 0.2); color:#a5b4fc;"><i data-lucide="info" style="width:10px; height:10px; margin-right:2px;"></i> Dados</span>' : ""}\n            </h3>\n            <div class="chat-header-status" id="chat-active-status">\n              ${statusText}\n            </div>\n          </div>\n        </div>\n\n        <div class="chat-header-actions" style="position:relative; display:flex; align-items:center; gap:6px;">\n          ${!this.activeChat.is_group && otherUser && !isReadOnlyBot && !isTargetSuspended && !isGroupSuspended ? `\n            <button class="btn-call-trigger" onclick="App.startVoiceCallFromChat()" title="Iniciar Chamada de Voz Criptografada">\n              <i data-lucide="phone" style="width:16px; height:16px;"></i>\n            </button>\n          ` : ""}\n\n          ${!isProtected && !this.activeChat.is_group ? `\n            <button class="btn-icon" onclick="App.openReportModal()" title="${t("report_modal_title")}" style="color:var(--danger);">\n              <i data-lucide="shield-alert"></i>\n            </button>\n          ` : ""}\n          \n          <button class="btn-icon" id="chat-more-btn" onclick="App.toggleChatMenu(event)" title="Mais Opções">\n            <i data-lucide="more-vertical"></i>\n          </button>\n\n          \x3c!-- BOTAO PARA FECHAR CONVERSA ATIVA (COMO NO WHATSAPP WEB) --\x3e\n          <button class="btn-icon" onclick="App.closeActiveChat()" title="Fechar conversa (Esc)" style="color:var(--text-muted);">\n            <i data-lucide="x"></i>\n          </button>\n\n          \x3c!-- MENU DROPDOWN DE OPÇÕES DO CHAT --\x3e\n          <div id="chat-menu-dropdown" class="chat-menu-dropdown" style="display:${this.isChatMenuOpen ? "flex" : "none"};">\n            ${this.activeChat.is_group ? `\n              <button class="chat-menu-item" onclick="App.closeChatMenu(); App.openGroupInfoModal(${this.activeChat.id})">\n                <i data-lucide="info" style="width:15px; height:15px; color:#38bdf8;"></i>\n                <span>Dados do Grupo</span>\n              </button>\n              ${this.activeChat.my_role === "admin" && !isGroupSuspended ? `\n                <button class="chat-menu-item" onclick="App.closeChatMenu(); App.openGroupInviteLinkModal(${this.activeChat.id})">\n                  <i data-lucide="link" style="width:15px; height:15px; color:var(--primary);"></i>\n                  <span>Convidar via Link</span>\n                </button>\n              ` : ""}\n              <button class="chat-menu-item" onclick="App.handleExportChatJson(${this.activeChat.id})">\n                <i data-lucide="download" style="width:15px; height:15px;"></i>\n                <span>Exportar Conversa (JSON)</span>\n              </button>\n              <button class="chat-menu-item danger" onclick="App.closeChatMenu(); App.openReportModal(null, null, null, ${this.activeChat.id})">\n                <i data-lucide="alert-triangle" style="width:15px; height:15px;"></i>\n                <span>Denunciar Grupo</span>\n              </button>\n              <button class="chat-menu-item danger" onclick="App.handleDeleteChat(${this.activeChat.id}, true)">\n                <i data-lucide="log-out" style="width:15px; height:15px;"></i>\n                <span>Sair do Grupo</span>\n              </button>\n            ` : `\n              ${!this.activeChat.is_group && otherUser && !isProtected ? `\n                ${isBlockedByMe ? `\n                  <button class="chat-menu-item" onclick="App.handleUnblockUser(${otherUser.id})">\n                    <i data-lucide="user-check" style="color:#10b981; width:15px; height:15px;"></i>\n                    <span>Desbloquear Contato</span>\n                  </button>\n                ` : `\n                  <button class="chat-menu-item danger" onclick="App.handleBlockUser(${otherUser.id})">\n                    <i data-lucide="user-x" style="width:15px; height:15px;"></i>\n                    <span>Bloquear Contato</span>\n                  </button>\n                `}\n                <button class="chat-menu-item danger" onclick="App.closeChatMenu(); App.openReportModal();">\n                  <i data-lucide="alert-triangle" style="width:15px; height:15px;"></i>\n                  <span>Denunciar Violação</span>\n                </button>\n              ` : ""}\n              ${otherUser ? `\n                <button class="chat-menu-item" onclick="navigator.clipboard.writeText('${otherUser.numeric_id}'); App.showToast('ID Numérico copiado!', 'success'); App.closeChatMenu();">\n                  <i data-lucide="copy" style="width:15px; height:15px;"></i>\n                  <span>Copiar ID do Usuário</span>\n                </button>\n              ` : ""}\n              <button class="chat-menu-item" onclick="App.handleExportChatJson(${this.activeChat.id})">\n                <i data-lucide="download" style="width:15px; height:15px;"></i>\n                <span>Exportar Conversa (JSON)</span>\n              </button>\n            `}\n          </div>\n        </div>\n      </div>\n\n      \x3c!-- BANNER DE MENSAGEM FIXADA NO TOPO DO GRUPO (SE HOUVER) --\x3e\n      ${this.activeChat.is_group && this.activeChat.pinned_message_id ? `\n        <div class="pinned-message-bar" id="pinned-message-bar" onclick="App.scrollToMessage(${this.activeChat.pinned_message_id})" title="Clique para rolar até a mensagem fixada">\n          <div class="pinned-bar-left">\n            <div class="pinned-bar-icon"><i data-lucide="pin" style="width:16px; height:16px;"></i></div>\n            <div class="pinned-bar-content">\n              <span class="pinned-bar-title">📌 Mensagem Fixada</span>\n              <span class="pinned-bar-snippet" id="pinned-bar-snippet-text">Clique para visualizar</span>\n            </div>\n          </div>\n          ${this.activeChat.my_role === "admin" ? `\n            <button type="button" class="btn-icon" style="padding:2px;" onclick="event.stopPropagation(); App.pinMessageForEveryone(${this.activeChat.id}, null)" title="Desafixar mensagem">\n              <i data-lucide="x" style="width:14px; height:14px;"></i>\n            </button>\n          ` : ""}\n        </div>\n      ` : ""}\n\n      \x3c!-- BANNER DE AVISO SE GRUPO SUSPENSO OU BLOQUEADO --\x3e\n      ${isGroupSuspended ? `\n        <div class="blocked-notice-banner" style="background:rgba(239, 68, 68, 0.18); border-color:rgba(239, 68, 68, 0.4); color:#fca5a5;">\n          <span>🚫 <strong>Grupo Suspenso:</strong> Este grupo foi suspenso por violação das políticas e diretrizes da plataforma (${this.escapeHTML(this.activeChat.suspension_reason || "Violação de Termos de Uso")}). Nenhuma interação é permitida.</span>\n        </div>\n      ` : ""}\n\n      ${!isGroupSuspended && isTargetSuspended ? `\n        <div class="blocked-notice-banner" style="background:rgba(239, 68, 68, 0.18); border-color:rgba(239, 68, 68, 0.4); color:#fca5a5;">\n          <span>🚫 <strong>Conta Suspensa:</strong> Este usuário foi suspenso por violação das políticas e diretrizes da plataforma. Nenhuma interação é permitida.</span>\n        </div>\n      ` : ""}\n\n      ${!isGroupSuspended && !isTargetSuspended && amIBlocked ? `\n        <div class="blocked-notice-banner">\n          <span>⚠️ Você foi bloqueado(a) por este usuário e não pode enviar novas mensagens.</span>\n        </div>\n      ` : ""}\n\n      ${!isGroupSuspended && !isTargetSuspended && isBlockedByMe ? `\n        <div class="blocked-notice-banner" style="background:rgba(245, 158, 11, 0.15); border-color:rgba(245, 158, 11, 0.35); color:#fde68a;">\n          <span>🚫 Você bloqueou este contato. Desbloqueie para voltar a conversar.</span>\n          <button class="btn-primary" style="padding:4px 12px; font-size:11.5px; border-radius:6px;" onclick="App.handleUnblockUser(${otherUser.id})">Desbloquear</button>\n        </div>\n      ` : ""}\n\n      \x3c!-- AVISO DE CRIPTOGRAFIA AES-256-GCM --\x3e\n      <div class="e2ee-banner">\n        <i data-lucide="lock" style="width:14px; height:14px;"></i>\n        <span>${t("e2ee_notice")}</span>\n      </div>\n\n      \x3c!-- LISTA DE MENSAGENS --\x3e\n      <div class="messages-container" id="messages-container">\n        \x3c!-- Mensagens carregadas via JS --\x3e\n      </div>\n\n      \x3c!-- BARRA DE GRAVAÇÃO DE VOZ (QUANDO ATIVA) --\x3e\n      <div id="voice-recording-bar" class="voice-recording-overlay" style="display:none;">\n        <div class="recording-pulse"></div>\n        <span class="recording-timer" id="recording-timer-display">00:00</span>\n        <div class="recording-wave-container" id="recording-wave-bars">\n          <div class="recording-wave-bar"></div>\n          <div class="recording-wave-bar"></div>\n          <div class="recording-wave-bar"></div>\n          <div class="recording-wave-bar"></div>\n          <div class="recording-wave-bar"></div>\n          <div class="recording-wave-bar"></div>\n          <div class="recording-wave-bar"></div>\n          <div class="recording-wave-bar"></div>\n        </div>\n        <span style="font-size:13px; color:var(--text-muted); flex:1;">Gravando áudio em alta definição...</span>\n        <button class="btn-icon" onclick="App.cancelVoiceRecording()" title="Cancelar Gravação" style="color:var(--danger);">\n          <i data-lucide="trash-2"></i>\n        </button>\n        <button class="btn-send" onclick="App.stopAndSendVoiceRecording()" title="Enviar Áudio">\n          <i data-lucide="send"></i>\n        </button>\n      </div>\n\n      \x3c!-- POPOVER DE ANEXOS --\x3e\n      <div id="attachment-popover" class="attachment-menu-popover" style="display:none;">\n        <button class="attachment-menu-item" onclick="App.triggerFileInput('media')">\n          <i data-lucide="image" style="color:#38bdf8;"></i>\n          <span>Fotos & Vídeos</span>\n        </button>\n        <button class="attachment-menu-item" onclick="App.triggerFileInput('audio')">\n          <i data-lucide="music" style="color:#ec4899;"></i>\n          <span>Música & Áudio</span>\n        </button>\n        <button class="attachment-menu-item" onclick="App.triggerFileInput('document')">\n          <i data-lucide="file-text" style="color:#10b981;"></i>\n          <span>Arquivos & Docs</span>\n        </button>\n      </div>\n\n      \x3c!-- POPOVER DE EMOJIS --\x3e\n      <div id="emoji-popover" class="emoji-picker-popover" style="display:none;">\n        <div class="emoji-categories">\n          <button class="emoji-cat-btn active" onclick="App.switchEmojiCat('smileys')">😀</button>\n          <button class="emoji-cat-btn" onclick="App.switchEmojiCat('gestures')">👍</button>\n          <button class="emoji-cat-btn" onclick="App.switchEmojiCat('hearts')">❤️</button>\n          <button class="emoji-cat-btn" onclick="App.switchEmojiCat('objects')">🔥</button>\n        </div>\n        <div class="emoji-grid" id="emoji-grid-content">\n          \x3c!-- Emojis renderizados --\x3e\n        </div>\n      </div>\n\n      \x3c!-- INPUTS DE ARQUIVO OCULTOS --\x3e\n      <input type="file" id="media-file-input" style="display:none;" accept="image/*,video/*" onchange="App.handleMediaUpload(this.files[0], 'media')" />\n      <input type="file" id="audio-file-input" style="display:none;" accept="audio/*" onchange="App.handleMediaUpload(this.files[0], 'audio')" />\n      <input type="file" id="document-file-input" style="display:none;" onchange="App.handleMediaUpload(this.files[0], 'file')" />\n\n      \x3c!-- BARRA INFERIOR DE ENVIO OU AVISO DE BOT / CONTA SUSPENSA / GRUPO SUSPENSO / RESTRINGIDO --\x3e\n      ${isGroupSuspended ? `\n        <div class="chat-bot-notice" style="background:rgba(239, 68, 68, 0.12); border-color:rgba(239, 68, 68, 0.35); color:#fca5a5;">\n          🚫 <strong>Grupo Suspenso por Violação dos Termos de Uso</strong><br>\n          <span style="font-size:12px; color:var(--text-muted);">Não é possível enviar mensagens ou interagir neste grupo suspenso pela moderação.</span>\n        </div>\n      ` : isTargetSuspended ? `\n        <div class="chat-bot-notice" style="background:rgba(239, 68, 68, 0.12); border-color:rgba(239, 68, 68, 0.35); color:#fca5a5;">\n          🚫 <strong>Conta Suspensa por Violação dos Termos de Uso</strong><br>\n          <span style="font-size:12px; color:var(--text-muted);">Não é possível enviar mensagens ou interagir com esta conta suspensa pela moderação.</span>\n        </div>\n      ` : isReadOnlyBot ? `\n        <div class="chat-bot-notice">\n          🛡️ <strong>Canal Informativo Oficial do Fechat</strong><br>\n          <span style="font-size:12px; color:var(--text-muted);">Este canal transmite avisos importantes, novidades e boas-vindas do sistema. Não aceita respostas diretas de usuários.</span>\n        </div>\n      ` : isGroupOnlyAdminsSend ? `\n        <div class="chat-bot-notice" style="background:rgba(99, 102, 241, 0.12); border-color:rgba(99, 102, 241, 0.35); color:#a5b4fc;">\n          🔒 <strong>Apenas Administradores Podem Enviar Mensagens</strong><br>\n          <span style="font-size:12px; color:var(--text-muted);">As configurações deste grupo permitem apenas mensagens enviadas por administradores.</span>\n        </div>\n      ` : `\n        <form class="chat-bottom-bar" onsubmit="App.handleSendMessage(event)">\n          ${amIBlocked || isBlockedByMe ? `\n            <input \n              type="text" \n              disabled \n              class="chat-input-box" \n              placeholder="${amIBlocked ? "Você não pode enviar mensagens pois foi bloqueado(a)..." : "Desbloqueie este contato para voltar a enviar mensagens..."}" \n              style="opacity:0.5; cursor:not-allowed;"\n            />\n          ` : `\n            <button type="button" class="btn-icon" id="attachment-btn" onclick="App.toggleAttachmentMenu(event)" title="Anexar Fotos, Vídeos ou Documentos">\n              <i data-lucide="paperclip"></i>\n            </button>\n            \n            <button type="button" class="btn-icon" id="emoji-btn" onclick="App.toggleEmojiPicker(event)" title="Inserir Emojis">\n              <i data-lucide="smile"></i>\n            </button>\n\n            <input \n              type="text" \n              id="chat-message-input" \n              class="chat-input-box" \n              placeholder="${t("message_input_placeholder")}" \n              autocomplete="off"\n              oninput="App.handleTypingInput()"\n            />\n\n            <button type="button" class="btn-icon" id="voice-record-btn" onclick="App.startVoiceRecording()" title="Gravar Áudio de Voz">\n              <i data-lucide="mic" style="color:var(--primary);"></i>\n            </button>\n\n            <button type="submit" class="btn-send" title="Enviar Mensagem">\n              <i data-lucide="send"></i>\n            </button>\n          `}\n        </form>\n      `}\n    `;
  },
  toggleChatMenu(e) {
    e.stopPropagation();
    this.isChatMenuOpen = !this.isChatMenuOpen;
    const menu = document.getElementById("chat-menu-dropdown");
    if (menu) menu.style.display = this.isChatMenuOpen ? "flex" : "none";
    this.refreshIcons();
  },
  closeChatMenu() {
    this.isChatMenuOpen = false;
    const menu = document.getElementById("chat-menu-dropdown");
    if (menu) menu.style.display = "none";
  },
  openChatContextMenu(e, chat) {
    this.closeChatContextMenu();
    const menuEl = document.createElement("div");
    menuEl.id = "chat-context-menu";
    menuEl.className = "chat-context-menu";
    menuEl.innerHTML = `\n      <button class="context-menu-item" onclick="App.handleTogglePinChat(${chat.id})">\n        <i data-lucide="${chat.is_pinned ? "pin-off" : "pin"}" style="width:16px; height:16px;"></i>\n        <span>${chat.is_pinned ? "Desafixar conversa" : "Fixar conversa"}</span>\n      </button>\n      <button class="context-menu-item" onclick="App.handleToggleMuteChat(${chat.id})">\n        <i data-lucide="${chat.is_muted ? "bell" : "bell-off"}" style="width:16px; height:16px;"></i>\n        <span>${chat.is_muted ? "Reativar notificações" : "Silenciar notificações"}</span>\n      </button>\n      <button class="context-menu-item" onclick="App.handleToggleArchiveChat(${chat.id})">\n        <i data-lucide="${chat.is_archived ? "archive-restore" : "archive"}" style="width:16px; height:16px;"></i>\n        <span>${chat.is_archived ? "Desarquivar conversa" : "Arquivar conversa"}</span>\n      </button>\n      <button class="context-menu-item" onclick="App.handleMarkUnread(${chat.id})">\n        <i data-lucide="check-check" style="width:16px; height:16px;"></i>\n        <span>Marcar como não lida</span>\n      </button>\n      <div class="context-menu-divider"></div>\n      <button class="context-menu-item" onclick="App.handleExportChatJson(${chat.id})">\n        <i data-lucide="download" style="width:16px; height:16px; color:#38bdf8;"></i>\n        <span>Exportar conversa (JSON)</span>\n      </button>\n      <div class="context-menu-divider"></div>\n      <button class="context-menu-item danger" onclick="App.handleDeleteChat(${chat.id}, ${chat.is_group})">\n        <i data-lucide="trash-2" style="width:16px; height:16px;"></i>\n        <span>${chat.is_group ? "Sair do grupo" : "Apagar conversa"}</span>\n      </button>\n    `;
    document.body.appendChild(menuEl);
    const menuWidth = 230;
    const menuHeight = 260;
    let posX = e.clientX;
    let posY = e.clientY;
    if (posX + menuWidth > window.innerWidth) {
      posX = window.innerWidth - menuWidth - 10;
    }
    if (posY + menuHeight > window.innerHeight) {
      posY = window.innerHeight - menuHeight - 10;
    }
    menuEl.style.left = `${posX}px`;
    menuEl.style.top = `${posY}px`;
    this.refreshIcons();
  },
  closeChatContextMenu() {
    const existing = document.getElementById("chat-context-menu");
    if (existing) existing.remove();
  },
  async handleTogglePinChat(chatId) {
    this.closeChatContextMenu();
    try {
      const res = await FechatAPI.togglePinChat(chatId);
      this.showToast(
        res.is_pinned ? "Conversa fixada no topo!" : "Conversa desafixada.",
        "success",
      );
      await this.loadData();
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  async handleToggleMuteChat(chatId) {
    this.closeChatContextMenu();
    try {
      const res = await FechatAPI.toggleMuteChat(chatId);
      this.showToast(
        res.is_muted
          ? "Notificações silenciadas para esta conversa."
          : "Notificações reativadas!",
        "success",
      );
      await this.loadData();
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  async handleToggleArchiveChat(chatId) {
    this.closeChatContextMenu();
    try {
      const res = await FechatAPI.toggleArchiveChat(chatId);
      this.showToast(
        res.is_archived
          ? "Conversa arquivada com sucesso."
          : "Conversa desarquivada.",
        "success",
      );
      await this.loadData();
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  handleMarkUnread(chatId) {
    this.closeChatContextMenu();
    this.unreadCounts[chatId] = (this.unreadCounts[chatId] || 0) + 1;
    this.renderSidebarList();
    this.showToast("Conversa marcada como não lida.", "info");
  },
  async handleExportChatJson(chatId) {
    this.closeChatContextMenu();
    this.showToast("Exportando histórico e gerando arquivo JSON...", "info");
    try {
      const data = await FechatAPI.exportChatData(chatId);
      const chat = data.chat;
      const rawMessages = data.messages || [];
      const exportedMessages = [];
      for (const m of rawMessages) {
        let plaintext = "[Mídia]";
        if (m.ciphertext && chat.aes_channel_key) {
          try {
            plaintext = await FechatCrypto.decrypt(
              m.ciphertext,
              m.iv,
              m.tag,
              chat.aes_channel_key,
            );
          } catch {
            plaintext = "[Criptografado com chave protegida]";
          }
        }
        exportedMessages.push({
          message_id: m.id,
          sender_id: m.sender_id,
          sender_name: m.sender_name,
          sender_username: m.sender_username,
          content: plaintext,
          message_type: m.message_type,
          media_url: m.media_url,
          media_name: m.media_name,
          timestamp: m.created_at,
          status: m.status,
        });
      }
      const exportPayload = {
        platform: "Fechat End-to-End Cryptographic Messenger",
        export_version: "1.0",
        exported_at: new Date().toISOString(),
        chat_info: {
          id: chat.id,
          uuid: chat.uuid,
          title: chat.title,
          is_group: chat.is_group,
          total_messages: exportedMessages.length,
          created_at: chat.created_at,
        },
        messages: exportedMessages,
      };
      const dataStr =
        "data:text/json;charset=utf-8," +
        encodeURIComponent(JSON.stringify(exportPayload, null, 2));
      const downloadAnchor = document.createElement("a");
      const safeTitle = (chat.title || "conversa")
        .toLowerCase()
        .replace(/[^a-z0-9]/g, "_");
      downloadAnchor.setAttribute("href", dataStr);
      downloadAnchor.setAttribute(
        "download",
        `fechat_export_${safeTitle}_${Date.now()}.json`,
      );
      document.body.appendChild(downloadAnchor);
      downloadAnchor.click();
      downloadAnchor.remove();
      this.showToast(
        "Conversa exportada com sucesso em formato JSON!",
        "success",
      );
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  async handleDeleteChat(chatId, isGroup) {
    this.closeChatContextMenu();
    const title = isGroup ? "Sair do Grupo?" : "Apagar Conversa?";
    const text = isGroup
      ? "Deseja realmente sair deste grupo?"
      : "Deseja realmente apagar esta conversa e seu histórico?";
    const confirmBtnText = isGroup ? "Sim, Sair do Grupo" : "Sim, Apagar";
    if (window.Swal) {
      const result = await Swal.fire({
        title: title,
        text: text,
        icon: "warning",
        showCancelButton: true,
        confirmButtonColor: "#ef4444",
        cancelButtonColor: "#475569",
        confirmButtonText: confirmBtnText,
        cancelButtonText: "Cancelar",
        background: "#131b2e",
        color: "#f8fafc",
      });
      if (!result.isConfirmed) return;
    } else {
      if (!confirm(text)) return;
    }
    try {
      await FechatAPI.deleteChat(chatId);
      this.showToast(
        isGroup
          ? "Você saiu do grupo com sucesso."
          : "Conversa apagada com sucesso.",
        "success",
      );
      if (this.activeChat && this.activeChat.id === chatId) {
        this.closeActiveChat();
      }
      await this.loadData();
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  closeActiveChat() {
    this.activeChat = null;
    const containerEl = document.getElementById("main-content-container");
    if (containerEl) {
      containerEl.classList.remove("workspace-active");
      containerEl.classList.add("sidebar-active");
    }
    const workspace = document.getElementById("primary-workspace");
    if (workspace) {
      workspace.innerHTML = this.renderActiveWorkspace();
      this.refreshIcons();
    }
    this.renderSidebarList();
  },
  async openChat(chat) {
    this.activeChat = chat;
    this.isChatMenuOpen = false;
    this.unreadCounts[chat.id] = 0;
    this.updateUnreadBadges();
    if (window.FechatAudio) FechatAudio.playTick();
    const containerEl = document.getElementById("main-content-container");
    if (containerEl) {
      containerEl.classList.remove("sidebar-active");
      containerEl.classList.add("workspace-active");
    }
    if (!chat.is_group) {
      const members = chat.members || [];
      const other = members.find((m) => m.user_id !== this.currentUser.id);
      if (other && other.user) {
        try {
          this.activeChatBlockStatus = await FechatAPI.getBlockStatus(
            other.user.id,
          );
        } catch {
          this.activeChatBlockStatus = {
            is_blocked_by_me: false,
            am_i_blocked: false,
          };
        }
      }
    } else {
      this.activeChatBlockStatus = {
        is_blocked_by_me: false,
        am_i_blocked: false,
      };
    }
    const workspace = document.getElementById("primary-workspace");
    if (workspace) {
      workspace.innerHTML = this.renderChatWindowHTML();
    }
    this.refreshIcons();
    this.renderSidebarList();
    await this.loadMessages(chat.id);
    FechatAPI.markChatRead(chat.id).catch(() => {});
  },
  async loadMessages(chatId) {
    const container = document.getElementById("messages-container");
    if (!container) return;
    container.innerHTML =
      '<div style="text-align:center; padding:20px; color:var(--text-dim);">Carregando mensagens com criptografia segura...</div>';
    try {
      const messages = await FechatAPI.getMessages(chatId);
      container.innerHTML = "";
      if (messages.length === 0) {
        container.innerHTML = `\n          <div style="text-align:center; padding:40px; color:var(--text-muted); font-size:13px;">\n            🛡️ Inicie esta conversa com segurança total.<br>Ninguém de fora tem acesso a este canal.\n          </div>\n        `;
        return;
      }
      for (const msg of messages) {
        await this.appendMessageToDOM(msg);
      }
      this.scrollToBottom();
    } catch (e) {
      container.innerHTML = `<div style="color:var(--danger); text-align:center; padding:20px;">${e.message}</div>`;
    }
  },
  renderTicksHTML(status) {
    if (status === "read") {
      return `<span class="tick-icon tick-read" title="Lido">✓✓</span>`;
    } else if (status === "delivered") {
      return `<span class="tick-icon tick-delivered" title="Entregue">✓✓</span>`;
    }
    return `<span class="tick-icon tick-sent" title="Enviado">✓</span>`;
  },
  getAuthorColor(senderId, senderName = "") {
    const colors = [
      "#38bdf8",
      "#fb7185",
      "#a3e635",
      "#f59e0b",
      "#c084fc",
      "#2dd4bf",
      "#f43f5e",
      "#fb923c",
      "#e879f9",
      "#60a5fa",
      "#4ade80",
      "#34d399",
      "#f472b6",
      "#a78bfa",
    ];
    const hashStr = String(senderId || senderName || "0");
    let hash = 0;
    for (let i = 0; i < hashStr.length; i++) {
      hash = hashStr.charCodeAt(i) + ((hash << 5) - hash);
    }
    const index = Math.abs(hash) % colors.length;
    return colors[index];
  },
  setReplyTo(messageId, senderName, rawSnippet) {
    let cleanSnippet = (rawSnippet || "")
      .replace(/<br>/g, " ")
      .replace(/<[^>]+>/g, "")
      .trim();
    const chars = Array.from(cleanSnippet);
    if (chars.length > 80) {
      cleanSnippet = chars.slice(0, 80).join("") + "...";
    }
    this.activeReply = {
      message_id: messageId,
      sender_name: senderName || "Usuário",
      snippet: cleanSnippet || "Mensagem",
    };
    this.renderReplyPreviewBar();
    const input = document.getElementById("chat-message-input");
    if (input) input.focus();
  },
  clearReply() {
    this.activeReply = null;
    const bar = document.getElementById("reply-preview-bar");
    if (bar) bar.remove();
  },
  renderReplyPreviewBar() {
    let bar = document.getElementById("reply-preview-bar");
    const form = document.querySelector(".chat-bottom-bar");
    if (!form) return;
    if (!this.activeReply) {
      if (bar) bar.remove();
      return;
    }
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "reply-preview-bar";
      bar.className = "reply-preview-bar";
      form.parentNode.insertBefore(bar, form);
    }
    bar.innerHTML = `\n      <div class="reply-preview-content">\n        <div class="reply-preview-title">\n          <i data-lucide="corner-up-left" style="width:14px; height:14px;"></i>\n          <span>Respondendo a ${this.escapeHTML(this.activeReply.sender_name)}</span>\n        </div>\n        <div class="reply-preview-text">${this.escapeHTML(this.activeReply.snippet)}</div>\n      </div>\n      <button type="button" class="reply-preview-close-btn" onclick="App.clearReply()" title="Cancelar resposta">\n        <i data-lucide="x" style="width:16px; height:16px;"></i>\n      </button>\n    `;
    this.refreshIcons();
  },
  scrollToMessage(messageId) {
    if (!messageId) return;
    const el = document.querySelector(
      `.message-row[data-msg-id="${messageId}"]`,
    );
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("highlight-message-pulse");
      setTimeout(() => el.classList.remove("highlight-message-pulse"), 1600);
    } else {
      this.showToast(
        "Mensagem original não está visível no histórico recente.",
        "info",
      );
    }
  },
  async appendMessageToDOM(msg) {
    const container = document.getElementById("messages-container");
    if (!container) return;
    const existingRow = container.querySelector(
      `.message-row[data-msg-id="${msg.id}"]`,
    );
    if (existingRow) {
      const ticksEl = existingRow.querySelector(".tick-icon");
      if (ticksEl && msg.status) {
        ticksEl.className =
          msg.status === "read"
            ? "tick-icon tick-read"
            : msg.status === "delivered"
              ? "tick-icon tick-delivered"
              : "tick-icon tick-sent";
        ticksEl.textContent =
          msg.status === "read"
            ? "✓✓"
            : msg.status === "delivered"
              ? "✓✓"
              : "✓";
      }
      return;
    }
    const isMe = msg.sender_id === this.currentUser.id;
    const timeStr = new Date(msg.created_at).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
    const row = document.createElement("div");
    row.className = `message-row ${isMe ? "sent" : "received"}`;
    row.setAttribute("data-msg-id", msg.id);
    if (msg.is_deleted) {
      row.innerHTML = `\n        <div class="message-bubble" style="background:rgba(255,255,255,0.04); border:1px dashed rgba(255,255,255,0.15);">\n          <div class="msg-text" style="font-style:italic; opacity:0.65; color:var(--text-muted); display:flex; align-items:center; gap:6px;">\n            <i data-lucide="ban" style="width:14px; height:14px;"></i>\n            <span>Esta mensagem foi apagada</span>\n          </div>\n          <div class="msg-meta">\n            <span>${timeStr}</span>\n          </div>\n        </div>\n      `;
      container.appendChild(row);
      this.refreshIcons();
      return;
    }
    let plaintext = "";
    try {
      plaintext = await FechatCrypto.decrypt(
        msg.ciphertext,
        msg.iv,
        msg.tag,
        this.activeChat.aes_channel_key,
      );
    } catch {
      plaintext = "[🔒 Mensagem criptografada]";
    }
    let mediaContent = "";
    if (msg.message_type === "image" && msg.media_url) {
      mediaContent = `<img src="${msg.media_url}" class="media-preview-img" onclick="window.open('${msg.media_url}', '_blank')" />`;
    } else if (msg.message_type === "video" && msg.media_url) {
      mediaContent = `<video src="${msg.media_url}" controls class="media-preview-video"></video>`;
    } else if (
      msg.message_type === "voice" ||
      msg.message_type === "audio" ||
      (msg.media_url &&
        (msg.media_url.endsWith(".webm") ||
          msg.media_url.endsWith(".mp3") ||
          msg.media_url.endsWith(".wav") ||
          msg.media_url.endsWith(".ogg")))
    ) {
      mediaContent = `\n        <div class="voice-note-player" data-audio-url="${msg.media_url || ""}">\n          <button class="voice-play-btn" onclick="App.toggleAudioPlay(this, '${msg.media_url || ""}')" title="Tocar áudio">\n            <i data-lucide="play" style="width:18px; height:18px;"></i>\n          </button>\n          <div class="voice-waveform-container">\n            <div class="voice-waveform-bars" onclick="App.toggleAudioPlay(this.closest('.voice-note-player').querySelector('.voice-play-btn'), '${msg.media_url || ""}')">\n              <span style="height:35%;"></span>\n              <span style="height:65%;"></span>\n              <span style="height:90%;"></span>\n              <span style="height:50%;"></span>\n              <span style="height:100%;"></span>\n              <span style="height:70%;"></span>\n              <span style="height:40%;"></span>\n              <span style="height:80%;"></span>\n              <span style="height:60%;"></span>\n              <span style="height:95%;"></span>\n              <span style="height:45%;"></span>\n              <span style="height:85%;"></span>\n              <span style="height:30%;"></span>\n              <span style="height:75%;"></span>\n              <span style="height:55%;"></span>\n            </div>\n            <div class="voice-progress-wrapper" onclick="App.seekAudio(event, this)">\n              <div class="audio-progress-bar" style="width:0%;"></div>\n            </div>\n            <div class="voice-time-row">\n              <span class="audio-time-display">0:00</span>\n              <span style="font-weight:700; font-size:10px; opacity:0.85;">🎙️ ÁUDIO</span>\n            </div>\n          </div>\n        </div>\n      `;
    } else if (msg.message_type === "file" && msg.media_url) {
      mediaContent = `\n        <a href="${msg.media_url}" target="_blank" download="${msg.media_name || "arquivo"}" style="text-decoration:none; color:inherit;">\n          <div class="file-attachment-card">\n            <i data-lucide="file" style="color:var(--primary); width:28px; height:28px;"></i>\n            <div class="file-info">\n              <div class="file-name">${msg.media_name || "Documento"}</div>\n              <div class="file-size">${msg.media_size ? (msg.media_size / 1024).toFixed(1) + " KB" : "Arquivo"}</div>\n            </div>\n            <i data-lucide="download" style="width:16px; height:16px;"></i>\n          </div>\n        </a>\n      `;
    }
    let quoteHTML = "";
    if (msg.reply_to_message_id) {
      quoteHTML = `\n        <div class="message-quote-box" onclick="App.scrollToMessage(${msg.reply_to_message_id})" title="Clique para ver a mensagem original">\n          <div class="quote-sender-name">${this.escapeHTML(msg.reply_to_sender_name || "Mensagem")}</div>\n          <div class="quote-snippet-text">${this.escapeHTML(msg.reply_to_snippet || "...")}</div>\n        </div>\n      `;
    }
    let groupHeaderHTML = "";
    if (!isMe && this.activeChat && this.activeChat.is_group && msg.sender) {
      const authorColor = this.getAuthorColor(
        msg.sender.id,
        msg.sender.full_name,
      );
      const senderAvatar =
        msg.sender.avatar_url ||
        `https://api.dicebear.com/7.x/bottts/svg?seed=${msg.sender.username}`;
      groupHeaderHTML = `\n        <div class="group-msg-header">\n          <img src="${senderAvatar}" class="group-msg-avatar" />\n          <span class="group-msg-author-name" style="color:${authorColor};">${this.escapeHTML(msg.sender.full_name)}</span>\n          ${msg.sender.numeric_id ? `<span class="group-msg-author-id">${this.formatId(msg.sender.numeric_id)}</span>` : ""}\n        </div>\n      `;
    }
    const isCallLog =
      msg.message_type === "call_log" ||
      (plaintext && plaintext.startsWith("CALL_LOG:"));
    if (isCallLog) {
      let logData = {};
      try {
        logData = JSON.parse(plaintext.replace("CALL_LOG:", ""));
      } catch (_) {}
      const status = logData.call_status || "ended";
      const durSecs = logData.duration || 0;
      const mins = String(Math.floor(durSecs / 60)).padStart(2, "0");
      const secs = String(durSecs % 60).padStart(2, "0");
      const formattedDur = durSecs > 0 ? `${mins}:${secs}` : "";
      let title = "Chamada de voz";
      let sub = "Finalizada";
      let icon = "phone";
      let iconClass = "ended";
      if (status === "ended") {
        title = "Chamada de voz";
        sub = durSecs > 0 ? `Duração: ${formattedDur}` : "Finalizada";
        icon = isMe ? "phone-outgoing" : "phone-incoming";
        iconClass = "ended";
      } else if (status === "missed") {
        title = isMe ? "Chamada não atendida" : "Chamada perdida";
        sub = isMe ? "Sem resposta" : "Você perdeu esta chamada";
        icon = isMe ? "phone-outgoing" : "phone-missed";
        iconClass = "missed";
      } else if (status === "rejected") {
        title = isMe ? "Chamada recusada" : "Chamada não atendida";
        sub = isMe ? "O contato recusou a chamada" : "Chamada recusada";
        icon = "phone-off";
        iconClass = "rejected";
      }
      mediaContent = `\n        <div class="call-log-card">\n          <div class="call-log-icon-wrap ${iconClass}">\n            <i data-lucide="${icon}" style="width:20px; height:20px;"></i>\n          </div>\n          <div class="call-log-body">\n            <div class="call-log-title">${title}</div>\n            <div class="call-log-sub">${sub}</div>\n          </div>\n          <button class="call-log-btn-callback" onclick="App.startVoiceCallFromChat()" title="Ligar de volta">\n            <i data-lucide="phone" style="width:13px; height:13px;"></i> Ligar\n          </button>\n        </div>\n      `;
    }
    const textHTML = isCallLog ? "" : this.formatMessageText(plaintext);
    const isSenderProtected =
      msg.sender &&
      (msg.sender.is_bot || msg.sender.is_verified || msg.sender.is_admin);
    const isChatProtected =
      this.activeChat &&
      (this.activeChat.is_bot ||
        (this.activeChat.target_user &&
          (this.activeChat.target_user.is_bot ||
            this.activeChat.target_user.is_verified ||
            this.activeChat.target_user.is_admin)));
    const canReport =
      !isMe && !isSenderProtected && !isChatProtected && !isCallLog;
    const isGroupAdmin = Boolean(
      this.activeChat &&
      this.activeChat.is_group &&
      this.activeChat.my_role === "admin",
    );
    const senderDisplayName = isMe
      ? "Você"
      : msg.sender
        ? msg.sender.full_name
        : "Usuário";
    const rawSnippet =
      plaintext ||
      (msg.message_type === "voice"
        ? "🎙️ Áudio"
        : isCallLog
          ? "📞 Chamada"
          : "📎 Mídia");
    row.innerHTML = `\n      <div class="message-bubble ${isCallLog ? "call-log-msg-bubble" : ""}">\n        ${groupHeaderHTML}\n        ${quoteHTML}\n        ${mediaContent}\n        ${textHTML}\n        <div class="msg-meta">\n          <span>${timeStr}</span>\n          ${isMe ? this.renderTicksHTML(msg.status || "sent") : ""}\n        </div>\n        \n        \x3c!-- BOTAO DE AÇÕES DA MENSAGEM --\x3e\n        <button \n          type="button" \n          class="message-action-trigger" \n          onclick="App.openMessageActionMenu(event, ${msg.id}, '${this.escapeHTML(senderDisplayName).replace(/'/g, "\\'")}', '${this.escapeHTML(rawSnippet).replace(/'/g, "\\'")}', ${isMe}, ${isGroupAdmin}, ${canReport}, '${msg.franking_tag || ""}')" \n          title="Opções da mensagem"\n        >\n          <i data-lucide="chevron-down" style="width:14px; height:14px;"></i>\n        </button>\n      </div>\n      ${canReport ? `\n        <button class="msg-menu-btn" onclick="App.openReportModal(${msg.id}, '${encodeURIComponent(plaintext)}', '${msg.franking_tag || ""}')" title="Denunciar esta mensagem">\n          <i data-lucide="alert-circle" style="width:16px; height:16px;"></i>\n        </button>\n      ` : ""}\n    `;
    const typingBubble = document.getElementById("chat-typing-bubble");
    if (typingBubble) {
      typingBubble.remove();
    }
    container.appendChild(row);
    this.refreshIcons();
  },
  openMessageActionMenu(
    e,
    messageId,
    senderName,
    snippetText,
    isMe,
    isGroupAdmin,
    canReport,
    frankingTag,
  ) {
    e.stopPropagation();
    this.closeMessageActionMenu();
    const menu = document.createElement("div");
    menu.id = "message-action-menu-dropdown";
    menu.className = "chat-menu-dropdown";
    menu.style.position = "fixed";
    menu.style.zIndex = "99999";
    menu.style.display = "flex";
    menu.innerHTML = `\n      <button class="chat-menu-item" onclick="App.closeMessageActionMenu(); App.setReplyTo(${messageId}, '${senderName.replace(/'/g, "\\'")}', '${snippetText.replace(/'/g, "\\'")}')">\n        <i data-lucide="corner-up-left" style="width:15px; height:15px; color:var(--primary);"></i>\n        <span>Responder</span>\n      </button>\n\n      <button class="chat-menu-item" onclick="App.closeMessageActionMenu(); navigator.clipboard.writeText('${snippetText.replace(/'/g, "\\'")}'); App.showToast('Texto copiado!', 'success');">\n        <i data-lucide="copy" style="width:15px; height:15px;"></i>\n        <span>Copiar</span>\n      </button>\n\n      ${this.activeChat && this.activeChat.is_group && isGroupAdmin ? `\n        <button class="chat-menu-item" onclick="App.closeMessageActionMenu(); App.pinMessageForEveryone(${this.activeChat.id}, ${messageId})">\n          <i data-lucide="pin" style="width:15px; height:15px; color:#facc15;"></i>\n          <span>Fixar para Todos</span>\n        </button>\n      ` : ""}\n\n      ${isMe || (this.activeChat && this.activeChat.is_group && isGroupAdmin) ? `\n        <button class="chat-menu-item danger" onclick="App.closeMessageActionMenu(); App.deleteMessageForEveryone(${messageId})">\n          <i data-lucide="trash-2" style="width:15px; height:15px;"></i>\n          <span>Apagar para Todos</span>\n        </button>\n      ` : ""}\n\n      ${canReport ? `\n        <button class="chat-menu-item danger" onclick="App.closeMessageActionMenu(); App.openReportModal(${messageId}, '${encodeURIComponent(snippetText)}', '${frankingTag}')">\n          <i data-lucide="alert-triangle" style="width:15px; height:15px;"></i>\n          <span>Denunciar</span>\n        </button>\n      ` : ""}\n    `;
    document.body.appendChild(menu);
    let posX = e.clientX;
    let posY = e.clientY;
    const menuWidth = 190;
    const menuHeight = 170;
    if (posX + menuWidth > window.innerWidth)
      posX = window.innerWidth - menuWidth - 10;
    if (posY + menuHeight > window.innerHeight)
      posY = window.innerHeight - menuHeight - 10;
    menu.style.left = `${posX}px`;
    menu.style.top = `${posY}px`;
    const closeHandler = () => {
      this.closeMessageActionMenu();
      document.removeEventListener("click", closeHandler);
    };
    setTimeout(() => document.addEventListener("click", closeHandler), 50);
    this.refreshIcons();
  },
  closeMessageActionMenu() {
    const existing = document.getElementById("message-action-menu-dropdown");
    if (existing) existing.remove();
  },
  async handleSendMessage(e) {
    e.preventDefault();
    const input = document.getElementById("chat-message-input");
    const text = input ? input.value.trim() : "";
    if (!text || !this.activeChat) return;
    const replyInfo = this.activeReply ? { ...this.activeReply } : null;
    this.clearReply();
    if (input) input.value = "";
    try {
      const encrypted = await FechatCrypto.encrypt(
        text,
        this.activeChat.aes_channel_key,
      );
      const sentMsg = await FechatAPI.sendMessage(
        this.activeChat.id,
        encrypted.ciphertext,
        encrypted.iv,
        encrypted.tag,
        "text",
        null,
        null,
        null,
        null,
        replyInfo ? replyInfo.message_id : null,
        replyInfo ? replyInfo.sender_name : null,
        replyInfo ? replyInfo.snippet : null,
      );
      if (sentMsg) {
        await this.appendMessageToDOM(sentMsg);
        const chat = (this.chats || []).find(
          (c) => c.id === this.activeChat.id,
        );
        if (chat) {
          chat.last_message = sentMsg;
          chat.updated_at = sentMsg.created_at || new Date().toISOString();
          this.chats.sort(
            (a, b) =>
              new Date(b.updated_at || b.created_at) -
              new Date(a.updated_at || a.created_at),
          );
          this.renderSidebarList();
        }
      }
      if (window.FechatAudio) FechatAudio.playSent();
      socketClient.sendTyping(this.activeChat.id, false);
      this.scrollToBottom();
    } catch (err) {
      console.error("Erro ao enviar mensagem:", err);
      this.showToast(
        err.message || "Falha ao enviar mensagem criptografada.",
        "danger",
      );
    }
  },
  handleTypingInput() {
    if (!this.activeChat) return;
    socketClient.sendTyping(this.activeChat.id, true);
    clearTimeout(this.typingTimeout);
    this.typingTimeout = setTimeout(() => {
      socketClient.sendTyping(this.activeChat.id, false);
    }, 2e3);
  },
  _activeAudio: null,
  _activeAudioUrl: null,
  _activeAudioBtn: null,
  _activeAudioPlayerEl: null,
  toggleAudioPlay(btn, audioUrl) {
    if (!audioUrl) {
      this.showToast("Arquivo de áudio não disponível.", "warning");
      return;
    }
    const playerEl = btn ? btn.closest(".voice-note-player") : null;
    if (this._activeAudio && this._activeAudioUrl === audioUrl) {
      if (this._activeAudio.paused) {
        this._activeAudio
          .play()
          .then(() => {
            this.updateAudioPlayerUI(btn, playerEl, true);
          })
          .catch((err) => {
            console.warn("Erro ao reproduzir áudio:", err);
            this.showToast("Não foi possível reproduzir o áudio.", "danger");
          });
      } else {
        this._activeAudio.pause();
        this.updateAudioPlayerUI(btn, playerEl, false);
      }
      return;
    }
    this.stopActiveAudio();
    const audio = new Audio(audioUrl);
    this._activeAudio = audio;
    this._activeAudioUrl = audioUrl;
    this._activeAudioBtn = btn;
    this._activeAudioPlayerEl = playerEl;
    const formatTime = (secs) => {
      if (isNaN(secs) || !isFinite(secs)) return "0:00";
      const m = Math.floor(secs / 60);
      const s = Math.floor(secs % 60);
      return `${m}:${String(s).padStart(2, "0")}`;
    };
    const timeDisplay = playerEl
      ? playerEl.querySelector(".audio-time-display")
      : null;
    const progressBar = playerEl
      ? playerEl.querySelector(".audio-progress-bar")
      : null;
    audio.onloadedmetadata = () => {
      if (timeDisplay && audio.duration) {
        timeDisplay.textContent = formatTime(audio.duration);
      }
    };
    audio.ontimeupdate = () => {
      if (audio.duration) {
        const percent = (audio.currentTime / audio.duration) * 100;
        if (progressBar) {
          progressBar.style.width = `${percent}%`;
        }
        if (timeDisplay) {
          timeDisplay.textContent = formatTime(audio.currentTime);
        }
      }
    };
    audio.onended = () => {
      this.updateAudioPlayerUI(btn, playerEl, false);
      if (progressBar) progressBar.style.width = "0%";
      if (timeDisplay && audio.duration) {
        timeDisplay.textContent = formatTime(audio.duration);
      }
      this._activeAudio = null;
      this._activeAudioUrl = null;
    };
    audio.onerror = (e) => {
      console.warn("Erro ao carregar áudio:", e);
      this.updateAudioPlayerUI(btn, playerEl, false);
      this.showToast("Erro ao carregar arquivo de áudio.", "danger");
      this._activeAudio = null;
      this._activeAudioUrl = null;
    };
    audio
      .play()
      .then(() => {
        this.updateAudioPlayerUI(btn, playerEl, true);
      })
      .catch((err) => {
        console.warn("Erro ao iniciar áudio:", err);
        this.updateAudioPlayerUI(btn, playerEl, false);
        this.showToast(
          "Clique no botão de play para reproduzir o áudio.",
          "info",
        );
      });
  },
  updateAudioPlayerUI(btn, playerEl, isPlaying) {
    if (btn) {
      btn.innerHTML = `<i data-lucide="${isPlaying ? "pause" : "play"}" style="width:18px; height:18px;"></i>`;
      btn.setAttribute("title", isPlaying ? "Pausar áudio" : "Tocar áudio");
      this.refreshIcons();
    }
    if (playerEl) {
      if (isPlaying) {
        playerEl.classList.add("playing");
      } else {
        playerEl.classList.remove("playing");
      }
    }
  },
  seekAudio(event, progressWrapper) {
    event.stopPropagation();
    if (!progressWrapper) return;
    const playerEl = progressWrapper.closest(".voice-note-player");
    const audioUrl = playerEl ? playerEl.getAttribute("data-audio-url") : null;
    const playBtn = playerEl ? playerEl.querySelector(".voice-play-btn") : null;
    if (!audioUrl) return;
    const rect = progressWrapper.getBoundingClientRect();
    const clickX = event.clientX - rect.left;
    const clickRatio = Math.max(0, Math.min(1, clickX / rect.width));
    if (!this._activeAudio || this._activeAudioUrl !== audioUrl) {
      this.toggleAudioPlay(playBtn, audioUrl);
      setTimeout(() => {
        if (this._activeAudio && this._activeAudio.duration) {
          this._activeAudio.currentTime =
            clickRatio * this._activeAudio.duration;
        }
      }, 150);
      return;
    }
    if (this._activeAudio && this._activeAudio.duration) {
      this._activeAudio.currentTime = clickRatio * this._activeAudio.duration;
      const progressBar = playerEl
        ? playerEl.querySelector(".audio-progress-bar")
        : null;
      if (progressBar) {
        progressBar.style.width = `${clickRatio * 100}%`;
      }
    }
  },
  stopActiveAudio() {
    if (this._activeAudio) {
      try {
        this._activeAudio.pause();
        this._activeAudio.currentTime = 0;
      } catch (_) {}
      this.updateAudioPlayerUI(
        this._activeAudioBtn,
        this._activeAudioPlayerEl,
        false,
      );
      this._activeAudio = null;
      this._activeAudioUrl = null;
      this._activeAudioBtn = null;
      this._activeAudioPlayerEl = null;
    }
  },
  async getBestAudioStream(isCall = false) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("API de microfone/áudio não suportada pelo navegador.");
    }
    try {
      return await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      });
    } catch (_) {}
    try {
      return await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: false,
      });
    } catch (err2) {
      if (
        isCall &&
        (err2.name === "NotFoundError" ||
          err2.name === "DevicesNotFoundError" ||
          String(err2).includes("NotFound"))
      ) {
        try {
          const AudioCtx = window.AudioContext || window.webkitAudioContext;
          if (AudioCtx) {
            const ctx = new AudioCtx();
            const dest = ctx.createMediaStreamDestination();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            gain.gain.value = 1e-5;
            osc.connect(gain);
            gain.connect(dest);
            osc.start();
            return dest.stream;
          }
        } catch (_) {}
      }
      throw err2;
    }
  },
  _recordingAudioCtx: null,
  _recordingWaveInterval: null,
  async startVoiceRecording() {
    try {
      const stream = await this.getBestAudioStream(false);
      this._recordingStream = stream;
      let chosenMime = "";
      if (window.MediaRecorder) {
        if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus"))
          chosenMime = "audio/webm;codecs=opus";
        else if (MediaRecorder.isTypeSupported("audio/webm"))
          chosenMime = "audio/webm";
        else if (MediaRecorder.isTypeSupported("audio/mp4"))
          chosenMime = "audio/mp4";
        else if (MediaRecorder.isTypeSupported("audio/ogg"))
          chosenMime = "audio/ogg";
      }
      this._recordingMimeType = chosenMime || "audio/webm";
      const options = chosenMime
        ? { mimeType: chosenMime, audioBitsPerSecond: 128e3 }
        : {};
      this.mediaRecorder = new MediaRecorder(stream, options);
      this.audioChunks = [];
      this.mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) this.audioChunks.push(e.data);
      };
      this.mediaRecorder.start(100);
      this.isRecording = true;
      this.recordingSeconds = 0;
      if (window.FechatAudio) FechatAudio.playRecordStart();
      const bar = document.getElementById("voice-recording-bar");
      if (bar) bar.style.display = "flex";
      const display = document.getElementById("recording-timer-display");
      if (display) display.textContent = "00:00";
      clearInterval(this.recordingInterval);
      this.recordingInterval = setInterval(() => {
        this.recordingSeconds++;
        const mins = String(Math.floor(this.recordingSeconds / 60)).padStart(
          2,
          "0",
        );
        const secs = String(this.recordingSeconds % 60).padStart(2, "0");
        const timerDisp = document.getElementById("recording-timer-display");
        if (timerDisp) timerDisp.textContent = `${mins}:${secs}`;
      }, 1e3);
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (AudioCtx) {
          this._recordingAudioCtx = new AudioCtx();
          const source =
            this._recordingAudioCtx.createMediaStreamSource(stream);
          const analyser = this._recordingAudioCtx.createAnalyser();
          analyser.fftSize = 32;
          source.connect(analyser);
          const dataArray = new Uint8Array(analyser.frequencyBinCount);
          clearInterval(this._recordingWaveInterval);
          this._recordingWaveInterval = setInterval(() => {
            if (!this.isRecording) return;
            analyser.getByteFrequencyData(dataArray);
            const waveBars = document.querySelectorAll(
              "#recording-wave-bars .recording-wave-bar",
            );
            if (waveBars && waveBars.length > 0) {
              waveBars.forEach((wbar, idx) => {
                const val = dataArray[idx % dataArray.length] || 0;
                const h = Math.max(
                  4,
                  Math.min(22, Math.floor((val / 255) * 22)),
                );
                wbar.style.height = `${h}px`;
              });
            }
          }, 60);
        }
      } catch (err) {
        console.warn("Audio analyser recording:", err);
      }
      this.refreshIcons();
    } catch (e) {
      console.warn("Erro ao acessar microfone:", e);
      if (e.name === "NotFoundError" || e.name === "DevicesNotFoundError") {
        this.showToast(
          "Nenhum microfone foi detectado neste dispositivo/computador.",
          "warning",
        );
      } else if (
        e.name === "NotAllowedError" ||
        e.name === "PermissionDeniedError"
      ) {
        this.showToast(
          "Permissão de acesso ao microfone foi negada no navegador.",
          "warning",
        );
      } else {
        this.showToast(
          "Microfone indisponível no momento: " +
            (e.message || "Erro de dispositivo"),
          "danger",
        );
      }
    }
  },
  cancelVoiceRecording() {
    if (this.mediaRecorder && this.isRecording) {
      this.mediaRecorder.onstop = null;
      try {
        this.mediaRecorder.stop();
      } catch (_) {}
      if (this._recordingStream) {
        try {
          this._recordingStream.getTracks().forEach((t) => t.stop());
        } catch (_) {}
        this._recordingStream = null;
      }
      if (this._recordingWaveInterval) {
        clearInterval(this._recordingWaveInterval);
        this._recordingWaveInterval = null;
      }
      if (this._recordingAudioCtx) {
        try {
          this._recordingAudioCtx.close();
        } catch (_) {}
        this._recordingAudioCtx = null;
      }
      this.isRecording = false;
      clearInterval(this.recordingInterval);
      if (window.FechatAudio) FechatAudio.playRecordStop();
      const bar = document.getElementById("voice-recording-bar");
      if (bar) bar.style.display = "none";
      this.audioChunks = [];
      this.showToast("Gravação de voz cancelada.", "info");
    }
  },
  async stopAndSendVoiceRecording() {
    if (!this.mediaRecorder || !this.isRecording) return;
    if (window.FechatAudio) FechatAudio.playRecordStop();
    if (this._recordingWaveInterval) {
      clearInterval(this._recordingWaveInterval);
      this._recordingWaveInterval = null;
    }
    if (this._recordingAudioCtx) {
      try {
        this._recordingAudioCtx.close();
      } catch (_) {}
      this._recordingAudioCtx = null;
    }
    this.mediaRecorder.onstop = async () => {
      const mimeType = this._recordingMimeType || "audio/webm";
      const audioBlob = new Blob(this.audioChunks, { type: mimeType });
      const ext = mimeType.includes("mp4")
        ? "mp4"
        : mimeType.includes("ogg")
          ? "ogg"
          : "webm";
      const audioFile = new File([audioBlob], `voice_${Date.now()}.${ext}`, {
        type: mimeType,
      });
      if (this._recordingStream) {
        try {
          this._recordingStream.getTracks().forEach((t) => t.stop());
        } catch (_) {}
        this._recordingStream = null;
      }
      await App.handleMediaUpload(audioFile, "voice");
    };
    try {
      this.mediaRecorder.stop();
    } catch (_) {}
    this.isRecording = false;
    clearInterval(this.recordingInterval);
    const bar = document.getElementById("voice-recording-bar");
    if (bar) bar.style.display = "none";
  },
  activeCall: null,
  async startVoiceCallFromChat() {
    if (!this.activeChat || this.activeChat.is_group) return;
    const members = this.activeChat.members || [];
    const other = members.find((m) => m.user_id !== this.currentUser.id);
    if (!other || !other.user) {
      this.showToast("Contato não disponível para ligação de voz.", "warning");
      return;
    }
    await this.initiateVoiceCall(other.user, this.activeChat.id);
  },
  async initiateVoiceCall(targetUser, chatId) {
    if (this.activeCall) {
      this.showToast("Você já possui uma chamada em andamento.", "warning");
      return;
    }
    try {
      const localStream = await this.getBestAudioStream(true);
      const pc = new RTCPeerConnection({
        iceServers: [
          { urls: "stun:stun.l.google.com:19302" },
          { urls: "stun:stun1.l.google.com:19302" },
          { urls: "stun:stun2.l.google.com:19302" },
        ],
      });
      localStream
        .getTracks()
        .forEach((track) => pc.addTrack(track, localStream));
      this.activeCall = {
        peerConnection: pc,
        localStream: localStream,
        remoteStream: null,
        targetUser: targetUser,
        chatId: chatId,
        isCaller: true,
        callState: "calling",
        startTime: null,
        durationSeconds: 0,
        timerInterval: null,
        isMuted: false,
        visualizerInterval: null,
      };
      pc.onicecandidate = (event) => {
        if (event.candidate && this.activeCall) {
          FechatAPI.sendCallSignal({
            signal_type: "candidate",
            target_user_id: targetUser.id,
            chat_id: chatId,
            candidate: event.candidate,
          });
        }
      };
      pc.ontrack = (event) => {
        if (event.streams && event.streams[0] && this.activeCall) {
          this.activeCall.remoteStream = event.streams[0];
          let audioEl = document.getElementById("remote-call-audio-player");
          if (!audioEl) {
            audioEl = document.createElement("audio");
            audioEl.id = "remote-call-audio-player";
            audioEl.autoplay = true;
            document.body.appendChild(audioEl);
          }
          audioEl.srcObject = event.streams[0];
          audioEl
            .play()
            .catch((e) => console.warn("Auto-play áudio chamada:", e));
        }
      };
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      if (window.FechatAudio) FechatAudio.startOutgoingRingback();
      this.renderVoiceCallModal();
      const res = await FechatAPI.sendCallSignal({
        signal_type: "initiate",
        target_user_id: targetUser.id,
        chat_id: chatId,
        sdp: offer,
      });
      if (res && res.status === "offline") {
        this.showToast(
          `${targetUser.full_name} está offline no momento.`,
          "warning",
        );
        this.endVoiceCall(false, "offline");
      }
    } catch (err) {
      console.warn("Erro ao iniciar chamada de voz:", err);
      if (
        err.name === "NotAllowedError" ||
        err.name === "PermissionDeniedError"
      ) {
        this.showToast(
          "Permissão de microfone necessária para fazer chamadas.",
          "danger",
        );
      } else {
        this.showToast(
          "Não foi possível iniciar a chamada: " +
            (err.message || "Erro no microfone"),
          "danger",
        );
      }
      this.endVoiceCall(false, "error");
    }
  },
  handleIncomingCallSignal(data) {
    const signalType = data.signal_type;
    if (signalType === "initiate") {
      if (this.activeCall) {
        FechatAPI.sendCallSignal({
          signal_type: "busy",
          target_user_id: data.sender_id,
          chat_id: data.chat_id,
        });
        return;
      }
      this.activeCall = {
        peerConnection: null,
        localStream: null,
        remoteStream: null,
        targetUser: {
          id: data.sender_id,
          full_name: data.sender_name,
          username: data.sender_username,
          numeric_id: data.sender_numeric_id,
          avatar_url: data.sender_avatar,
        },
        chatId: data.chat_id,
        incomingSdp: data.sdp,
        isCaller: false,
        callState: "incoming",
        startTime: null,
        durationSeconds: 0,
        timerInterval: null,
        isMuted: false,
        visualizerInterval: null,
      };
      if (window.FechatAudio) FechatAudio.startIncomingRingtone();
      this.renderVoiceCallModal();
      return;
    }
    if (!this.activeCall) return;
    if (signalType === "accept") {
      if (this.activeCall.isCaller && this.activeCall.peerConnection) {
        if (window.FechatAudio) {
          FechatAudio.stopOutgoingRingback();
          FechatAudio.playCallConnected();
        }
        this.activeCall.peerConnection
          .setRemoteDescription(new RTCSessionDescription(data.sdp))
          .then(() => {
            this.activeCall.callState = "connected";
            this.activeCall.startTime = Date.now();
            this.startCallTimer();
            this.renderVoiceCallModal();
            this.startCallVisualizer();
          })
          .catch((err) => {
            console.warn("Erro ao definir SDP remoto:", err);
          });
      }
    } else if (signalType === "candidate") {
      if (this.activeCall.peerConnection && data.candidate) {
        this.activeCall.peerConnection
          .addIceCandidate(new RTCIceCandidate(data.candidate))
          .catch((err) => {
            console.warn("Erro ao adicionar candidato ICE:", err);
          });
      }
    } else if (signalType === "mute_toggle") {
      if (this.activeCall) {
        this.activeCall.remoteMuted = Boolean(data.is_muted);
        this.renderVoiceCallModal();
      }
    } else if (signalType === "reject") {
      this.showToast("Chamada recusada pelo contato.", "info");
      this.endVoiceCall(false, "rejected");
    } else if (signalType === "busy") {
      this.showToast("O contato está ocupado em outra chamada.", "warning");
      this.endVoiceCall(false, "busy");
    } else if (signalType === "hangup") {
      this.showToast("Chamada finalizada pelo contato.", "info");
      this.endVoiceCall(false, "hangup");
    }
  },
  async acceptIncomingCall() {
    if (!this.activeCall || this.activeCall.isCaller) return;
    if (window.FechatAudio) {
      FechatAudio.stopIncomingRingtone();
      FechatAudio.playCallConnected();
    }
    try {
      const localStream = await this.getBestAudioStream(true);
      const pc = new RTCPeerConnection({
        iceServers: [
          { urls: "stun:stun.l.google.com:19302" },
          { urls: "stun:stun1.l.google.com:19302" },
          { urls: "stun:stun2.l.google.com:19302" },
        ],
      });
      localStream
        .getTracks()
        .forEach((track) => pc.addTrack(track, localStream));
      this.activeCall.peerConnection = pc;
      this.activeCall.localStream = localStream;
      pc.onicecandidate = (event) => {
        if (event.candidate && this.activeCall) {
          FechatAPI.sendCallSignal({
            signal_type: "candidate",
            target_user_id: this.activeCall.targetUser.id,
            chat_id: this.activeCall.chatId,
            candidate: event.candidate,
          });
        }
      };
      pc.ontrack = (event) => {
        if (event.streams && event.streams[0] && this.activeCall) {
          this.activeCall.remoteStream = event.streams[0];
          let audioEl = document.getElementById("remote-call-audio-player");
          if (!audioEl) {
            audioEl = document.createElement("audio");
            audioEl.id = "remote-call-audio-player";
            audioEl.autoplay = true;
            document.body.appendChild(audioEl);
          }
          audioEl.srcObject = event.streams[0];
          audioEl
            .play()
            .catch((e) => console.warn("Auto-play áudio chamada:", e));
        }
      };
      await pc.setRemoteDescription(
        new RTCSessionDescription(this.activeCall.incomingSdp),
      );
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      await FechatAPI.sendCallSignal({
        signal_type: "accept",
        target_user_id: this.activeCall.targetUser.id,
        chat_id: this.activeCall.chatId,
        sdp: answer,
      });
      this.activeCall.callState = "connected";
      this.activeCall.startTime = Date.now();
      this.startCallTimer();
      this.renderVoiceCallModal();
      this.startCallVisualizer();
    } catch (err) {
      console.warn("Erro ao aceitar chamada:", err);
      this.showToast(
        "Falha ao conectar chamada de voz: " +
          (err.message || "Erro no microfone"),
        "danger",
      );
      this.rejectIncomingCall();
    }
  },
  rejectIncomingCall() {
    if (this.activeCall) {
      const chatId = this.activeCall.chatId;
      if (window.FechatAudio) FechatAudio.stopIncomingRingtone();
      FechatAPI.sendCallSignal({
        signal_type: "reject",
        target_user_id: this.activeCall.targetUser.id,
        chat_id: chatId,
      });
      this.sendCallLogMessage(chatId, "rejected", 0);
      this.endVoiceCall(false, "rejected");
    }
  },
  async sendCallLogMessage(chatId, callType, durationSeconds = 0) {
    if (!chatId) return;
    const chat =
      (this.chats || []).find((c) => c.id === chatId) || this.activeChat;
    if (!chat || !chat.aes_channel_key) return;
    const callData = {
      call_status: callType,
      duration: durationSeconds,
      timestamp: new Date().toISOString(),
    };
    const text = `CALL_LOG:${JSON.stringify(callData)}`;
    try {
      const encrypted = await FechatCrypto.encrypt(text, chat.aes_channel_key);
      const sent = await FechatAPI.sendMessage(
        chatId,
        encrypted.ciphertext,
        encrypted.iv,
        encrypted.tag,
        "call_log",
      );
      if (sent) {
        if (this.activeChat && this.activeChat.id === chatId) {
          await this.appendMessageToDOM(sent);
          this.scrollToBottom();
        }
        const found = (this.chats || []).find((c) => c.id === chatId);
        if (found) {
          found.last_message = sent;
          found.updated_at = sent.created_at || new Date().toISOString();
          this.renderSidebarList();
        }
      }
    } catch (e) {
      console.warn("Erro ao enviar registro de chamada no chat:", e);
    }
  },
  endVoiceCall(sendHangup = true, reason = "ended") {
    if (!this.activeCall) return;
    const chatId = this.activeCall.chatId;
    const dur = this.activeCall.durationSeconds || 0;
    const wasConnected = this.activeCall.callState === "connected";
    const isCaller = this.activeCall.isCaller;
    if (window.FechatAudio) {
      FechatAudio.stopIncomingRingtone();
      FechatAudio.stopOutgoingRingback();
      FechatAudio.playCallEnded();
    }
    if (sendHangup && this.activeCall.targetUser) {
      FechatAPI.sendCallSignal({
        signal_type: "hangup",
        target_user_id: this.activeCall.targetUser.id,
        chat_id: chatId,
        duration: dur,
      });
    }
    if (this.activeCall.peerConnection) {
      try {
        this.activeCall.peerConnection.close();
      } catch (_) {}
    }
    if (this.activeCall.localStream) {
      try {
        this.activeCall.localStream.getTracks().forEach((t) => t.stop());
      } catch (_) {}
    }
    clearInterval(this.activeCall.timerInterval);
    clearInterval(this.activeCall.visualizerInterval);
    const audioEl = document.getElementById("remote-call-audio-player");
    if (audioEl) audioEl.remove();
    this.activeCall = null;
    this.closeVoiceCallModal();
    if (wasConnected) {
      this.sendCallLogMessage(chatId, "ended", dur);
    } else if (
      isCaller &&
      (reason === "offline" || reason === "busy" || reason === "error")
    ) {
      this.sendCallLogMessage(chatId, "missed", 0);
    } else if (isCaller && reason === "ended") {
      this.sendCallLogMessage(chatId, "missed", 0);
    }
  },
  toggleCallMute() {
    if (!this.activeCall || !this.activeCall.localStream) return;
    const audioTrack = this.activeCall.localStream.getAudioTracks()[0];
    if (audioTrack) {
      audioTrack.enabled = !audioTrack.enabled;
      this.activeCall.isMuted = !audioTrack.enabled;
      if (this.activeCall.targetUser) {
        FechatAPI.sendCallSignal({
          signal_type: "mute_toggle",
          target_user_id: this.activeCall.targetUser.id,
          chat_id: this.activeCall.chatId,
          is_muted: this.activeCall.isMuted,
        });
      }
      const muteBtn = document.getElementById("call-mute-btn");
      if (muteBtn) {
        if (this.activeCall.isMuted) {
          muteBtn.classList.add("active");
          muteBtn.innerHTML = '<i data-lucide="mic-off"></i>';
        } else {
          muteBtn.classList.remove("active");
          muteBtn.innerHTML = '<i data-lucide="mic"></i>';
        }
        this.refreshIcons();
      }
      this.renderVoiceCallModal();
    }
  },
  startCallTimer() {
    if (!this.activeCall) return;
    clearInterval(this.activeCall.timerInterval);
    this.activeCall.timerInterval = setInterval(() => {
      if (!this.activeCall) return;
      this.activeCall.durationSeconds++;
      const mins = String(
        Math.floor(this.activeCall.durationSeconds / 60),
      ).padStart(2, "0");
      const secs = String(this.activeCall.durationSeconds % 60).padStart(
        2,
        "0",
      );
      const timerEl = document.getElementById("call-timer-display");
      if (timerEl) timerEl.textContent = `${mins}:${secs}`;
    }, 1e3);
  },
  startCallVisualizer() {
    if (!this.activeCall) return;
    const bars = document.querySelectorAll(".call-audio-bar");
    if (bars.length === 0) return;
    clearInterval(this.activeCall.visualizerInterval);
    this.activeCall.visualizerInterval = setInterval(() => {
      if (!this.activeCall) return;
      if (this.activeCall.remoteMuted) {
        bars.forEach((bar) => {
          bar.style.height = "4px";
        });
        return;
      }
      bars.forEach((bar) => {
        const h = Math.floor(Math.random() * 24) + 6;
        bar.style.height = `${h}px`;
      });
    }, 100);
  },
  renderVoiceCallModal() {
    if (!this.activeCall) return;
    let modalOverlay = document.getElementById("voice-call-modal-overlay");
    if (!modalOverlay) {
      modalOverlay = document.createElement("div");
      modalOverlay.id = "voice-call-modal-overlay";
      modalOverlay.className = "voice-call-overlay";
      document.body.appendChild(modalOverlay);
    }
    const u = this.activeCall.targetUser;
    const isIncoming = this.activeCall.callState === "incoming";
    const isConnected = this.activeCall.callState === "connected";
    const isRemoteMuted = Boolean(this.activeCall.remoteMuted);
    const avatarClass = isConnected ? "connected" : "calling";
    let statusText = "Chamando...";
    let statusBadgeClass = "ringing";
    if (isIncoming) {
      statusText = "Chamada de Voz Recebida";
      statusBadgeClass = "ringing";
    } else if (isConnected) {
      statusText = "Chamada em Andamento";
      statusBadgeClass = "connected";
    }
    modalOverlay.innerHTML = `\n      <div class="voice-call-card">\n        <div class="call-avatar-wrapper ${avatarClass}">\n          <img src="${u.avatar_url || `https://api.dicebear.com/7.x/identicon/svg?seed=${u.username}`}" class="call-avatar-img" />\n        </div>\n        <h3 class="call-user-name">${this.escapeHTML(u.full_name || u.username)}</h3>\n        <div class="call-user-id">@${this.escapeHTML(u.username)} • ${this.formatId(u.numeric_id || "")}</div>\n        <div class="call-status-badge ${statusBadgeClass}">\n          <i data-lucide="shield-check" style="width:14px; height:14px;"></i> ${statusText}\n        </div>\n\n        ${isRemoteMuted ? `\n          <div class="remote-mute-badge">\n            <i data-lucide="mic-off" style="width:13px; height:13px;"></i>\n            <span>${this.escapeHTML(u.full_name || u.username)} mutou o microfone</span>\n          </div>\n        ` : ""}\n\n        ${isConnected ? `\n          <div class="call-timer-text" id="call-timer-display">${String(Math.floor(this.activeCall.durationSeconds / 60)).padStart(2, "0")}:${String(this.activeCall.durationSeconds % 60).padStart(2, "0")}</div>\n          <div class="call-audio-visualizer">\n            <div class="call-audio-bar"></div>\n            <div class="call-audio-bar"></div>\n            <div class="call-audio-bar"></div>\n            <div class="call-audio-bar"></div>\n            <div class="call-audio-bar"></div>\n            <div class="call-audio-bar"></div>\n            <div class="call-audio-bar"></div>\n          </div>\n        ` : ""}\n\n        <div class="call-controls-row">\n          ${isIncoming ? `\n            <button class="call-action-btn call-btn-end" onclick="App.rejectIncomingCall()" title="Recusar Chamada">\n              <i data-lucide="phone-off" style="width:24px; height:24px;"></i>\n            </button>\n            <button class="call-action-btn call-btn-accept" onclick="App.acceptIncomingCall()" title="Atender Chamada">\n              <i data-lucide="phone" style="width:24px; height:24px;"></i>\n            </button>\n          ` : `\n            ${isConnected ? `\n              <button class="call-action-btn call-btn-mute ${this.activeCall.isMuted ? "active" : ""}" id="call-mute-btn" onclick="App.toggleCallMute()" title="${this.activeCall.isMuted ? "Desmutar Microfone" : "Mutar Microfone"}">\n                <i data-lucide="${this.activeCall.isMuted ? "mic-off" : "mic"}" style="width:22px; height:22px;"></i>\n              </button>\n            ` : ""}\n            <button class="call-action-btn call-btn-end" onclick="App.endVoiceCall(true)" title="Encerrar Chamada">\n              <i data-lucide="phone-off" style="width:24px; height:24px;"></i>\n            </button>\n          `}\n        </div>\n\n        <div class="call-e2ee-tag">\n          <i data-lucide="lock" style="width:12px; height:12px; color:#10b981;"></i>\n          <span>Criptografia de Ponta a Ponta (WebRTC DTLS-SRTP)</span>\n        </div>\n      </div>\n    `;
    this.refreshIcons();
  },
  closeVoiceCallModal() {
    const modalOverlay = document.getElementById("voice-call-modal-overlay");
    if (modalOverlay) modalOverlay.remove();
  },
  toggleAttachmentMenu(e) {
    e.stopPropagation();
    const popover = document.getElementById("attachment-popover");
    if (!popover) return;
    this.isAttachmentMenuOpen = !this.isAttachmentMenuOpen;
    popover.style.display = this.isAttachmentMenuOpen ? "flex" : "none";
    this.refreshIcons();
  },
  closeAttachmentMenu() {
    const popover = document.getElementById("attachment-popover");
    if (popover) {
      popover.style.display = "none";
      this.isAttachmentMenuOpen = false;
    }
  },
  triggerFileInput(type) {
    this.closeAttachmentMenu();
    if (type === "media") document.getElementById("media-file-input").click();
    if (type === "audio") document.getElementById("audio-file-input").click();
    if (type === "document")
      document.getElementById("document-file-input").click();
  },
  async handleMediaUpload(file, typeCategory) {
    if (!file || !this.activeChat) return;
    this.showToast(`Enviando ${file.name || "mídia"} com criptografia...`);
    try {
      const uploadRes = await FechatAPI.uploadChatMedia(file);
      let msgType = "file";
      if (typeCategory === "voice") msgType = "voice";
      else if (file.type.startsWith("image/")) msgType = "image";
      else if (file.type.startsWith("video/")) msgType = "video";
      else if (file.type.startsWith("audio/")) msgType = "audio";
      const encrypted = await FechatCrypto.encrypt(
        `[${msgType.toUpperCase()}]`,
        this.activeChat.aes_channel_key,
      );
      const sentMsg = await FechatAPI.sendMessage(
        this.activeChat.id,
        encrypted.ciphertext,
        encrypted.iv,
        encrypted.tag,
        msgType,
        uploadRes.media_url,
        uploadRes.media_name,
        uploadRes.media_size,
      );
      if (sentMsg) {
        await this.appendMessageToDOM(sentMsg);
        const chat = (this.chats || []).find(
          (c) => c.id === this.activeChat.id,
        );
        if (chat) {
          chat.last_message = sentMsg;
          chat.updated_at = sentMsg.created_at || new Date().toISOString();
          this.chats.sort(
            (a, b) =>
              new Date(b.updated_at || b.created_at) -
              new Date(a.updated_at || a.created_at),
          );
          this.renderSidebarList();
        }
      }
      if (window.FechatAudio) FechatAudio.playSent();
      this.scrollToBottom();
    } catch (e) {
      console.error("Erro ao enviar anexo:", e);
      this.showToast("Falha ao enviar anexo.", "danger");
    }
  },
  emojiDatabase: {
    smileys: [
      "😀",
      "😁",
      "😂",
      "🤣",
      "😃",
      "😄",
      "😅",
      "😆",
      "😉",
      "😊",
      "😋",
      "😎",
      "😍",
      "😘",
      "😗",
      "😙",
      "😚",
      "☺️",
      "😇",
      "🥳",
      "😏",
      "😌",
      "🤤",
      "😴",
      "😷",
      "🤒",
      "🤕",
      "🤯",
      "🥶",
      "🥵",
      "😱",
      "😡",
      "🤬",
      "🤡",
      "👻",
      "💀",
      "👽",
    ],
    gestures: [
      "👍",
      "👎",
      "👏",
      "🙌",
      "🤝",
      "✌️",
      "🤞",
      "🤙",
      "👊",
      "✊",
      "🤛",
      "🤜",
      "🙏",
      "💪",
      "👈",
      "👉",
      "👆",
      "👇",
      "✋",
      "🤚",
      "🖐️",
      "🖖",
      "👋",
      "🧑",
      "👨",
      "👩",
      "👶",
      "👵",
      "👴",
    ],
    hearts: [
      "❤️",
      "🧡",
      "💛",
      "💚",
      "💙",
      "💜",
      "🖤",
      "🤍",
      "🤎",
      "💔",
      "❣️",
      "💕",
      "💞",
      "💓",
      "💗",
      "💖",
      "💘",
      "💝",
      "💟",
      "💌",
      "💋",
      "💯",
    ],
    objects: [
      "🔥",
      "✨",
      "⭐",
      "🌟",
      "💫",
      "💥",
      "🚀",
      "🎉",
      "🎊",
      "🏆",
      "💎",
      "🎁",
      "🎈",
      "🍻",
      "☕",
      "🍕",
      "🍔",
      "🍟",
      "🍿",
      "⚽",
      "🎮",
      "🎯",
      "🔒",
      "🛡️",
    ],
  },
  toggleEmojiPicker(e) {
    e.stopPropagation();
    const popover = document.getElementById("emoji-popover");
    if (!popover) return;
    this.isEmojiPickerOpen = !this.isEmojiPickerOpen;
    popover.style.display = this.isEmojiPickerOpen ? "flex" : "none";
    if (this.isEmojiPickerOpen) this.switchEmojiCat("smileys");
  },
  closeEmojiPicker() {
    const popover = document.getElementById("emoji-popover");
    if (popover) {
      popover.style.display = "none";
      this.isEmojiPickerOpen = false;
    }
  },
  switchEmojiCat(cat) {
    document
      .querySelectorAll(".emoji-cat-btn")
      .forEach((btn) => btn.classList.remove("active"));
    const grid = document.getElementById("emoji-grid-content");
    if (!grid) return;
    grid.innerHTML = "";
    const emojis = this.emojiDatabase[cat] || this.emojiDatabase.smileys;
    emojis.forEach((emo) => {
      const b = document.createElement("button");
      b.className = "emoji-btn";
      b.textContent = emo;
      b.onclick = () => App.insertEmoji(emo);
      grid.appendChild(b);
    });
  },
  insertEmoji(emoji) {
    const input = document.getElementById("chat-message-input");
    if (input) {
      input.value += emoji;
      input.focus();
    }
  },
  async handleIncomingMessage(msg) {
    const isCurrentActiveChat =
      this.activeChat && this.activeChat.id === msg.chat_id;
    if (isCurrentActiveChat) {
      await this.appendMessageToDOM(msg);
      this.scrollToBottom();
      if (window.FechatAudio) FechatAudio.playReceived();
      FechatAPI.markChatRead(msg.chat_id).catch(() => {});
    } else {
      this.unreadCounts[msg.chat_id] =
        (this.unreadCounts[msg.chat_id] || 0) + 1;
      if (window.FechatAudio) FechatAudio.playReceived();
      this.updateUnreadBadges();
      const senderName = msg.sender ? msg.sender.full_name : "Novo Contato";
      this.showToast(`💬 Nova mensagem de ${senderName}`);
      if (
        document.hidden &&
        "Notification" in window &&
        Notification.permission === "granted"
      ) {
        try {
          new Notification(`Fechat: ${senderName}`, {
            body: "Mensagem segura recebida (criptografia AES-256)",
            icon:
              msg.sender?.avatar_url ||
              "https://api.dicebear.com/7.x/bottts/svg?seed=fechat",
          });
        } catch {}
      }
    }
    await this.loadData();
    this.updateUnreadBadges();
  },
  handlePresenceUpdate(data) {
    if (data.is_online) {
      this.onlineUsers.add(data.user_id);
    } else {
      this.onlineUsers.delete(data.user_id);
    }
    if (data.last_seen) {
      this.contacts.forEach((c) => {
        if (c.contact_user && c.contact_user.id === data.user_id) {
          c.contact_user.last_seen = data.last_seen;
        }
      });
      this.chats.forEach((chat) => {
        if (!chat.is_group && chat.members) {
          chat.members.forEach((m) => {
            if (m.user && m.user.id === data.user_id) {
              m.user.last_seen = data.last_seen;
            }
          });
        }
      });
    }
    if (this.activeChat && !this.activeChat.is_group) {
      const other = this.activeChat.members.find(
        (m) => m.user_id === data.user_id,
      );
      if (other && other.user) {
        if (data.last_seen) other.user.last_seen = data.last_seen;
        const statusEl = document.getElementById("chat-active-status");
        if (
          statusEl &&
          !this.activeChatBlockStatus.am_i_blocked &&
          !this.activeChatBlockStatus.is_blocked_by_me
        ) {
          statusEl.innerHTML = formatLastSeen(
            other.user.last_seen,
            data.is_online,
          );
        }
        const dot = document.querySelector(
          ".chat-header-user .online-dot, .chat-header-user .offline-dot",
        );
        if (dot) dot.className = data.is_online ? "online-dot" : "offline-dot";
      }
    }
    this.renderSidebarList();
  },
  async handleBlockUpdate(data) {
    if (this.activeChat && !this.activeChat.is_group) {
      const other = this.activeChat.members.find(
        (m) => m.user_id !== this.currentUser.id,
      );
      if (
        other &&
        (other.user.id === data.target_user_id ||
          other.user.id === data.blocker_user_id)
      ) {
        if (data.am_i_blocked !== undefined)
          this.activeChatBlockStatus.am_i_blocked = data.am_i_blocked;
        if (data.is_blocked_by_me !== undefined)
          this.activeChatBlockStatus.is_blocked_by_me = data.is_blocked_by_me;
        const workspace = document.getElementById("primary-workspace");
        workspace.innerHTML = this.renderChatWindowHTML();
        this.refreshIcons();
        await this.loadMessages(this.activeChat.id);
      }
    }
    if (data.am_i_blocked) {
      this.showToast("Você foi bloqueado(a) por um usuário.", "danger");
    }
  },
  async handleBlockUser(targetUserId) {
    this.closeChatMenu();
    if (window.Swal) {
      const result = await Swal.fire({
        title: "Bloquear Contato?",
        text: "Esta pessoa não poderá mais enviar mensagens para você nem ver quando você está online.",
        icon: "warning",
        showCancelButton: true,
        confirmButtonColor: "#ef4444",
        cancelButtonColor: "#475569",
        confirmButtonText: "Sim, Bloquear",
        cancelButtonText: "Cancelar",
      });
      if (!result.isConfirmed) return;
    }
    try {
      await FechatAPI.blockUser(targetUserId);
      this.showToast("Contato bloqueado com sucesso.", "success");
      this.activeChatBlockStatus.is_blocked_by_me = true;
      const workspace = document.getElementById("primary-workspace");
      workspace.innerHTML = this.renderChatWindowHTML();
      this.refreshIcons();
      await this.loadMessages(this.activeChat.id);
      await this.loadData();
    } catch (e) {
      this.showToast(e.message, "danger");
    }
  },
  async handleUnblockUser(targetUserId) {
    this.closeChatMenu();
    try {
      await FechatAPI.unblockUser(targetUserId);
      this.showToast("Contato desbloqueado com sucesso!", "success");
      this.activeChatBlockStatus.is_blocked_by_me = false;
      const workspace = document.getElementById("primary-workspace");
      workspace.innerHTML = this.renderChatWindowHTML();
      this.refreshIcons();
      await this.loadMessages(this.activeChat.id);
      await this.loadData();
    } catch (e) {
      this.showToast(e.message, "danger");
    }
  },
  handleTypingUpdate(data) {
    if (this.activeChat && this.activeChat.id === data.chat_id) {
      const statusEl = document.getElementById("chat-active-status");
      if (
        statusEl &&
        !this.activeChatBlockStatus.am_i_blocked &&
        !this.activeChatBlockStatus.is_blocked_by_me
      ) {
        if (data.is_typing) {
          statusEl.innerHTML = `<span style="color:#a5b4fc; font-style:italic;">💬 ${t("typing_indicator")}</span>`;
        } else {
          const other = this.activeChat.members.find(
            (m) => m.user_id === data.user_id,
          );
          const isOnline = this.onlineUsers.has(data.user_id);
          statusEl.innerHTML = formatLastSeen(
            other ? other.user.last_seen : null,
            isOnline,
          );
        }
      }
    }
  },
  handleReadReceipt(data) {
    if (this.activeChat && this.activeChat.id === data.chat_id) {
      document
        .querySelectorAll(".message-row.sent .tick-icon")
        .forEach((tick) => {
          tick.className = "tick-icon tick-read";
          tick.title = "Lido";
        });
    }
  },
  scrollToBottom() {
    const container = document.getElementById("messages-container");
    if (container) container.scrollTop = container.scrollHeight;
  },
  escapeHTML(str) {
    return str.replace(
      /[&<>'"]/g,
      (tag) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          "'": "&#39;",
          '"': "&quot;",
        })[tag] || tag,
    );
  },
  renderProfileView() {
    const avatarUrl =
      this.currentUser.avatar_url ||
      `https://api.dicebear.com/7.x/bottts/svg?seed=${this.currentUser.username}`;
    return `\n      <div class="settings-section">\n        <div class="view-header-mobile">\n          <button class="btn-icon mobile-back-btn" onclick="App.closeActiveChat()" title="Voltar">\n            <i data-lucide="arrow-left"></i>\n          </button>\n          <h2 style="font-size:18px; font-weight:700; font-family:var(--font-heading);">Meu Perfil</h2>\n        </div>\n\n        <div class="settings-card" style="text-align:center; align-items:center; padding:28px 20px;">\n          \x3c!-- FOTO DE PERFIL / GIF --\x3e\n          <div class="avatar-upload-container" onclick="document.getElementById('profile-avatar-file-input').click()" title="Alterar foto de perfil">\n            <div class="avatar-wrapper" style="width:100px; height:100px;">\n              <img src="${avatarUrl}" class="avatar-img" style="border:3px solid var(--primary);" />\n              <div class="avatar-upload-overlay">\n                <i data-lucide="camera" style="width:26px; height:26px;"></i>\n              </div>\n            </div>\n          </div>\n          <input type="file" id="profile-avatar-file-input" style="display:none;" accept="image/png, image/jpeg, image/webp, image/gif" onchange="App.handleAvatarFileChange(this.files[0])" />\n          <p style="font-size:12px; color:var(--text-muted); margin-top:8px;">Toque na imagem para escolher uma foto ou GIF animado</p>\n\n          <h2 style="font-size:22px; font-weight:800; font-family:var(--font-heading); margin-top:14px; display:flex; align-items:center; justify-content:center; gap:6px;">\n            ${this.escapeHTML(this.currentUser.full_name)}\n            ${this.currentUser.is_verified ? '<span class="verified-badge"><i data-lucide="badge-check"></i></span>' : ""}\n          </h2>\n          <p style="color:var(--text-muted); font-size:14px;">@${this.escapeHTML(this.currentUser.username)}</p>\n          \n          \x3c!-- CARTÃO DE ID DE 12 DÍGITOS --\x3e\n          <div style="background:rgba(99, 102, 241, 0.12); border:1px solid rgba(99, 102, 241, 0.3); border-radius:var(--radius-lg); padding:16px 20px; margin:20px 0; width:100%; max-width:420px;">\n            <div style="font-size:11.5px; color:#a5b4fc; font-weight:600; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">\n              ${t("profile_id_label")}\n            </div>\n            <div style="font-size:22px; font-family:monospace; font-weight:800; color:#ffffff; letter-spacing:2px;">\n              ${this.formatId(this.currentUser.numeric_id)}\n            </div>\n            <p style="font-size:12px; color:var(--text-muted); margin-top:6px;">\n              ${t("profile_id_desc")}\n            </p>\n            <button class="btn-primary" onclick="App.copyMyId()" style="margin-top:12px; font-size:12.5px; padding:7px 16px;">\n              <i data-lucide="copy" style="width:14px; height:14px;"></i> ${t("copy_id_btn")}\n            </button>\n          </div>\n        </div>\n\n        \x3c!-- FORMULÁRIO DE EDIÇÃO ORGANIZADO & PROTEGIDO --\x3e\n        <div class="settings-card" style="padding:24px;">\n          <h3 style="font-size:16px; font-weight:700; font-family:var(--font-heading); margin-bottom:16px; display:flex; align-items:center; gap:8px;">\n            <i data-lucide="user-check" style="color:var(--primary);"></i> Informações Pessoais\n          </h3>\n          \n          <form onsubmit="App.saveProfileChanges(event)" style="display:flex; flex-direction:column; gap:16px;">\n            <div class="form-group">\n              <label class="form-label">${t("full_name_label")}</label>\n              <input \n                type="text" \n                id="profile-name-input" \n                class="form-input" \n                maxlength="70" \n                required \n                placeholder="Ex: Diego Rafael" \n                value="${this.escapeHTML(this.currentUser.full_name)}" \n              />\n              <span style="font-size:11px; color:var(--text-dim);">Como as pessoas verão você nas conversas.</span>\n            </div>\n\n            <div class="form-group">\n              <label class="form-label" style="display:flex; justify-content:space-between; align-items:center;">\n                <span>Nome de Usuário (@)</span>\n                ${this.currentUser.is_new_account ? `\n                  <span style="color:#f59e0b; font-size:11.5px; font-weight:600;">🔒 Bloqueado (Conta Nova: ${this.currentUser.days_until_username_unlock}d)</span>\n                ` : !this.currentUser.can_change_username ? `\n                  <span style="color:#f59e0b; font-size:11.5px; font-weight:600;">⏳ Bloqueado (${this.currentUser.days_until_cooldown_ends}d)</span>\n                ` : `\n                  <span style="color:#10b981; font-size:11.5px; font-weight:600;">🔓 Alteração Liberada</span>\n                `}\n              </label>\n              <input \n                type="text" \n                id="profile-username-input" \n                class="form-input" \n                maxlength="30" \n                required \n                pattern="^[a-zA-Z0-9_.]{3,30}$" \n                placeholder="Ex: diego_rafael" \n                value="${this.escapeHTML(this.currentUser.username)}" \n                ${!this.currentUser.can_change_username ? 'disabled style="opacity:0.6; cursor:not-allowed;"' : ""}\n              />\n              <span style="font-size:11.5px; color:var(--text-dim);">\n                ${this.currentUser.is_new_account ? `Por segurança contra fraudes, o nome de usuário fica bloqueado nos primeiros 30 dias (${this.currentUser.days_until_username_unlock} dia(s) restante(s)).` : !this.currentUser.can_change_username ? `Você só pode alterar seu nome de usuário 1 vez a cada 7 dias (${this.currentUser.days_until_cooldown_ends} dia(s) restante(s)).` : `Apenas letras, números, ponto (.) e underline (_). Permitido 1 alteração a cada 7 dias.`}\n              </span>\n            </div>\n\n            <div class="form-group">\n              <label class="form-label">${t("bio_label")}</label>\n              <textarea \n                id="profile-bio-input" \n                class="form-input" \n                maxlength="150" \n                placeholder="Ex: Olá! Estou usando o Fechat." \n                style="min-height:80px; font-family:inherit; resize:vertical;"\n              >${this.escapeHTML(this.currentUser.bio || "")}</textarea>\n              <span style="font-size:11px; color:var(--text-dim);">Frase de status ou recado no seu perfil (máx. 150 caracteres).</span>\n            </div>\n\n            <button type="submit" class="btn-primary" style="margin-top:6px; font-size:13.5px; padding:10px 20px;">\n              <i data-lucide="check" style="width:16px; height:16px;"></i> ${t("save_profile")}\n            </button>\n          </form>\n        </div>\n      </div>\n    `;
  },
  async handleAvatarFileChange(file) {
    if (!file) return;
    try {
      this.showToast("Atualizando foto de perfil...");
      const res = await FechatAPI.uploadAvatar(file);
      this.currentUser.avatar_url = res.avatar_url;
      this.showToast("Foto de perfil atualizada com sucesso!", "success");
      this.renderApp();
    } catch (e) {
      this.showToast(e.message, "danger");
    }
  },
  copyMyId() {
    navigator.clipboard.writeText(this.formatId(this.currentUser.numeric_id));
    this.showToast(t("copied_success"), "success");
  },
  async saveProfileChanges(e) {
    if (e && e.preventDefault) e.preventDefault();
    const fullNameInput = document.getElementById("profile-name-input");
    const usernameInput = document.getElementById("profile-username-input");
    const bioInput = document.getElementById("profile-bio-input");
    const fullName = fullNameInput ? fullNameInput.value.trim() : "";
    const username = usernameInput
      ? usernameInput.value.trim().toLowerCase()
      : "";
    const bio = bioInput ? bioInput.value.trim() : "";
    if (!fullName || fullName.length < 2) {
      this.showToast(
        "O nome completo deve ter pelo menos 2 caracteres.",
        "warning",
      );
      return;
    }
    const payload = { full_name: fullName, bio: bio };
    if (username && username !== this.currentUser.username) {
      if (!this.currentUser.can_change_username) {
        this.showToast(
          "Seu nome de usuário não pode ser alterado no momento devido às regras de governança e segurança.",
          "warning",
        );
        return;
      }
      const usernameRegex = /^[a-zA-Z0-9_.]{3,30}$/;
      if (!usernameRegex.test(username)) {
        this.showToast(
          "O nome de usuário deve conter apenas letras, números, ponto (.) ou underline (_), com 3 a 30 caracteres.",
          "warning",
        );
        return;
      }
      payload.username = username;
    }
    try {
      this.currentUser = await FechatAPI.updateProfile(payload);
      this.showToast("Perfil atualizado com sucesso!", "success");
      this.renderApp();
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  renderSettingsView() {
    return `\n      <div class="settings-section">\n        <div class="view-header-mobile">\n          <button class="btn-icon mobile-back-btn" onclick="App.closeActiveChat()" title="Voltar">\n            <i data-lucide="arrow-left"></i>\n          </button>\n          <h2 style="font-size:18px; font-weight:700; font-family:var(--font-heading);">${t("nav_settings")}</h2>\n        </div>\n        \n        <div class="settings-card">\n          <h3 style="font-size:16px; font-weight:700;">🌐 ${t("language_label")}</h3>\n          <div style="display:flex; gap:12px; margin-top:8px; flex-wrap:wrap;">\n            <button class="btn-secondary ${currentLang === "pt_BR" ? "btn-primary" : ""}" onclick="setLanguage('pt_BR'); App.renderApp()">\n              🇧🇷 Português (Brasil)\n            </button>\n            <button class="btn-secondary ${currentLang === "en_US" ? "btn-primary" : ""}" onclick="setLanguage('en_US'); App.renderApp()">\n              🇺🇸 English (US)\n            </button>\n          </div>\n        </div>\n\n        <div class="settings-card">\n          <h3 style="font-size:16px; font-weight:700;">🎨 ${t("theme_label")}</h3>\n          <div style="display:flex; gap:12px; margin-top:8px; flex-wrap:wrap;">\n            <button class="btn-secondary" onclick="App.setTheme('dark'); App.renderApp()">\n              🌙 ${t("theme_dark")}\n            </button>\n            <button class="btn-secondary" onclick="App.setTheme('light'); App.renderApp()">\n              ☀️ ${t("theme_light")}\n            </button>\n          </div>\n        </div>\n\n        <div class="settings-card">\n          <h3 style="font-size:16px; font-weight:700;">🔔 Efeitos Sonoros & Notificações</h3>\n          <p style="color:var(--text-muted); font-size:13px; margin:6px 0 12px 0;">\n            Sons gerados com sintetizador nativo Web Audio API no envio, recebimento e gravação de áudio.\n          </p>\n          <div style="display:flex; gap:10px; flex-wrap:wrap;">\n            <button class="btn-secondary" onclick="const muted = FechatAudio.toggleMute(); App.showToast(muted ? 'Efeitos sonoros desativados.' : 'Efeitos sonoros ativados!', 'success'); App.renderApp();">\n              ${window.FechatAudio && window.FechatAudio.isMuted ? "🔇 Ativar Sons" : "🔊 Silenciar Sons"}\n            </button>\n            <button class="btn-secondary" onclick="FechatAudio.playReceived(); App.showToast('Testando som de recebimento!');">\n              🎵 Testar Som de Mensagem\n            </button>\n            <button class="btn-secondary" onclick="FechatAudio.playSent(); App.showToast('Testando som de envio!');">\n              📤 Testar Som de Envio\n            </button>\n          </div>\n        </div>\n\n        <div class="settings-card">\n          <h3 style="font-size:16px; font-weight:700;">🛡️ Privacidade & Criptografia</h3>\n          <p style="color:var(--text-muted); font-size:13px; line-height:1.5;">\n            Suas mensagens e mídias operam com chaves AES-256-GCM. Nenhum servidor intermediário armazena suas mensagens em texto simples.\n          </p>\n          <div style="font-family:monospace; font-size:11px; background:rgba(0,0,0,0.3); padding:10px; border-radius:6px; color:#a5b4fc; word-break:break-all;">\n            Cipher Suite: AES-256-GCM (128-bit Auth Tag, 96-bit CSPRNG Nonce)\n          </div>\n        </div>\n\n        <div class="settings-card">\n          <button class="btn-danger" onclick="App.logout()">\n            <i data-lucide="log-out"></i> ${t("logout_btn")}\n          </button>\n        </div>\n      </div>\n    `;
  },
  judicialActiveSubTab: "investigation",
  switchJudicialTab(subTab) {
    if (!this.currentUser || !this.currentUser.is_admin) return;
    this.judicialActiveSubTab = subTab;
    document
      .querySelectorAll(".judicial-tab-btn")
      .forEach((btn) => btn.classList.remove("active"));
    const activeBtn = document.getElementById(`judicial-tab-btn-${subTab}`);
    if (activeBtn) activeBtn.classList.add("active");
    document
      .querySelectorAll(".judicial-subtab-content")
      .forEach((el) => (el.style.display = "none"));
    const contentEl = document.getElementById(
      `judicial-subtab-content-${subTab}`,
    );
    if (contentEl) contentEl.style.display = "block";
    this.loadComplianceData();
  },
  async handleAdminLogin(e) {
    if (e) e.preventDefault();
    const usernameInput = document.getElementById("admin-login-username");
    const passwordInput = document.getElementById("admin-login-password");
    const loginId = usernameInput ? usernameInput.value.trim() : "admin";
    const password = passwordInput ? passwordInput.value : "";
    if (!password) {
      this.showToast("Digite a senha de administrador.", "danger");
      return;
    }
    try {
      const res = await FechatAPI.login(loginId, password);
      FechatAPI.setToken(res.access_token);
      this.currentUser = res.user;
      socketClient.connect(res.access_token);
      this.showToast(
        `Autenticado como ${res.user.full_name}!`,
        "success",
      );
      this.renderApp();
      await this.loadData();
    } catch (err) {
      this.showToast(
        err.message || "Falha na autenticação de administrador.",
        "danger",
      );
    }
  },
  renderComplianceView() {
    if (!this.currentUser || !this.currentUser.is_admin) {
      return `\n        <div class="settings-section" style="max-width:540px; margin:40px auto; text-align:center;">\n          <div class="view-header-mobile">\n            <button class="btn-icon mobile-back-btn" onclick="App.closeActiveChat()" title="Voltar">\n              <i data-lucide="arrow-left"></i>\n            </button>\n            <h2 style="font-size:18px; font-weight:700; font-family:var(--font-heading); color:var(--danger);">Portal Judicial</h2>\n          </div>\n          <div class="settings-card" style="padding:32px; border-color:rgba(239, 68, 68, 0.3); background:rgba(19, 27, 46, 0.85);">\n            <div class="brand-logo" style="width:68px; height:68px; margin:0 auto 16px; background:rgba(239, 68, 68, 0.15); color:var(--danger); border-color:rgba(239, 68, 68, 0.35);">\n              <i data-lucide="shield-alert" style="width:34px; height:34px;"></i>\n            </div>\n            <h2 style="font-size:22px; font-weight:800; color:var(--danger); margin-bottom:8px; font-family:var(--font-heading);">⚖️ Portal de Conformidade & Acesso Judicial</h2>\n            <p style="color:var(--text-muted); font-size:13.5px; line-height:1.5; margin-bottom:24px;">\n              Área restrita a autoridades judiciais, delegacias de crimes cibernéticos e administradores de conformidade da plataforma.\n            </p>\n            <form onsubmit="App.handleAdminLogin(event)" style="display:flex; flex-direction:column; gap:14px; text-align:left;">\n              <div class="form-group">\n                <label class="form-label">Identificação de Autoridade / Administrador</label>\n                <input type="text" id="admin-login-username" class="form-input" placeholder="admin ou e-mail institucional" required value="admin" />\n              </div>\n              <div class="form-group">\n                <label class="form-label">Senha de Acesso Criptográfico</label>\n                <input type="password" id="admin-login-password" class="form-input" placeholder="Digite sua senha de segurança" required />\n              </div>\n              <button type="submit" class="btn-primary" style="background:var(--danger); padding:12px; margin-top:8px; font-size:14px; display:flex; align-items:center; justify-content:center; gap:8px;">\n                <i data-lucide="key" style="width:16px; height:16px;"></i> Autenticar e Acessar Painel Judicial\n              </button>\n            </form>\n          </div>\n        </div>\n      `;
    }
    const currentSub = this.judicialActiveSubTab || "investigation";
    setTimeout(() => this.loadComplianceData(), 60);
    return `\n      <div class="settings-section" style="max-width:960px;">\n        <div class="view-header-mobile">\n          <button class="btn-icon mobile-back-btn" onclick="App.closeActiveChat()" title="Voltar">\n            <i data-lucide="arrow-left"></i>\n          </button>\n          <h2 style="font-size:18px; font-weight:700; font-family:var(--font-heading); color:var(--danger);">Painel Judicial</h2>\n        </div>\n        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:14px;">\n          <div>\n            <h2 style="font-size:22px; font-weight:800; font-family:var(--font-heading); color:var(--danger);">⚖️ ${t("compliance_title")}</h2>\n            <p style="color:var(--text-muted); font-size:13px; margin-top:2px;">Auditoria forense, mandados judiciais e controle de conformidade legal</p>\n          </div>\n          <div style="display:flex; align-items:center; gap:8px;">\n            <span class="compliance-badge-restricted">Oficial Autorizado</span>\n            <span class="id-badge" style="background:rgba(239, 68, 68, 0.15); color:#fca5a5;">${this.currentUser.full_name || "Admin"}</span>\n          </div>\n        </div>\n\n        \x3c!-- NAVEGAÇÃO DE SUB-ABAS JUDICIAIS --\x3e\n        <div class="judicial-subnav">\n          <button type="button" class="judicial-tab-btn ${currentSub === "investigation" ? "active" : ""}" id="judicial-tab-btn-investigation" onclick="App.switchJudicialTab('investigation')">\n            <i data-lucide="users" style="width:16px; height:16px;"></i> Investigação & Sessões de Usuários\n          </button>\n          <button type="button" class="judicial-tab-btn ${currentSub === "orders" ? "active" : ""}" id="judicial-tab-btn-orders" onclick="App.switchJudicialTab('orders')">\n            <i data-lucide="file-text" style="width:16px; height:16px;"></i> Mandados & Trilha SHA-256\n          </button>\n          <button type="button" class="judicial-tab-btn ${currentSub === "reports" ? "active" : ""}" id="judicial-tab-btn-reports" onclick="App.switchJudicialTab('reports')">\n            <i data-lucide="shield-alert" style="width:16px; height:16px;"></i> Denúncias & Sentinel\n          </button>\n        </div>\n\n        \x3c!-- ABA 1: INVESTIGAÇÃO & SESSÕES DE USUÁRIOS --\x3e\n        <div id="judicial-subtab-content-investigation" class="judicial-subtab-content" style="display: ${currentSub === "investigation" ? "block" : "none"};">\n          <div class="settings-card" style="margin-bottom:16px;">\n            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:12px;">\n              <h3 style="font-size:16px; font-weight:700;">🔍 Rastreamento Forense de Usuários</h3>\n              <span id="judicial-users-total-count" style="font-size:12px; color:var(--text-dim);">Carregando usuários...</span>\n            </div>\n            <div style="display:flex; gap:10px; margin-bottom:14px;">\n              <input type="text" id="judicial-user-search-input" class="form-input" placeholder="Buscar por Nome, @usuário, ID de 12 dígitos, E-mail ou IP..." onkeyup="if(event.key==='Enter') App.handleSearchJudicialUsers()" />\n              <button class="btn-primary" onclick="App.handleSearchJudicialUsers()" style="background:var(--danger); white-space:nowrap;">\n                <i data-lucide="search" style="width:15px; height:15px;"></i> Filtrar\n              </button>\n              <button class="btn-secondary" onclick="document.getElementById('judicial-user-search-input').value=''; App.handleSearchJudicialUsers();" title="Limpar filtro">\n                <i data-lucide="rotate-ccw" style="width:15px; height:15px;"></i>\n              </button>\n            </div>\n            <div id="judicial-users-table-container">\n              <div style="text-align:center; padding:24px; color:var(--text-muted);">Carregando base de usuários...</div>\n            </div>\n          </div>\n        </div>\n\n        \x3c!-- ABA 2: MANDADOS & ORDENS JUDICIAIS --\x3e\n        <div id="judicial-subtab-content-orders" class="judicial-subtab-content" style="display: ${currentSub === "orders" ? "block" : "none"};">\n          <div class="settings-card">\n            <h3 style="font-size:16px; font-weight:700;">📑 Registrar Ordem ou Mandado Judicial</h3>\n            <form onsubmit="App.handleRegisterJudicialOrder(event)" style="display:grid; grid-template-columns: 1fr 1fr; gap:14px; margin-top:8px;">\n              <div class="form-group">\n                <label class="form-label">${t("court_number_label")}</label>\n                <input type="text" id="order-court-number" class="form-input" placeholder="Ex: Processo nº 1002345-2026.8.26.0100" required />\n              </div>\n              <div class="form-group">\n                <label class="form-label">${t("issuing_court_label")}</label>\n                <input type="text" id="order-issuing-court" class="form-input" placeholder="Ex: 2ª Vara de Crimes Cibernéticos" required />\n              </div>\n              <div class="form-group">\n                <label class="form-label">${t("officer_badge_label")}</label>\n                <input type="text" id="order-officer-badge" class="form-input" placeholder="Ex: Delegado / Matrícula 9821-SP" required />\n              </div>\n              <div class="form-group">\n                <label class="form-label">${t("target_id_label")}</label>\n                <input type="text" id="order-target-id" class="form-input" placeholder="ID de 12 Dígitos ou @username" required />\n              </div>\n              <div class="form-group" style="grid-column: span 2;">\n                <label class="form-label">${t("action_type_label")}</label>\n                <select id="order-action-type" class="form-input">\n                  <option value="account_suspension">${t("action_suspend")}</option>\n                  <option value="metadata_export">${t("action_metadata")}</option>\n                  <option value="preservation">${t("action_preserve")}</option>\n                  <option value="dossier_export">Exportação de Dossiê Forense Integral</option>\n                </select>\n              </div>\n              <div style="grid-column: span 2;">\n                <button type="submit" class="btn-primary" style="background:var(--danger);">\n                  Executar e Registrar Trilha Criptográfica SHA-256\n                </button>\n              </div>\n            </form>\n          </div>\n\n          <div class="settings-card">\n            <h3 style="font-size:16px; font-weight:700;">🔒 Trilha de Auditoria Criptográfica Imutável (SHA-256)</h3>\n            <div id="compliance-audit-logs-container">\n              <div style="color:var(--text-dim); font-size:13px;">Carregando registros imutáveis...</div>\n            </div>\n          </div>\n        </div>\n\n        \x3c!-- ABA 3: DENÚNCIAS ATIVAS & SENTINEL --\x3e\n        <div id="judicial-subtab-content-reports" class="judicial-subtab-content" style="display: ${currentSub === "reports" ? "block" : "none"};">\n          <div class="settings-card">\n            <h3 style="font-size:16px; font-weight:700;">🚨 Denúncias Recebidas & Franking Criptográfico</h3>\n            <div id="compliance-reports-container">\n              <div style="color:var(--text-dim); font-size:13px;">Carregando denúncias...</div>\n            </div>\n          </div>\n        </div>\n\n      </div>\n    `;
  },
  async handleSearchJudicialUsers() {
    const input = document.getElementById("judicial-user-search-input");
    const query = input ? input.value.trim() : "";
    await this.loadJudicialUsers(query);
  },
  async loadJudicialUsers(query = "") {
    if (!this.currentUser || !this.currentUser.is_admin) return;
    const container = document.getElementById("judicial-users-table-container");
    const totalEl = document.getElementById("judicial-users-total-count");
    if (!container) return;
    try {
      const users = await FechatAPI.getJudicialUsersList(query);
      if (totalEl)
        totalEl.textContent = `${users.length} usuário(s) localizado(s)`;
      if (users.length === 0) {
        container.innerHTML =
          '<div style="text-align:center; padding:24px; color:var(--text-muted); font-size:13px;">Nenhum usuário encontrado para esta pesquisa.</div>';
        return;
      }
      let html = `\n        <div class="forensic-table-container">\n          <table class="forensic-table">\n            <thead>\n              <tr>\n                <th>Usuário</th>\n                <th>Identificador</th>\n                <th>IP de Conexão</th>\n                <th>Dispositivo & Navegador</th>\n                <th>Status</th>\n                <th style="text-align:right;">Ações Forenses</th>\n              </tr>\n            </thead>\n            <tbody>\n      `;
      users.forEach((u) => {
        const isOnline = u.is_online
          ? '<span style="color:#10b981;">● Online</span>'
          : '<span style="color:var(--text-muted);">○ Offline</span>';
        const isSuspended = u.is_suspended;
        const statusBadge = isSuspended
          ? '<span style="background:rgba(239, 68, 68, 0.2); color:#fca5a5; padding:2px 6px; border-radius:4px; font-size:11px; font-weight:700;">⛔ SUSPENSO</span>'
          : u.is_verified
            ? '<span style="background:rgba(56, 189, 248, 0.2); color:#38bdf8; padding:2px 6px; border-radius:4px; font-size:11px; font-weight:700;">✅ VERIFICADO</span>'
            : '<span style="color:#10b981; font-size:11px;">ATIVO</span>';
        html += `\n          <tr>\n            <td>\n              <div style="display:flex; align-items:center; gap:8px;">\n                <img src="${u.avatar_url || `https://api.dicebear.com/7.x/identicon/svg?seed=${u.username}`}" style="width:28px; height:28px; border-radius:50%; object-fit:cover;" />\n                <div>\n                  <div style="font-weight:700; font-size:13px; display:flex; align-items:center; gap:4px;">\n                    ${this.escapeHTML(u.full_name)}\n                    ${u.is_verified ? '<i data-lucide="badge-check" style="width:13px; height:13px; color:var(--primary);"></i>' : ""}\n                    ${u.is_admin ? '<i data-lucide="shield" style="width:13px; height:13px; color:var(--danger);" title="Admin"></i>' : ""}\n                  </div>\n                  <div style="font-size:11px; color:var(--text-dim);">@${this.escapeHTML(u.username)}</div>\n                </div>\n              </div>\n            </td>\n            <td>\n              <span class="id-badge">${u.numeric_id}</span>\n            </td>\n            <td>\n              <span class="forensic-ip-badge">${u.last_ip || "127.0.0.1"}</span>\n            </td>\n            <td>\n              <span class="forensic-device-badge" title="${this.escapeHTML(u.user_agent || "")}">${this.escapeHTML(u.device_info || "Desktop")}</span>\n            </td>\n            <td>\n              ${statusBadge}\n              <div style="font-size:10.5px; margin-top:2px;">${isOnline}</div>\n            </td>\n            <td style="text-align:right;">\n              <div style="display:flex; justify-content:flex-end; gap:6px; flex-wrap:nowrap;">\n                <button type="button" class="btn-secondary" style="padding:4px 8px; font-size:11px;" onclick="App.openJudicialDossierModal(${u.id})" title="Ver Dossiê e Conversas">\n                  <i data-lucide="folder-search" style="width:13px; height:13px;"></i> Dossiê\n                </button>\n                <button type="button" class="btn-secondary" style="padding:4px 8px; font-size:11px;" onclick="App.openJudicialNoticeModal(${u.id}, '${this.escapeHTML(u.full_name)}')" title="Enviar Notificação Oficial">\n                  <i data-lucide="bell" style="width:13px; height:13px;"></i> Intimar\n                </button>\n                <button type="button" class="btn-secondary" style="padding:4px 8px; font-size:11px;" onclick="App.openJudicialExportModal(${u.id}, '${this.escapeHTML(u.full_name)}')" title="Exportar Relatório SHA-256">\n                  <i data-lucide="download" style="width:13px; height:13px;"></i> Exportar\n                </button>\n                ${isSuspended ? `<button type="button" class="btn-primary" style="background:#10b981; padding:4px 8px; font-size:11px;" onclick="App.handleUnsuspendUser(${u.id})" title="Reativar Conta">Reativar</button>` : `<button type="button" class="btn-danger" style="padding:4px 8px; font-size:11px;" onclick="App.handleSuspendUser(${u.id})" title="Suspender Acesso">Suspender</button>`}\n              </div>\n            </td>\n          </tr>\n        `;
      });
      html += "</tbody></table></div>";
      container.innerHTML = html;
      this.refreshIcons();
    } catch (err) {
      container.innerHTML = `<div style="color:var(--danger); padding:16px; font-size:13px;">Erro ao listar usuários: ${err.message}</div>`;
    }
  },
  async loadComplianceData() {
    if (!this.currentUser || !this.currentUser.is_admin) return;
    const sub = this.judicialActiveSubTab || "investigation";
    if (sub === "investigation") {
      const input = document.getElementById("judicial-user-search-input");
      const query = input ? input.value.trim() : "";
      await this.loadJudicialUsers(query);
      return;
    }
    try {
      const orders = await FechatAPI.getJudicialAuditLogs();
      const reports = await FechatAPI.getAbuseReports();
      const auditContainer = document.getElementById(
        "compliance-audit-logs-container",
      );
      const reportsContainer = document.getElementById(
        "compliance-reports-container",
      );
      if (auditContainer) {
        if (orders.length === 0) {
          auditContainer.innerHTML =
            '<p style="color:var(--text-muted); font-size:13px;">Nenhuma ordem judicial registrada até o momento.</p>';
        } else {
          let html = `\n            <table class="audit-table">\n              <thead>\n                <tr>\n                  <th>Processo / Mandado</th>\n                  <th>Juízo</th>\n                  <th>Alvo</th>\n                  <th>Ação</th>\n                  <th>Data/Hora</th>\n                  <th>SHA-256 Hash</th>\n                </tr>\n              </thead>\n              <tbody>\n          `;
          orders.forEach((o) => {
            html += `\n              <tr>\n                <td><strong>${o.court_order_number}</strong></td>\n                <td>${o.issuing_court}</td>\n                <td><span class="id-badge">${o.target_identifier}</span></td>\n                <td>${o.action_type}</td>\n                <td style="font-size:11px; color:var(--text-muted);">${o.created_at ? new Date(o.created_at).toLocaleString() : "-"}</td>\n                <td><span class="forensic-hash-pill">${(o.audit_hash || "").slice(0, 18)}...</span></td>\n              </tr>\n            `;
          });
          html += "</tbody></table>";
          auditContainer.innerHTML = html;
        }
      }
      if (reportsContainer) {
        if (reports.length === 0) {
          reportsContainer.innerHTML =
            '<p style="color:var(--text-muted); font-size:13px;">Nenhuma denúncia pendente de moderação.</p>';
        } else {
          let html =
            '<div style="display:flex; flex-direction:column; gap:10px; margin-top:8px;">';
          reports.forEach((r) => {
            html += `\n              <div style="background:rgba(0,0,0,0.25); border:1px solid var(--border-glass); padding:12px; border-radius:var(--radius-md);">\n                <div style="display:flex; justify-content:space-between; align-items:center;">\n                  <span style="font-weight:700; color:var(--danger);">${(r.category || "OTHER").toUpperCase()}</span>\n                  <span class="id-badge">Franking: ${r.franking_verified ? "✅ Verificado" : "Sem tag"}</span>\n                </div>\n                <p style="font-size:13px; margin:6px 0;"><strong>Motivo:</strong> ${r.reason}</p>\n                ${r.plaintext_evidence ? `<div style="background:rgba(239, 68, 68, 0.1); border-left:3px solid var(--danger); padding:8px; font-size:12px; margin:6px 0;">Evidência: "${r.plaintext_evidence}"</div>` : ""}\n                <div style="display:flex; gap:10px; margin-top:8px;">\n                  ${r.reported_user_id ? `<button class="btn-danger" onclick="App.handleSuspendUser(${r.reported_user_id})" style="font-size:11px; padding:6px 12px;">${t("suspend_btn")}</button>` : ""}\n                </div>\n              </div>\n            `;
          });
          html += "</div>";
          reportsContainer.innerHTML = html;
        }
      }
    } catch (e) {
      console.warn("Erro compliance:", e);
    }
  },
  async openJudicialDossierModal(userId) {
    const modal = document.getElementById("modal-container");
    modal.innerHTML = `\n      <div class="modal-overlay active">\n        <div class="modal-content" style="max-width:720px;">\n          <div class="modal-header">\n            <h3>📑 Dossiê Forense do Usuário</h3>\n            <button class="btn-close" onclick="App.closeModal()"><i data-lucide="x"></i></button>\n          </div>\n          <div id="dossier-modal-body" style="padding:16px 0; text-align:center; color:var(--text-muted);">\n            Carregando dados consolidados de sessões, conversas e auditoria...\n          </div>\n        </div>\n      </div>\n    `;
    this.refreshIcons();
    try {
      const data = await FechatAPI.getJudicialUserDossier(userId);
      const u = data.user;
      const chats = data.chats || [];
      const reports = data.reports || [];
      const bodyEl = document.getElementById("dossier-modal-body");
      if (!bodyEl) return;
      let html = `\n        <div style="display:flex; gap:16px; align-items:center; background:rgba(0,0,0,0.3); padding:14px; border-radius:var(--radius-md); margin-bottom:16px; text-align:left;">\n          <img src="${u.avatar_url || `https://api.dicebear.com/7.x/identicon/svg?seed=${u.username}`}" style="width:52px; height:52px; border-radius:50%; object-fit:cover;" />\n          <div style="flex:1;">\n            <h4 style="font-size:16px; font-weight:700; margin-bottom:2px;">${this.escapeHTML(u.full_name)} (@${this.escapeHTML(u.username)})</h4>\n            <div style="display:flex; flex-wrap:wrap; gap:8px; font-size:12px; margin-top:4px;">\n              <span class="id-badge">${u.numeric_id}</span>\n              <span class="forensic-ip-badge">IP: ${u.last_ip || "127.0.0.1"}</span>\n              <span class="forensic-device-badge">${this.escapeHTML(u.device_info || "Desktop")}</span>\n            </div>\n          </div>\n        </div>\n\n        <div style="text-align:left; margin-bottom:16px;">\n          <h4 style="font-size:14px; font-weight:700; color:var(--primary); margin-bottom:8px;">💬 Conversas e Canais Registrados (${chats.length})</h4>\n          ${chats.length === 0 ? '<p style="font-size:12px; color:var(--text-muted);">Nenhum chat registrado.</p>' : `\n            <div style="max-height:220px; overflow-y:auto; display:flex; flex-direction:column; gap:6px;">\n              ${chats.map((c) => `\n                <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-glass); padding:8px 12px; border-radius:6px; display:flex; justify-content:space-between; align-items:center;">\n                  <div>\n                    <div style="font-weight:700; font-size:13px;">${this.escapeHTML(c.title || "Chat")} ${c.is_group ? '<span class="id-badge" style="font-size:10px;">GRUPO</span>' : ""}</div>\n                    <div style="font-size:11px; color:var(--text-dim);">${c.member_count} participante(s) • Função: ${c.role}</div>\n                  </div>\n                  <button type="button" class="btn-primary" style="background:var(--danger); font-size:11px; padding:4px 10px;" onclick="App.openJudicialChatInspectionModal(${c.chat_id}, '${this.escapeHTML(c.title)}')">\n                    <i data-lucide="eye" style="width:12px; height:12px;"></i> Descriptografar e Inspecionar\n                  </button>\n                </div>\n              `).join("")}\n            </div>\n          `}\n        </div>\n\n        <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:16px; border-top:1px solid var(--border-glass); padding-top:12px;">\n          <button class="btn-secondary" onclick="App.closeModal()">Fechar</button>\n          <button class="btn-primary" style="background:var(--danger);" onclick="App.openJudicialExportModal(${u.id}, '${this.escapeHTML(u.full_name)}')">\n            <i data-lucide="download" style="width:14px; height:14px;"></i> Exportar Dossiê SHA-256\n          </button>\n        </div>\n      `;
      bodyEl.innerHTML = html;
      this.refreshIcons();
    } catch (err) {
      const bodyEl = document.getElementById("dossier-modal-body");
      if (bodyEl)
        bodyEl.innerHTML = `<div style="color:var(--danger); font-size:13px;">Erro ao carregar dossiê: ${err.message}</div>`;
    }
  },
  async openJudicialChatInspectionModal(chatId, chatTitle) {
    const modal = document.getElementById("modal-container");
    modal.innerHTML = `\n      <div class="modal-overlay active">\n        <div class="modal-content" style="max-width:780px;">\n          <div class="modal-header">\n            <h3>🔓 Inspeção Forense: ${this.escapeHTML(chatTitle || "Conversa")}</h3>\n            <button class="btn-close" onclick="App.closeModal()"><i data-lucide="x"></i></button>\n          </div>\n          <div style="background:rgba(239, 68, 68, 0.1); border-left:3px solid var(--danger); padding:8px 12px; font-size:12px; color:#fca5a5; margin-bottom:12px;">\n            ⚠️ Descriptografia autorizada pelo Oficial de Segurança & Compliance para fins de instrução e preservação judicial.\n          </div>\n          <div id="judicial-chat-terminal-body" class="forensic-terminal-box">\n            Carregando e descriptografando mensagens com a chave AES-256 do canal...\n          </div>\n          <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:14px;">\n            <button class="btn-secondary" onclick="App.closeModal()">Fechar</button>\n          </div>\n        </div>\n      </div>\n    `;
    this.refreshIcons();
    try {
      const data = await FechatAPI.getJudicialChatMessages(chatId, 200);
      const msgs = data.messages || [];
      const container = document.getElementById("judicial-chat-terminal-body");
      if (!container) return;
      if (msgs.length === 0) {
        container.innerHTML =
          '<div style="color:var(--text-muted); text-align:center; padding:20px;">Nenhuma mensagem registrada nesta conversa.</div>';
        return;
      }
      let html = "";
      msgs.forEach((m) => {
        const senderName = m.sender ? m.sender.full_name : "Usuário";
        const senderId = m.sender ? m.sender.numeric_id : m.sender_id;
        const timeStr = m.created_at
          ? new Date(m.created_at).toLocaleString()
          : "";
        const isMedia = m.media_url
          ? `<div style="margin-top:4px; font-size:11.5px; color:#38bdf8;">📎 Mídia/Anexo: <a href="${m.media_url}" target="_blank" style="color:#38bdf8; text-decoration:underline;">${this.escapeHTML(m.media_name || "Abrir Arquivo")}</a></div>`
          : "";
        html += `\n          <div class="forensic-msg-item">\n            <div class="forensic-msg-header">\n              <span><strong>${this.escapeHTML(senderName)}</strong> (${senderId})</span>\n              <span>${timeStr}</span>\n            </div>\n            <div class="forensic-msg-plaintext">${this.escapeHTML(m.plaintext)}</div>\n            ${isMedia}\n          </div>\n        `;
      });
      container.innerHTML = html;
      this.refreshIcons();
    } catch (err) {
      const container = document.getElementById("judicial-chat-terminal-body");
      if (container)
        container.innerHTML = `<div style="color:var(--danger);">Erro na descriptografia judicial: ${err.message}</div>`;
    }
  },
  openJudicialNoticeModal(userId, userFullName) {
    const modal = document.getElementById("modal-container");
    modal.innerHTML = `\n      <div class="modal-overlay active">\n        <div class="modal-content" style="max-width:540px;">\n          <div class="modal-header">\n            <h3>⚖️ Expedir Notificação / Intimação Oficial</h3>\n            <button class="btn-close" onclick="App.closeModal()"><i data-lucide="x"></i></button>\n          </div>\n          <p style="color:var(--text-muted); font-size:13px; margin-bottom:12px;">\n            A notificação será enviada pelo <strong>Bot de Conformidade Legal</strong> diretamente para <strong>${this.escapeHTML(userFullName)}</strong> com carimbo de validade.\n          </p>\n          <form onsubmit="App.handleSendJudicialNoticeSubmit(event, ${userId})" style="display:flex; flex-direction:column; gap:12px;">\n            <div class="form-group">\n              <label class="form-label">Título da Notificação</label>\n              <input type="text" id="notice-title-input" class="form-input" placeholder="Ex: AVISO DE VIOLAÇÃO DE TERMOS / ORDEM JUDICIAL" required value="NOTIFICAÇÃO OFICIAL DE CONFORMIDADE" />\n            </div>\n            <div class="form-group">\n              <label class="form-label">Conteúdo da Notificação / Intimação</label>\n              <textarea id="notice-body-input" class="form-input" style="min-height:110px; resize:vertical;" placeholder="Descreva os termos da intimação, advertência ou ordem legal..." required></textarea>\n            </div>\n            <button type="submit" class="btn-primary" style="background:var(--danger); padding:10px;">\n              <i data-lucide="send" style="width:14px; height:14px;"></i> Transmitir Notificação com Fé Pública\n            </button>\n          </form>\n        </div>\n      </div>\n    `;
    this.refreshIcons();
  },
  async handleSendJudicialNoticeSubmit(e, userId) {
    e.preventDefault();
    const title = document.getElementById("notice-title-input").value.trim();
    const body = document.getElementById("notice-body-input").value.trim();
    try {
      await FechatAPI.sendJudicialNotice(userId, title, body);
      this.showToast(
        "Notificação judicial transmitida com sucesso!",
        "success",
      );
      this.closeModal();
    } catch (err) {
      this.showToast("Erro ao enviar notificação: " + err.message, "danger");
    }
  },
  openJudicialExportModal(userId, userFullName) {
    const modal = document.getElementById("modal-container");
    modal.innerHTML = `\n      <div class="modal-overlay active">\n        <div class="modal-content" style="max-width:560px;">\n          <div class="modal-header">\n            <h3>📑 Exportar Dossiê Forense Integral (SHA-256)</h3>\n            <button class="btn-close" onclick="App.closeModal()"><i data-lucide="x"></i></button>\n          </div>\n          <p style="color:var(--text-muted); font-size:13px; margin-bottom:12px;">\n            Gera um pacote auditável com todas as mensagens, mídias e metadados de <strong>${this.escapeHTML(userFullName)}</strong> com assinatura criptográfica SHA-256.\n          </p>\n          <form onsubmit="App.handleExportJudicialDossierSubmit(event, ${userId})" style="display:flex; flex-direction:column; gap:12px;">\n            <div class="form-group">\n              <label class="form-label">Número do Mandado / Processo</label>\n              <input type="text" id="export-order-number" class="form-input" placeholder="Ex: Autos nº 0019283-2026.8.26.0100" required value="AUTOS-${Date.now()}" />\n            </div>\n            <div class="form-group">\n              <label class="form-label">Juízo / Delegacia Solicitante</label>\n              <input type="text" id="export-issuing-court" class="form-input" placeholder="Ex: Vara de Inquéritos Policiais" required value="Auditoria Forense de Compliance" />\n            </div>\n            <div class="form-group">\n              <label class="form-label">Autoridade / Matrícula</label>\n              <input type="text" id="export-officer-badge" class="form-input" placeholder="Ex: Perito Criminal Matrícula 7721" required value="${this.currentUser.username}" />\n            </div>\n            <div class="form-group">\n              <label class="form-label">Motivação</label>\n              <input type="text" id="export-reason" class="form-input" placeholder="Ex: Instrução criminal / Quebra judicial" required value="Instrução e Preservação Forense" />\n            </div>\n            <div style="display:flex; gap:10px; margin-top:8px;">\n              <button type="submit" class="btn-primary" style="background:var(--danger); padding:10px; flex:1;">\n                <i data-lucide="file-check" style="width:14px; height:14px;"></i> Gerar e Visualizar Laudo Oficial (PDF)\n              </button>\n            </div>\n          </form>\n        </div>\n      </div>\n    `;
    this.refreshIcons();
  },
  async handleExportJudicialDossierSubmit(e, userId) {
    e.preventDefault();
    const orderNum = document
      .getElementById("export-order-number")
      .value.trim();
    const court = document.getElementById("export-issuing-court").value.trim();
    const badge = document.getElementById("export-officer-badge").value.trim();
    const reason = document.getElementById("export-reason").value.trim();
    try {
      this.showToast(
        "Compilando dados forenses, histórico de chats e calculando hash SHA-256...",
        "info",
      );
      const res = await FechatAPI.exportJudicialDossier(
        userId,
        orderNum,
        court,
        badge,
        reason,
      );
      const dossier = res.dossier;
      const sha256 = res.sha256_hash;
      this.closeModal();
      this.openJudicialPrintableReport(dossier, sha256);
      this.loadComplianceData();
    } catch (err) {
      this.showToast("Erro ao gerar laudo forense: " + err.message, "danger");
    }
  },
  openJudicialPrintableReport(dossier, sha256) {
    const modal = document.getElementById("modal-container");
    const header = dossier.document_header || {};
    const subj = dossier.investigated_subject || {};
    const reports = dossier.abuse_reports_and_sentinel || [];
    const dialogs = dossier.dialog_transcripts || [];
    const summary = dossier.forensic_summary || {};
    const seal = dossier.cryptographic_seal || {};
    const protocolId =
      header.forensic_protocol || summary.protocol_id || `LAUDO-${Date.now()}`;
    const digitalSig =
      seal.digital_signature_stamp ||
      `FECHAT-COMPLIANCE-SIGN-${sha256.slice(0, 24).toUpperCase()}`;
    const groupsList = dialogs.filter((d) => d.is_group);
    let groupsHtml = "";
    if (groupsList.length === 0) {
      groupsHtml =
        '<p style="font-size:12px; color:#64748b; font-style:italic;">Nenhum grupo ou comunidade registrado para este usuário.</p>';
    } else {
      groupsHtml = `\n        <table class="forensic-table" style="background:#fff; color:#0f172a; margin-top:6px;">\n          <thead>\n            <tr style="background:#f1f5f9;">\n              <th style="color:#475569;">ID do Chat</th>\n              <th style="color:#475569;">Nome do Grupo</th>\n              <th style="color:#475569;">Função do Investigado</th>\n              <th style="color:#475569;">Total de Membros</th>\n              <th style="color:#475569;">Status do Grupo</th>\n            </tr>\n          </thead>\n          <tbody>\n            ${groupsList.map((g) => `\n              <tr>\n                <td><span class="id-badge" style="background:#e2e8f0; color:#334155;">#${g.chat_id}</span></td>\n                <td><strong>${this.escapeHTML(g.chat_title)}</strong></td>\n                <td><span style="font-weight:700; color:${g.target_role === "admin" ? "#b91c1c" : "#334155"};">${(g.target_role || "membro").toUpperCase()}</span></td>\n                <td>${(g.participants || []).length} integrantes</td>\n                <td>${g.is_suspended ? '<span style="color:#b91c1c; font-weight:700;">⛔ SUSPENSO</span>' : '<span style="color:#15803d; font-weight:700;">🟢 ATIVO</span>'}</td>\n              </tr>\n            `).join("")}\n          </tbody>\n        </table>\n      `;
    }
    let dialogsHtml = "";
    if (dialogs.length === 0) {
      dialogsHtml =
        '<p style="font-size:12px; color:#64748b; font-style:italic;">Nenhum histórico de mensagens registrado para este investigado.</p>';
    } else {
      dialogs.forEach((d) => {
        let msgsHtml = "";
        if (d.messages.length === 0) {
          msgsHtml =
            '<div style="font-size:11.5px; color:#94a3b8; padding:8px;">Nenhuma mensagem registrada nesta conversa.</div>';
        } else {
          d.messages.forEach((m) => {
            const isTarget = m.is_subject_sender;
            const rowClass = isTarget ? "investigated" : "interlocutor";
            const speakerBadge = isTarget
              ? `🚨 [INVESTIGADO: ${this.escapeHTML(m.sender_name)} • ID: ${m.sender_numeric_id}]`
              : `💬 [INTERLOCUTOR: ${this.escapeHTML(m.sender_name)} • ID: ${m.sender_numeric_id}]`;
            const dateStr = m.timestamp_utc
              ? new Date(m.timestamp_utc).toLocaleString("pt-BR")
              : "-";
            const replySnippet = m.reply_to_message_id
              ? `<div style="font-size:10.5px; color:#64748b; margin-bottom:4px; font-style:italic; border-left:2px solid #94a3b8; padding-left:4px;">↳ Em resposta à mensagem #${m.reply_to_message_id} (${this.escapeHTML(m.reply_to_sender_name || "Usuário")}): "${this.escapeHTML(m.reply_to_snippet || "")}"</div>`
              : "";
            const mediaStr = m.media_url
              ? `<div style="margin-top:5px; font-size:11px; font-weight:600; color:#0284c7; background:#f0f9ff; padding:4px 8px; border-radius:4px; border:1px solid #bae6fd;">📎 ANEXO/MÍDIA PERICIAL: ${this.escapeHTML(m.media_name || "Arquivo")} • URL: ${m.media_url}</div>`
              : "";
            msgsHtml += `\n              <div class="forensic-msg-row ${rowClass}">\n                <div class="forensic-msg-meta">\n                  <span class="forensic-msg-speaker">${speakerBadge}</span>\n                  <span><strong>MSG #${m.message_id}</strong> • ${dateStr} (BRT/UTC)</span>\n                </div>\n                ${replySnippet}\n                <div class="forensic-msg-body">${this.escapeHTML(m.plaintext_content)}</div>\n                ${mediaStr}\n              </div>\n            `;
          });
        }
        const participantsStr = (d.participants || [])
          .map(
            (p) =>
              `${p.full_name} (@${p.username} - ID: ${p.numeric_id}) [${p.role}]`,
          )
          .join(", ");
        dialogsHtml += `\n          <div class="forensic-dialog-box">\n            <div class="forensic-dialog-header">\n              <span><strong>${this.escapeHTML(d.chat_title)}</strong> ${d.is_group ? "(GRUPO / COMUNIDADE)" : "(CONVERSA PRIVADA 1:1)"}</span>\n              <span style="font-size:11px; color:#475569;">Cód. Conversa: #${d.chat_id} • Total Mensagens: ${d.chat_messages_total}</span>\n            </div>\n            <div style="font-size:11px; color:#475569; padding:6px 12px; background:#f8fafc; border-bottom:1px solid #e2e8f0;">\n              <strong>Participantes Mapeados:</strong> ${this.escapeHTML(participantsStr || "Não identificados")}\n            </div>\n            <div class="forensic-dialog-messages">\n              ${msgsHtml}\n            </div>\n          </div>\n        `;
      });
    }
    let reportsHtml = "";
    if (reports.length === 0) {
      reportsHtml =
        '<p style="font-size:12px; color:#64748b; font-style:italic;">Nenhuma infração ou denúncia formal registrada contra este usuário no período apurado.</p>';
    } else {
      reports.forEach((r) => {
        reportsHtml += `\n          <div style="background:#fef2f2; border:1px solid #fca5a5; padding:8px 12px; border-radius:6px; margin-bottom:8px; font-size:12px;">\n            <div style="display:flex; justify-content:space-between; font-weight:700; color:#991b1b;">\n              <span>DENÚNCIA #${r.report_id} • CATEGORIA: ${r.category}</span>\n              <span>Franking Criptográfico: ${r.franking_verified ? "AUTÊNTICO (HMAC VERIFICADO) ✅" : "SEM TAG"}</span>\n            </div>\n            <p style="margin:4px 0; color:#334155;"><strong>Motivação / Relato:</strong> ${this.escapeHTML(r.reason)}</p>\n            ${r.plaintext_evidence ? `<div style="background:#fff; padding:6px; border-radius:4px; font-family:monospace; font-size:11px; color:#b91c1c; border-left:3px solid #ef4444;">Evidência Anexada na Denúncia: "${this.escapeHTML(r.plaintext_evidence)}"</div>` : ""}\n            <div style="font-size:10.5px; color:#64748b; margin-top:4px;">Denunciante: ${r.reporter_numeric_id} • Data: ${r.created_at ? new Date(r.created_at).toLocaleString("pt-BR") : "-"}</div>\n          </div>\n        `;
      });
    }
    modal.innerHTML = `\n      <div class="modal-overlay active" style="padding:10px;">\n        <div class="modal-content" style="max-width:960px; max-height:94vh; padding:16px; background:#1e293b;">\n          <div class="modal-header no-print" style="margin-bottom:12px; display:flex; justify-content:space-between; align-items:center;">\n            <div style="display:flex; align-items:center; gap:8px;">\n              <span class="id-badge" style="background:#b91c1c; color:#fff; font-weight:700;">PROCESSO OFICIAL</span>\n              <h3 style="color:#f8fafc; font-size:16px;">📑 Laudo Pericial Forense Digital (Visualização A4 / PDF)</h3>\n            </div>\n            <div style="display:flex; gap:8px;">\n              <button class="btn-primary" style="background:#b91c1c; font-size:12px; padding:6px 14px;" onclick="window.print()">\n                <i data-lucide="printer" style="width:14px; height:14px;"></i> Imprimir / Salvar como PDF Oficial\n              </button>\n              <button class="btn-secondary" style="font-size:12px; padding:6px 12px;" onclick="App.downloadDossierJson('${subj.numeric_id}', '${header.court_order_number}', ${JSON.stringify(JSON.stringify(dossier))})">\n                <i data-lucide="download" style="width:14px; height:14px;"></i> Baixar JSON\n              </button>\n              <button class="btn-close" onclick="App.closeModal()"><i data-lucide="x"></i></button>\n            </div>\n          </div>\n\n          <div id="printable-forensic-report" class="forensic-report-paper" style="max-height:80vh; overflow-y:auto;">\n            \x3c!-- MARCAS D'ÁGUA EM DIAGONAL NO FUNDO --\x3e\n            <div class="forensic-watermark-overlay">\n              <div class="forensic-watermark-line">LAUDO PERICIAL OFICIAL • CADEIA DE CUSTÓDIA</div>\n              <div class="forensic-watermark-line">DOCUMENTO JUDICIAL CONFIDENCIAL • FECHAT COMPLIANCE</div>\n              <div class="forensic-watermark-line">PROVA PERICIAL AUTENTICADA • SHA-256 VERIFIED</div>\n              <div class="forensic-watermark-line">USO EXCLUSIVO DAS AUTORIDADES COMPETENTES</div>\n              <div class="forensic-watermark-line">FECHAT SECURITY • ICP DIGITAL • NÃO COPIAR</div>\n              <div class="forensic-watermark-line">LAUDO PERICIAL OFICIAL • CADEIA DE CUSTÓDIA</div>\n            </div>\n\n            <div class="forensic-report-content">\n              \x3c!-- CABEÇALHO OFICIAL COM BRASÕES --\x3e\n              <div class="forensic-header">\n                <div class="forensic-seal-box">\n                  <div class="forensic-seal-icon">⚖️</div>\n                  <div class="forensic-header-titles">\n                    <h2>FECHAT FORENSIC INTELLIGENCE & COMPLIANCE</h2>\n                    <h3>Laudo Técnico Pericial de Preservação & Descriptografia Digital</h3>\n                    <div style="font-size:11px; color:#64748b; margin-top:2px;">Cadeia de Custódia Digital nos termos dos arts. 158-A a 158-F do CPP e Marco Civil da Internet</div>\n                  </div>\n                </div>\n                <div class="forensic-order-badge">\n                  <strong>PROTOCOLO FORENSE:</strong> <span style="font-family:monospace; color:#b91c1c;">${protocolId}</span>\n                  <div><strong>PROCESSO / MANDADO:</strong> ${this.escapeHTML(header.court_order_number || "NÃO ESPECIFICADO")}</div>\n                  <div><strong>JUÍZO / REQUISITANTE:</strong> ${this.escapeHTML(header.issuing_court || "Auditoria Geral")}</div>\n                  <div><strong>OFICIAL EXPEDIDOR:</strong> ${this.escapeHTML(header.officer_badge || "admin")}</div>\n                  <div><strong>EMISSÃO:</strong> ${header.emission_timestamp_brt || new Date().toLocaleString("pt-BR")}</div>\n                </div>\n              </div>\n\n              \x3c!-- SEÇÃO 1: QUALIFICAÇÃO CADASTRAL DO INVESTIGADO & SESSÕES --\x3e\n              <div class="forensic-section">\n                <div class="forensic-section-title">\n                  <span>SEÇÃO I - QUALIFICAÇÃO CADASTRAL & METADADOS FORENSES DE REDE</span>\n                </div>\n                <div class="forensic-grid">\n                  <div class="forensic-grid-item">\n                    <span class="forensic-grid-label">Nome Completo do Investigado</span>\n                    <span class="forensic-grid-value">${this.escapeHTML(subj.full_name || "N/D")}</span>\n                  </div>\n                  <div class="forensic-grid-item">\n                    <span class="forensic-grid-label">ID Numérico de 12 Dígitos</span>\n                    <span class="forensic-grid-value" style="font-family:monospace; color:#b91c1c;">${subj.numeric_id || "N/D"}</span>\n                  </div>\n                  <div class="forensic-grid-item">\n                    <span class="forensic-grid-label">Nome de Usuário (@handle)</span>\n                    <span class="forensic-grid-value">@${this.escapeHTML(subj.username || "N/D")} (ID Banco: #${subj.id})</span>\n                  </div>\n                  <div class="forensic-grid-item">\n                    <span class="forensic-grid-label">E-mail Cadastrado</span>\n                    <span class="forensic-grid-value">${this.escapeHTML(subj.email || "N/D")}</span>\n                  </div>\n                  <div class="forensic-grid-item">\n                    <span class="forensic-grid-label">Data de Criação da Conta</span>\n                    <span class="forensic-grid-value">${subj.account_created_at ? new Date(subj.account_created_at).toLocaleString("pt-BR") : "N/D"} (${subj.account_age_days || 0} dias)</span>\n                  </div>\n                  <div class="forensic-grid-item">\n                    <span class="forensic-grid-label">Último Acesso / Conexão</span>\n                    <span class="forensic-grid-value">${subj.last_seen_at ? new Date(subj.last_seen_at).toLocaleString("pt-BR") : "N/D"}</span>\n                  </div>\n                  <div class="forensic-grid-item">\n                    <span class="forensic-grid-label">Endereço IP de Origem (Último Registro)</span>\n                    <span class="forensic-grid-value" style="color:#b91c1c; font-family:monospace; font-weight:700;">${subj.last_known_ip || "127.0.0.1"}</span>\n                  </div>\n                  <div class="forensic-grid-item">\n                    <span class="forensic-grid-label">Dispositivo & Sistema Operacional</span>\n                    <span class="forensic-grid-value">${this.escapeHTML(subj.device_category || "Computador / Desktop")}</span>\n                  </div>\n                  <div class="forensic-grid-item" style="grid-column: span 2;">\n                    <span class="forensic-grid-label">User-Agent String Bruta (Forense)</span>\n                    <span class="forensic-grid-value" style="font-size:10.5px; color:#475569; font-family:monospace;">${this.escapeHTML(subj.user_agent_raw || "Padrão")}</span>\n                  </div>\n                  <div class="forensic-grid-item">\n                    <span class="forensic-grid-label">Fingerprint de Origem de Rede (SHA-256)</span>\n                    <span class="forensic-grid-value" style="font-size:10px; font-family:monospace; color:#0284c7;">${subj.network_origin_fingerprint ? subj.network_origin_fingerprint.slice(0, 32) + "..." : "-"}</span>\n                  </div>\n                  <div class="forensic-grid-item">\n                    <span class="forensic-grid-label">Status da Conta no Fechat</span>\n                    <span class="forensic-grid-value">${subj.is_suspended ? "⛔ CONTA SUSPENSA" : "🟢 CONTA ATIVA"} • ${subj.is_verified ? "VERIFICADO (SELO OFICIAL)" : "NÃO VERIFICADO"}</span>\n                  </div>\n                </div>\n              </div>\n\n              \x3c!-- SEÇÃO 2: GRUPOS E COMUNIDADES --\x3e\n              <div class="forensic-section">\n                <div class="forensic-section-title">\n                  <span>SEÇÃO II - MAPEAMENTO DE GRUPOS E COMUNIDADES VINCULADAS (${groupsList.length})</span>\n                </div>\n                ${groupsHtml}\n              </div>\n\n              \x3c!-- SEÇÃO 3: HISTÓRICO DE DENÚNCIAS E SENTINEL --\x3e\n              <div class="forensic-section">\n                <div class="forensic-section-title">\n                  <span>SEÇÃO III - HISTÓRICO DE DENÚNCIAS & SENTINEL MODERAÇÃO (${reports.length})</span>\n                </div>\n                ${reportsHtml}\n              </div>\n\n              \x3c!-- SEÇÃO 4: TRANSCRIÇÕES CRONOLÓGICAS DE CONVERSAS --\x3e\n              <div class="forensic-section">\n                <div class="forensic-section-title">\n                  <span>SEÇÃO IV - TRANSCRIÇÃO FORENSE INTEGRAL DE DIÁLOGOS DESCRIPTOGRAFADOS (${summary.total_messages_extracted || 0} MENSAGENS)</span>\n                </div>\n                ${dialogsHtml}\n              </div>\n\n              \x3c!-- SEÇÃO 5: TERMO DE ENCERRAMENTO & ASSINATURAS DIGITAIS --\x3e\n              <div class="forensic-section forensic-closing-box">\n                <div class="forensic-section-title" style="border:none; margin-bottom:6px;">\n                  <span>SEÇÃO V - TERMO DE ENCERRAMENTO, FÉ PÚBLICA & ASSINATURAS DIGITAIS</span>\n                </div>\n                <p style="font-size:11.5px; color:#334155; line-height:1.4;">\n                  Atesta-se, sob as penas da lei e em estrito cumprimento às ordens judiciais expedidas, que os dados, mensagens e metadados constantes neste laudo foram extraídos diretamente dos bancos relacionais e decifrados com as chaves AES-256 do canal sob custódia, preservando a higidez, integridade temporal e a cadeia de custódia ininterrupta da prova digital (ISO/IEC 27037).\n                </p>\n\n                <div style="margin-top:12px; background:#fff; border:1px solid #cbd5e1; padding:10px; border-radius:6px;">\n                  <div style="display:flex; justify-content:space-between; font-size:11px; font-weight:700; color:#1e293b;">\n                    <span>SELO DE INTEGRIDADE DIGITAL (HASH SHA-256 CANÔNICO DA PROVA):</span>\n                    <span style="color:#15803d;">CADEIA DE CUSTÓDIA VÁLIDA</span>\n                  </div>\n                  <div class="forensic-hash-display">${sha256}</div>\n                  <div style="font-size:10px; color:#64748b; font-family:monospace; text-align:center;">Assinatura Criptográfica: ${digitalSig}</div>\n                </div>\n\n                \x3c!-- BLOCOS DE ASSINATURA DIGITAL EM CAMPOS CORRETOS --\x3e\n                <div class="forensic-signatures" style="display:grid; grid-template-columns: repeat(3, 1fr); gap:16px; margin-top:28px;">\n                  <div style="background:#fff; border:1px solid #e2e8f0; padding:12px; border-radius:6px; text-align:center;">\n                    <div style="font-size:10px; color:#94a3b8; text-transform:uppercase; margin-bottom:28px;">Assinado Digitalmente por ICP-Fechat</div>\n                    <div class="forensic-sig-line" style="width:100%;">Oficial de Segurança & Compliance</div>\n                    <div style="font-size:10.5px; color:#334155; font-weight:700;">Fechat Security Department</div>\n                    <div style="font-size:9.5px; color:#64748b;">Matrícula: 4031-SEC-2026</div>\n                  </div>\n                  <div style="background:#fff; border:1px solid #e2e8f0; padding:12px; border-radius:6px; text-align:center;">\n                    <div style="font-size:10px; color:#94a3b8; text-transform:uppercase; margin-bottom:28px;">Validação Pericial Técnica</div>\n                    <div class="forensic-sig-line" style="width:100%;">Perito Criminal / Autoridade Policial</div>\n                    <div style="font-size:10.5px; color:#334155; font-weight:700;">${this.escapeHTML(header.officer_badge || "Autoridade Requisitante")}</div>\n                    <div style="font-size:9.5px; color:#64748b;">Laudo Técnico Pericial</div>\n                  </div>\n                  <div style="background:#fff; border:1px solid #e2e8f0; padding:12px; border-radius:6px; text-align:center;">\n                    <div style="font-size:10px; color:#94a3b8; text-transform:uppercase; margin-bottom:28px;">Juízo / Vara Competente</div>\n                    <div class="forensic-sig-line" style="width:100%;">Vara Judicial / Ministério Público</div>\n                    <div style="font-size:10.5px; color:#334155; font-weight:700;">${this.escapeHTML(header.issuing_court || "Poder Judiciário")}</div>\n                    <div style="font-size:9.5px; color:#64748b;">Autos: ${this.escapeHTML(header.court_order_number || "Processo")}</div>\n                  </div>\n                </div>\n              </div>\n\n            </div>\n          </div>\n        </div>\n      </div>\n    `;
    this.refreshIcons();
  },
  downloadDossierJson(numericId, orderNum, dossierJsonStr) {
    const blob = new Blob([dossierJsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `laudo_forense_${numericId}_${orderNum}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    this.showToast("Download do JSON pericial concluído!", "success");
  },
  async handleUnsuspendUser(userId) {
    try {
      await FechatAPI.unsuspendUser(userId);
      this.showToast("Conta reativada com sucesso!", "success");
      this.loadComplianceData();
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  async handleSuspendUser(userId) {
    if (window.Swal) {
      const result = await Swal.fire({
        title: "Suspender Conta?",
        text: "Esta ação bloqueará o acesso desta conta imediatamente por violação das políticas de segurança.",
        icon: "warning",
        showCancelButton: true,
        confirmButtonColor: "#ef4444",
        cancelButtonColor: "#475569",
        confirmButtonText: "Sim, Suspender Conta",
        cancelButtonText: "Cancelar",
      });
      if (!result.isConfirmed) return;
    } else {
      if (!confirm("Tem certeza de que deseja suspender esta conta?")) return;
    }
    try {
      await FechatAPI.suspendUser(
        userId,
        "Violação de Termos / Decisão de Autoridade de Segurança",
      );
      this.showToast("Usuário suspenso com sucesso!", "success");
      this.loadComplianceData();
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  openAddContactModal() {
    const modal = document.getElementById("modal-container");
    modal.innerHTML = `\n      <div class="modal-overlay active">\n        <div class="modal-content">\n          <div class="modal-header">\n            <h3>${t("add_contact_modal_title")}</h3>\n            <button class="btn-close" onclick="App.closeModal()"><i data-lucide="x"></i></button>\n          </div>\n          <p style="color:var(--text-muted); font-size:13px;">${t("add_contact_modal_desc")}</p>\n          <div id="modal-alert-box"></div>\n          \n          <form onsubmit="App.handleAddContactSubmit(event)" style="display:flex; flex-direction:column; gap:14px;">\n            <div class="form-group">\n              <label class="form-label">${t("identifier_input_label")}</label>\n              <input type="text" id="contact-identifier-input" class="form-input" placeholder="ID de 12 dígitos, @usuario ou e-mail" required />\n            </div>\n            <div class="form-group">\n              <label class="form-label">${t("nickname_label")}</label>\n              <input type="text" id="contact-nickname-input" class="form-input" placeholder="Ex: Carlos" />\n            </div>\n            <button type="submit" class="btn-primary">${t("add_btn")}</button>\n          </form>\n        </div>\n      </div>\n    `;
    this.refreshIcons();
  },
  async handleAddContactSubmit(e) {
    e.preventDefault();
    const idVal = document.getElementById("contact-identifier-input").value;
    const nickVal = document.getElementById("contact-nickname-input").value;
    try {
      await FechatAPI.addContact(idVal, nickVal);
      this.showToast("Contato adicionado com sucesso!", "success");
      this.closeModal();
      await this.loadData();
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  openNewChatModal() {
    const modal = document.getElementById("modal-container");
    const contactsList = this.contacts || [];
    const renderContactsHtml = (items) => {
      if (!items || items.length === 0) {
        return `\n          <div style="text-align:center; padding:24px 16px; color:var(--text-muted); font-size:13px;">\n            Nenhum contato encontrado.\n          </div>\n        `;
      }
      return items
        .map((c) => {
          const isSuspended = Boolean(
            c.contact_user.is_suspended || c.contact_user.is_active === false,
          );
          const isOnline = this.onlineUsers.has(c.contact_user.id);
          const displayName = c.nickname || c.contact_user.full_name;
          const avatarUrl =
            c.contact_user.avatar_url ||
            `https://api.dicebear.com/7.x/bottts/svg?seed=${c.contact_user.username}`;
          const isVerified = Boolean(c.contact_user.is_verified);
          const isBot = Boolean(c.contact_user.is_bot);
          return `\n          <div \n            class="new-chat-contact-item" \n            onclick="${isSuspended ? `App.showToast('Esta conta foi suspensa por infração aos termos.', 'danger')` : `App.closeModal(); App.startDirectChatWith(${c.contact_user.id})`}"\n            style="display:flex; align-items:center; gap:12px; padding:10px 12px; border-radius:var(--radius-md); cursor:pointer; transition:background 0.2s; ${isSuspended ? "opacity:0.65;" : ""}"\n            onmouseover="this.style.background='rgba(255,255,255,0.06)'"\n            onmouseout="this.style.background='transparent'"\n          >\n            <div class="avatar-wrapper" style="width:40px; height:40px;">\n              <img src="${avatarUrl}" class="avatar-img" />\n              <div class="${isSuspended ? "blocked-dot" : isOnline ? "online-dot" : "offline-dot"}"></div>\n            </div>\n            <div style="flex:1; min-width:0;">\n              <div style="display:flex; align-items:center; justify-content:space-between; gap:6px;">\n                <span style="font-size:14px; font-weight:600; color:var(--text-main); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">\n                  ${displayName}\n                  ${isSuspended ? '<span class="bot-tag" style="background:rgba(239, 68, 68, 0.2); color:#fca5a5; border-color:rgba(239, 68, 68, 0.4); margin-left:4px;">SUSPENSO</span>' : ""}\n                  ${!isSuspended && isVerified ? '<span class="verified-badge"><i data-lucide="badge-check"></i></span>' : ""}\n                  ${!isSuspended && isBot ? '<span class="bot-tag">OFICIAL</span>' : ""}\n                </span>\n                <span class="id-badge" style="font-size:10.5px;">${this.formatId(c.contact_user.numeric_id)}</span>\n              </div>\n              <div style="font-size:12px; color:var(--text-muted); margin-top:2px;">\n                ${isSuspended ? '<span style="color:#ef4444;">🚫 Conta suspensa</span>' : `@${c.contact_user.username}`}\n              </div>\n            </div>\n          </div>\n        `;
        })
        .join("");
    };
    modal.innerHTML = `\n      <div class="modal-overlay active">\n        <div class="modal-content" style="max-width:440px; padding:20px;">\n          <div class="modal-header" style="margin-bottom:12px;">\n            <div style="display:flex; align-items:center; gap:8px;">\n              <div style="width:32px; height:32px; border-radius:50%; background:rgba(99, 102, 241, 0.15); display:flex; align-items:center; justify-content:center; color:var(--primary);">\n                <i data-lucide="message-square-plus" style="width:18px; height:18px;"></i>\n              </div>\n              <h3 style="font-size:17px; font-weight:700; margin:0;">Nova Conversa</h3>\n            </div>\n            <button class="btn-close" onclick="App.closeModal()"><i data-lucide="x"></i></button>\n          </div>\n\n          \x3c!-- BOTAO PARA ADICIONAR NOVO CONTATO --\x3e\n          <div \n            onclick="App.openAddContactModal()" \n            style="display:flex; align-items:center; gap:12px; padding:10px 12px; border-radius:var(--radius-md); background:rgba(99, 102, 241, 0.12); border:1px dashed rgba(99, 102, 241, 0.4); cursor:pointer; margin-bottom:14px; transition:background 0.2s;"\n            onmouseover="this.style.background='rgba(99, 102, 241, 0.22)'"\n            onmouseout="this.style.background='rgba(99, 102, 241, 0.12)'"\n          >\n            <div style="width:36px; height:36px; border-radius:50%; background:var(--primary); display:flex; align-items:center; justify-content:center; color:#fff;">\n              <i data-lucide="user-plus" style="width:18px; height:18px;"></i>\n            </div>\n            <div style="flex:1;">\n              <div style="font-size:13.5px; font-weight:700; color:#fff;">Adicionar Novo Contato</div>\n              <div style="font-size:11.5px; color:#a5b4fc;">Adicione por ID de 12 dígitos, @usuário ou e-mail</div>\n            </div>\n            <i data-lucide="chevron-right" style="width:16px; height:16px; color:#a5b4fc;"></i>\n          </div>\n\n          \x3c!-- CAMPO DE BUSCA RAPIDA NOS CONTATOS --\x3e\n          ${contactsList.length > 3 ? `\n            <div class="search-wrapper" style="margin-bottom:10px;">\n              <span class="search-icon"><i data-lucide="search" style="width:14px; height:14px;"></i></span>\n              <input \n                type="text" \n                id="new-chat-search-input" \n                class="search-input" \n                placeholder="Filtrar contatos..." \n                oninput="App.filterNewChatContacts(this.value)" \n                style="padding:8px 12px 8px 34px; font-size:12.5px;"\n              />\n            </div>\n          ` : ""}\n\n          <div style="font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; color:var(--text-dim); margin-bottom:6px; padding:0 4px;">\n            Seus Contatos (${contactsList.length})\n          </div>\n\n          \x3c!-- LISTA DE CONTATOS --\x3e\n          <div id="new-chat-contacts-container" style="max-height:260px; overflow-y:auto; display:flex; flex-direction:column; gap:4px; margin-bottom:6px;">\n            ${renderContactsHtml(contactsList)}\n          </div>\n        </div>\n      </div>\n    `;
    this.refreshIcons();
  },
  filterNewChatContacts(query) {
    const container = document.getElementById("new-chat-contacts-container");
    if (!container) return;
    const cleanQ = (query || "").toLowerCase().trim();
    const filtered = (this.contacts || []).filter((c) => {
      const name = (c.nickname || c.contact_user.full_name || "").toLowerCase();
      const user = (c.contact_user.username || "").toLowerCase();
      const numId = (c.contact_user.numeric_id || "").toLowerCase();
      return (
        name.includes(cleanQ) || user.includes(cleanQ) || numId.includes(cleanQ)
      );
    });
    if (filtered.length === 0) {
      container.innerHTML = `<div style="text-align:center; padding:20px 10px; color:var(--text-muted); font-size:13px;">Nenhum contato coincide com "${this.escapeHTML(query)}".</div>`;
      return;
    }
    container.innerHTML = filtered
      .map((c) => {
        const isSuspended = Boolean(
          c.contact_user.is_suspended || c.contact_user.is_active === false,
        );
        const isOnline = this.onlineUsers.has(c.contact_user.id);
        const displayName = c.nickname || c.contact_user.full_name;
        const avatarUrl =
          c.contact_user.avatar_url ||
          `https://api.dicebear.com/7.x/bottts/svg?seed=${c.contact_user.username}`;
        const isVerified = Boolean(c.contact_user.is_verified);
        const isBot = Boolean(c.contact_user.is_bot);
        return `\n        <div \n          class="new-chat-contact-item" \n          onclick="${isSuspended ? `App.showToast('Esta conta foi suspensa por infração aos termos.', 'danger')` : `App.closeModal(); App.startDirectChatWith(${c.contact_user.id})`}"\n          style="display:flex; align-items:center; gap:12px; padding:10px 12px; border-radius:var(--radius-md); cursor:pointer; transition:background 0.2s; ${isSuspended ? "opacity:0.65;" : ""}"\n          onmouseover="this.style.background='rgba(255,255,255,0.06)'"\n          onmouseout="this.style.background='transparent'"\n        >\n          <div class="avatar-wrapper" style="width:40px; height:40px;">\n            <img src="${avatarUrl}" class="avatar-img" />\n            <div class="${isSuspended ? "blocked-dot" : isOnline ? "online-dot" : "offline-dot"}"></div>\n          </div>\n          <div style="flex:1; min-width:0;">\n            <div style="display:flex; align-items:center; justify-content:space-between; gap:6px;">\n              <span style="font-size:14px; font-weight:600; color:var(--text-main); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">\n                ${displayName}\n                ${isSuspended ? '<span class="bot-tag" style="background:rgba(239, 68, 68, 0.2); color:#fca5a5; border-color:rgba(239, 68, 68, 0.4); margin-left:4px;">SUSPENSO</span>' : ""}\n                ${!isSuspended && isVerified ? '<span class="verified-badge"><i data-lucide="badge-check"></i></span>' : ""}\n                ${!isSuspended && isBot ? '<span class="bot-tag">OFICIAL</span>' : ""}\n              </span>\n              <span class="id-badge" style="font-size:10.5px;">${this.formatId(c.contact_user.numeric_id)}</span>\n            </div>\n            <div style="font-size:12px; color:var(--text-muted); margin-top:2px;">\n              ${isSuspended ? '<span style="color:#ef4444;">🚫 Conta suspensa</span>' : `@${c.contact_user.username}`}\n            </div>\n          </div>\n        </div>\n      `;
      })
      .join("");
    this.refreshIcons();
  },
  openCreateGroupModal() {
    const modal = document.getElementById("modal-container");
    let membersHtml = "";
    if (this.contacts.length === 0) {
      membersHtml =
        '<div style="font-size:13px; color:var(--text-dim); padding:12px; text-align:center;">Adicione contatos primeiro para convidá-los ao grupo.</div>';
    } else {
      membersHtml = `\n        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">\n          <span id="group-selected-count" style="font-size:12.5px; color:var(--primary); font-weight:600;">0 contatos selecionados</span>\n          <button type="button" class="btn-secondary" style="padding:4px 10px; font-size:11.5px;" onclick="App.toggleSelectAllGroupMembers()">Selecionar Todos</button>\n        </div>\n        <div class="members-picker-list" style="max-height:170px; overflow-y:auto; display:flex; flex-direction:column; gap:6px; background:rgba(0,0,0,0.2); border-radius:var(--radius-md); padding:8px;">\n          ${this.contacts.map((c) => `\n            <label class="member-picker-item" id="member-picker-${c.contact_user.id}" style="display:flex; align-items:center; gap:10px; padding:6px 8px; border-radius:6px; cursor:pointer;">\n              <input type="checkbox" name="group-member" value="${c.contact_user.id}" class="member-picker-checkbox" onchange="App.updateGroupMemberCount()" />\n              <img src="${c.contact_user.avatar_url || "https://api.dicebear.com/7.x/bottts/svg?seed=" + c.contact_user.username}" style="width:30px; height:30px; border-radius:50%; object-fit:cover;" />\n              <div style="flex:1; display:flex; flex-direction:column;">\n                <span style="font-size:13px; font-weight:600;">\n                  ${c.nickname || c.contact_user.full_name}\n                  ${c.contact_user.is_verified ? '<span class="verified-badge"><i data-lucide="badge-check"></i></span>' : ""}\n                </span>\n                <span style="font-size:11px; color:var(--text-dim);">${this.formatId(c.contact_user.numeric_id)}</span>\n              </div>\n            </label>\n          `).join("")}\n        </div>\n      `;
    }
    modal.innerHTML = `\n      <div class="modal-overlay active">\n        <div class="modal-content">\n          <div class="modal-header">\n            <h3><i data-lucide="users" style="color:var(--primary);"></i> ${t("create_group_modal_title")}</h3>\n            <button class="btn-close" onclick="App.closeModal()"><i data-lucide="x"></i></button>\n          </div>\n          <p style="color:var(--text-muted); font-size:13px;">${t("create_group_desc")}</p>\n          <div id="modal-alert-box"></div>\n          \n          <form onsubmit="App.handleCreateGroupSubmit(event)" style="display:flex; flex-direction:column; gap:14px;">\n            <div class="form-group">\n              <label class="form-label">${t("group_name_label")}</label>\n              <input type="text" id="group-name-input" class="form-input" placeholder="Ex: Família & Amigos" required />\n            </div>\n            <div class="form-group">\n              <label class="form-label">${t("group_desc_label")}</label>\n              <input type="text" id="group-desc-input" class="form-input" placeholder="Ex: Espaço acolhedor e seguro" />\n            </div>\n            <div class="form-group">\n              <label class="form-label">${t("select_members_label")}</label>\n              ${membersHtml}\n            </div>\n            <button type="submit" class="btn-primary" style="margin-top:6px;">${t("create_btn")}</button>\n          </form>\n        </div>\n      </div>\n    `;
    this.refreshIcons();
  },
  toggleSelectAllGroupMembers() {
    const checkboxes = document.querySelectorAll('input[name="group-member"]');
    const allChecked = Array.from(checkboxes).every((cb) => cb.checked);
    checkboxes.forEach((cb) => {
      cb.checked = !allChecked;
    });
    this.updateGroupMemberCount();
  },
  updateGroupMemberCount() {
    const checkboxes = document.querySelectorAll(
      'input[name="group-member"]:checked',
    );
    const counter = document.getElementById("group-selected-count");
    if (counter) {
      counter.textContent = `${checkboxes.length} contato(s) selecionado(s)`;
    }
  },
  async handleCreateGroupSubmit(e) {
    e.preventDefault();
    const title = document.getElementById("group-name-input").value;
    const desc = document.getElementById("group-desc-input").value;
    const checkboxes = document.querySelectorAll(
      'input[name="group-member"]:checked',
    );
    const memberIds = Array.from(checkboxes).map((cb) => parseInt(cb.value));
    try {
      const newGroup = await FechatAPI.createGroupChat(title, desc, memberIds);
      this.showToast(
        `Grupo "${title}" criado com chave AES-256 exclusiva!`,
        "success",
      );
      this.closeModal();
      await this.loadData();
      this.openChat(newGroup);
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  async startDirectChatWith(userId) {
    try {
      const chat = await FechatAPI.createDirectChat(userId);
      await this.loadData();
      const fullChat = (this.chats || []).find((c) => c.id === chat.id) || chat;
      this.switchTab("chats");
      await this.openChat(fullChat);
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  openReportModal(
    messageId = null,
    plaintext = null,
    frankingTag = null,
    chatId = null,
  ) {
    const targetChatId =
      chatId || (this.activeChat ? this.activeChat.id : null);
    const modal = document.getElementById("modal-container");
    modal.innerHTML = `\n      <div class="modal-overlay active">\n        <div class="modal-content">\n          <div class="modal-header">\n            <h3 style="color:var(--danger);">⚠️ ${t("report_modal_title")}</h3>\n            <button class="btn-close" onclick="App.closeModal()"><i data-lucide="x"></i></button>\n          </div>\n          <p style="color:var(--text-muted); font-size:13px;">${t("report_desc")}</p>\n          <div id="modal-alert-box"></div>\n          \n          <form onsubmit="App.handleSubmitReport(event, ${messageId}, '${plaintext ? encodeURIComponent(plaintext) : ""}', '${frankingTag || ""}', ${targetChatId})" style="display:flex; flex-direction:column; gap:14px;">\n            <div class="form-group">\n              <label class="form-label">${t("report_category_label")}</label>\n              <select id="report-category-select" class="form-input">\n                <option value="csam">${t("category_csam")}</option>\n                <option value="fraud">${t("category_fraud")}</option>\n                <option value="cybercrime">${t("category_cybercrime")}</option>\n                <option value="harassment">${t("category_harassment")}</option>\n                <option value="other">${t("category_other")}</option>\n              </select>\n            </div>\n            <div class="form-group">\n              <label class="form-label">${t("report_reason_label")}</label>\n              <textarea id="report-reason-input" class="form-input" style="min-height:90px;" placeholder="Explique brevemente para que nossa equipe de segurança possa agir..." required></textarea>\n            </div>\n            <button type="submit" class="btn-danger">${t("submit_report_btn")}</button>\n          </form>\n        </div>\n      </div>\n    `;
    this.refreshIcons();
  },
  async handleSubmitReport(
    e,
    messageId,
    encodedPlaintext,
    frankingTag,
    chatId = null,
  ) {
    e.preventDefault();
    const category = document.getElementById("report-category-select").value;
    const reason = document.getElementById("report-reason-input").value;
    const plaintext = encodedPlaintext
      ? decodeURIComponent(encodedPlaintext)
      : null;
    try {
      await FechatAPI.submitReport({
        chat_id: chatId || (this.activeChat ? this.activeChat.id : null),
        message_id: messageId,
        category: category,
        reason: reason,
        plaintext_evidence: plaintext,
        franking_tag: frankingTag || null,
      });
      this.showToast(
        "Denúncia recebida com sucesso. Nossa equipe atuará com rigor.",
        "success",
      );
      this.closeModal();
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  showSecurityErrorModal(err) {
    const modal = document.getElementById("modal-container");
    if (!modal) return;
    const statusCode = err.statusCode || 500;
    const incidentId =
      err.incidentId ||
      "REQ-" + Date.now().toString(36).toUpperCase() + "-2026";
    const clientIp = err.clientIp || "127.0.0.1";
    const detail =
      err.detail ||
      err.message ||
      "Exceção interceptada pela blindagem de segurança.";
    modal.innerHTML = `\n      <div class="modal-overlay active">\n        <div class="modal-content" style="max-width:540px; border-color:rgba(239, 68, 68, 0.4); box-shadow:0 0 30px rgba(239, 68, 68, 0.2);">\n          <div style="display:flex; justify-content:space-between; align-items:center;">\n            <div style="background:rgba(239,68,68,0.15); border:1px solid rgba(239,68,68,0.3); color:#fca5a5; padding:4px 12px; border-radius:9999px; font-family:monospace; font-weight:700; font-size:13px; display:inline-flex; align-items:center; gap:6px;">\n              <i data-lucide="shield-alert" style="width:14px; height:14px;"></i>\n              <span>ERRO ${statusCode}</span>\n            </div>\n            <button class="btn-close" onclick="App.closeModal()"><i data-lucide="x"></i></button>\n          </div>\n\n          <div style="margin-top:6px;">\n            <h3 style="font-size:20px; font-weight:800; font-family:var(--font-heading); color:var(--text-main);">Instabilidade Interceptada</h3>\n            <p style="color:var(--text-muted); font-size:13.5px; line-height:1.5; margin-top:6px;">${detail}</p>\n          </div>\n\n          <div style="background:rgba(0,0,0,0.35); border:1px solid var(--border-glass); border-radius:var(--radius-md); padding:12px 16px; display:grid; grid-template-columns:1fr 1fr; gap:10px; font-size:12px;">\n            <div>\n              <div style="color:var(--text-dim); font-size:10.5px; font-weight:600; text-transform:uppercase;">ID de Rastreio</div>\n              <div style="font-family:monospace; color:#a5b4fc; font-weight:700; font-size:12px; margin-top:2px;">${incidentId}</div>\n            </div>\n            <div>\n              <div style="color:var(--text-dim); font-size:10.5px; font-weight:600; text-transform:uppercase;">IP de Origem</div>\n              <div style="font-family:monospace; color:var(--text-main); font-weight:700; font-size:12px; margin-top:2px;">${clientIp}</div>\n            </div>\n          </div>\n\n          <div style="display:flex; gap:10px; margin-top:8px;">\n            <button class="btn-secondary" style="flex:1;" onclick="App.closeModal()">\n              <i data-lucide="arrow-left" style="width:14px; height:14px;"></i>\n              <span>Voltar</span>\n            </button>\n            <button class="btn-primary" style="flex:1;" onclick="window.location.reload()">\n              <i data-lucide="rotate-cw" style="width:14px; height:14px;"></i>\n              <span>Recarregar</span>\n            </button>\n          </div>\n        </div>\n      </div>\n    `;
    this.refreshIcons();
  },
  handleChatHeaderClick() {
    if (!this.activeChat) return;
    if (this.activeChat.is_group) {
      this.openGroupInfoModal(this.activeChat.id);
    }
  },
  async openGroupInfoModal(chatId) {
    const modal = document.getElementById("modal-container");
    if (!modal) return;
    modal.innerHTML = `\n      <div class="modal-overlay active">\n        <div class="modal-content" style="max-width:540px; padding:24px;">\n          <div style="text-align:center; padding:30px; color:var(--text-muted);">\n            <i data-lucide="loader-2" class="animate-spin" style="width:24px; height:24px; margin-bottom:8px;"></i>\n            <div>Carregando dados do grupo...</div>\n          </div>\n        </div>\n      </div>\n    `;
    this.refreshIcons();
    try {
      const group = await FechatAPI.getGroupDetails(chatId);
      this._currentGroupDetails = group;
      const isAdmin = group.my_role === "admin";
      const avatarUrl =
        group.avatar_url ||
        `https://api.dicebear.com/7.x/bottts/svg?seed=${group.title}`;
      const members = group.members || [];
      const renderMembersListHTML = (list) =>
        list
          .map((m) => {
            const isCreator = Boolean(m.is_creator);
            const isMemAdmin = m.role === "admin";
            const isMe = m.user_id === this.currentUser.id;
            const memAvatar =
              m.user.avatar_url ||
              `https://api.dicebear.com/7.x/bottts/svg?seed=${m.user.username}`;
            const isOnline = this.onlineUsers.has(m.user_id);
            const isSuspended = Boolean(
              m.user.is_suspended || m.user.is_active === false,
            );
            let roleBadge =
              '<span class="group-role-badge member">Membro</span>';
            if (isCreator) {
              roleBadge =
                '<span class="group-role-badge creator">👑 Criador</span>';
            } else if (isMemAdmin) {
              roleBadge =
                '<span class="group-role-badge admin">🛡️ Admin</span>';
            }
            let actionsDropdown = "";
            if (isAdmin && !isMe && !isCreator) {
              actionsDropdown = `\n              <div style="display:flex; align-items:center; gap:6px;">\n                ${!isMemAdmin ? `\n                  <button class="btn-secondary" style="padding:4px 8px; font-size:11px;" onclick="App.promoteGroupMember(${group.id}, ${m.user_id})" title="Tornar Administrador">\n                    Promover\n                  </button>\n                ` : `\n                  <button class="btn-secondary" style="padding:4px 8px; font-size:11px; color:#fca5a5;" onclick="App.demoteGroupMember(${group.id}, ${m.user_id})" title="Rebaixar a Membro">\n                    Rebaixar\n                  </button>\n                `}\n                <button class="btn-icon" style="color:var(--danger); padding:4px;" onclick="App.removeGroupMember(${group.id}, ${m.user_id}, '${this.escapeHTML(m.user.full_name).replace(/'/g, "\\'")}')" title="Remover do Grupo">\n                  <i data-lucide="user-minus" style="width:15px; height:15px;"></i>\n                </button>\n              </div>\n            `;
            }
            return `\n            <div class="group-member-item" style="border-bottom:1px solid rgba(255,255,255,0.04);">\n              <div class="avatar-wrapper" style="width:36px; height:36px;">\n                <img src="${memAvatar}" class="avatar-img" />\n                <div class="${isSuspended ? "blocked-dot" : isOnline ? "online-dot" : "offline-dot"}"></div>\n              </div>\n              <div style="flex:1; min-width:0;">\n                <div style="display:flex; align-items:center; gap:6px;">\n                  <span style="font-size:13.5px; font-weight:600; color:var(--text-main); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">\n                    ${this.escapeHTML(m.user.full_name)} ${isMe ? '<span style="color:var(--primary); font-size:11px;">(Você)</span>' : ""}\n                  </span>\n                  ${roleBadge}\n                </div>\n                <div style="font-size:11.5px; color:var(--text-muted);">\n                  @${m.user.username} • <span style="font-family:monospace;">${this.formatId(m.user.numeric_id)}</span>\n                </div>\n              </div>\n              ${actionsDropdown}\n            </div>\n          `;
          })
          .join("");
      modal.innerHTML = `\n        <div class="modal-overlay active">\n          <div class="modal-content" style="max-width:560px; max-height:88vh; overflow-y:auto; padding:24px;">\n            <div class="modal-header" style="margin-bottom:16px;">\n              <h3 style="font-size:18px; font-weight:800;">Dados do Grupo</h3>\n              <button class="btn-close" onclick="App.closeModal()"><i data-lucide="x"></i></button>\n            </div>\n\n            \x3c!-- CABEÇALHO DO GRUPO (FOTO, NOME, DESCRIÇÃO) --\x3e\n            <div style="display:flex; flex-direction:column; align-items:center; text-align:center; margin-bottom:20px;">\n              <div class="avatar-wrapper" style="width:76px; height:76px; margin-bottom:12px; box-shadow:0 6px 20px rgba(0,0,0,0.3);">\n                <img src="${avatarUrl}" class="avatar-img" id="group-detail-avatar-preview" />\n              </div>\n              \n              <div style="width:100%; max-width:440px;">\n                <input \n                  type="text" \n                  id="group-edit-title" \n                  class="form-input" \n                  value="${this.escapeHTML(group.title)}" \n                  ${!isAdmin && group.only_admins_edit_info ? 'disabled style="opacity:0.7; text-align:center; font-weight:700; font-size:16px;"' : 'style="text-align:center; font-weight:700; font-size:16px;"'}\n                  placeholder="Nome do Grupo" \n                />\n                <textarea \n                  id="group-edit-desc" \n                  class="form-input" \n                  rows="2" \n                  ${!isAdmin && group.only_admins_edit_info ? 'disabled style="opacity:0.7; font-size:12.5px; margin-top:8px; resize:none;"' : 'style="font-size:12.5px; margin-top:8px; resize:none;"'}\n                  placeholder="Descrição do grupo (opcional)"\n                >${this.escapeHTML(group.description || "")}</textarea>\n              </div>\n\n              ${isAdmin || !group.only_admins_edit_info ? `\n                <button class="btn-primary" style="margin-top:10px; padding:6px 16px; font-size:12px;" onclick="App.saveGroupInfo(${group.id})">\n                  Salvar Informações\n                </button>\n              ` : ""}\n            </div>\n\n            \x3c!-- PERMISSÕES DO GRUPO (APENAS PARA ADMINISTRADORES) --\x3e\n            ${isAdmin ? `\n              <div style="background:rgba(0,0,0,0.25); border:1px solid var(--border-glass); border-radius:var(--radius-md); padding:14px; margin-bottom:20px;">\n                <div style="font-size:12.5px; font-weight:700; color:var(--text-main); margin-bottom:10px; display:flex; align-items:center; gap:6px;">\n                  <i data-lucide="sliders" style="width:15px; height:15px; color:var(--primary);"></i>\n                  <span>Permissões e Configurações</span>\n                </div>\n                \n                <label style="display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; cursor:pointer; font-size:13px; color:var(--text-main);">\n                  <span>Apenas administradores podem enviar mensagens</span>\n                  <input type="checkbox" id="group-perm-only-admins-send" ${group.only_admins_send_messages ? "checked" : ""} onchange="App.saveGroupInfo(${group.id})" />\n                </label>\n\n                <label style="display:flex; align-items:center; justify-content:space-between; cursor:pointer; font-size:13px; color:var(--text-main);">\n                  <span>Apenas administradores podem editar dados do grupo</span>\n                  <input type="checkbox" id="group-perm-only-admins-edit" ${group.only_admins_edit_info ? "checked" : ""} onchange="App.saveGroupInfo(${group.id})" />\n                </label>\n              </div>\n            ` : ""}\n\n            \x3c!-- BOTAO DE CONVITE VIA LINK --\x3e\n            ${isAdmin && !group.is_suspended ? `\n              <button class="btn-secondary" style="width:100%; margin-bottom:18px; display:flex; align-items:center; justify-content:center; gap:8px; padding:10px;" onclick="App.openGroupInviteLinkModal(${group.id})">\n                <i data-lucide="link" style="width:16px; height:16px; color:var(--primary);"></i>\n                <span>Convidar para o grupo via link</span>\n              </button>\n            ` : ""}\n\n            \x3c!-- LISTA DE PARTICIPANTES --\x3e\n            <div style="margin-bottom:16px;">\n              <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:10px;">\n                <div style="font-size:13px; font-weight:700; color:var(--text-main);">\n                  Participantes (${members.length})\n                </div>\n                ${isAdmin || !group.only_admins_edit_info ? `\n                  <button class="btn-primary" style="padding:4px 10px; font-size:12px; display:flex; align-items:center; gap:4px;" onclick="App.openAddGroupMembersModal(${group.id})">\n                    <i data-lucide="user-plus" style="width:14px; height:14px;"></i>\n                    <span>Adicionar</span>\n                  </button>\n                ` : ""}\n              </div>\n\n              \x3c!-- BUSCA DE MEMBROS --\x3e\n              ${members.length > 4 ? `\n                <div class="search-wrapper" style="margin-bottom:10px;">\n                  <span class="search-icon"><i data-lucide="search" style="width:14px; height:14px;"></i></span>\n                  <input type="text" class="search-input" placeholder="Buscar participante..." oninput="App.filterGroupMembers(this.value)" style="padding:7px 12px 7px 32px; font-size:12px;" />\n                </div>\n              ` : ""}\n\n              <div id="group-members-list-container" style="max-height:220px; overflow-y:auto; display:flex; flex-direction:column; gap:4px;">\n                ${renderMembersListHTML(members)}\n              </div>\n            </div>\n\n            \x3c!-- ACOES DO GRUPO (DENUNCIAR E SAIR) --\x3e\n            <div style="border-top:1px solid var(--border-glass); padding-top:16px; margin-top:10px; display:flex; flex-direction:column; gap:8px;">\n              <button class="btn-secondary" style="width:100%; color:var(--danger); border-color:rgba(239, 68, 68, 0.3); display:flex; align-items:center; justify-content:center; gap:8px;" onclick="App.closeModal(); App.openReportModal(null, null, null, ${group.id})">\n                <i data-lucide="alert-triangle" style="width:16px; height:16px;"></i>\n                <span>Denunciar Grupo</span>\n              </button>\n              <button class="btn-danger" style="width:100%; display:flex; align-items:center; justify-content:center; gap:8px;" onclick="App.closeModal(); App.handleDeleteChat(${group.id}, true)">\n                <i data-lucide="log-out" style="width:16px; height:16px;"></i>\n                <span>Sair do Grupo</span>\n              </button>\n            </div>\n          </div>\n        </div>\n      `;
      this.refreshIcons();
    } catch (err) {
      this.showToast(err.message, "danger");
      this.closeModal();
    }
  },
  filterGroupMembers(query) {
    const container = document.getElementById("group-members-list-container");
    if (!container || !this._currentGroupDetails) return;
    const clean = (query || "").toLowerCase().trim();
    const filtered = (this._currentGroupDetails.members || []).filter((m) => {
      const name = (m.user.full_name || "").toLowerCase();
      const user = (m.user.username || "").toLowerCase();
      const id = (m.user.numeric_id || "").toLowerCase();
      return name.includes(clean) || user.includes(clean) || id.includes(clean);
    });
    if (filtered.length === 0) {
      container.innerHTML =
        '<div style="text-align:center; padding:16px; color:var(--text-muted); font-size:12px;">Nenhum participante encontrado.</div>';
      return;
    }
    const group = this._currentGroupDetails;
    const isAdmin = group.my_role === "admin";
    container.innerHTML = filtered
      .map((m) => {
        const isCreator = Boolean(m.is_creator);
        const isMemAdmin = m.role === "admin";
        const isMe = m.user_id === this.currentUser.id;
        const memAvatar =
          m.user.avatar_url ||
          `https://api.dicebear.com/7.x/bottts/svg?seed=${m.user.username}`;
        const isOnline = this.onlineUsers.has(m.user_id);
        const isSuspended = Boolean(
          m.user.is_suspended || m.user.is_active === false,
        );
        let roleBadge = '<span class="group-role-badge member">Membro</span>';
        if (isCreator) {
          roleBadge =
            '<span class="group-role-badge creator">👑 Criador</span>';
        } else if (isMemAdmin) {
          roleBadge = '<span class="group-role-badge admin">🛡️ Admin</span>';
        }
        let actionsDropdown = "";
        if (isAdmin && !isMe && !isCreator) {
          actionsDropdown = `\n          <div style="display:flex; align-items:center; gap:6px;">\n            ${!isMemAdmin ? `\n              <button class="btn-secondary" style="padding:4px 8px; font-size:11px;" onclick="App.promoteGroupMember(${group.id}, ${m.user_id})" title="Tornar Administrador">\n                Promover\n              </button>\n            ` : `\n              <button class="btn-secondary" style="padding:4px 8px; font-size:11px; color:#fca5a5;" onclick="App.demoteGroupMember(${group.id}, ${m.user_id})" title="Rebaixar a Membro">\n                Rebaixar\n              </button>\n            `}\n            <button class="btn-icon" style="color:var(--danger); padding:4px;" onclick="App.removeGroupMember(${group.id}, ${m.user_id}, '${this.escapeHTML(m.user.full_name).replace(/'/g, "\\'")}')" title="Remover do Grupo">\n              <i data-lucide="user-minus" style="width:15px; height:15px;"></i>\n            </button>\n          </div>\n        `;
        }
        return `\n        <div class="group-member-item" style="border-bottom:1px solid rgba(255,255,255,0.04);">\n          <div class="avatar-wrapper" style="width:36px; height:36px;">\n            <img src="${memAvatar}" class="avatar-img" />\n            <div class="${isSuspended ? "blocked-dot" : isOnline ? "online-dot" : "offline-dot"}"></div>\n          </div>\n          <div style="flex:1; min-width:0;">\n            <div style="display:flex; align-items:center; gap:6px;">\n              <span style="font-size:13.5px; font-weight:600; color:var(--text-main); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">\n                ${this.escapeHTML(m.user.full_name)} ${isMe ? '<span style="color:var(--primary); font-size:11px;">(Você)</span>' : ""}\n              </span>\n              ${roleBadge}\n            </div>\n            <div style="font-size:11.5px; color:var(--text-muted);">\n              @${m.user.username} • <span style="font-family:monospace;">${this.formatId(m.user.numeric_id)}</span>\n            </div>\n          </div>\n          ${actionsDropdown}\n        </div>\n      `;
      })
      .join("");
    this.refreshIcons();
  },
  async saveGroupInfo(chatId) {
    const title = document.getElementById("group-edit-title")?.value;
    const desc = document.getElementById("group-edit-desc")?.value;
    const onlyAdminsSend = document.getElementById(
      "group-perm-only-admins-send",
    )?.checked;
    const onlyAdminsEdit = document.getElementById(
      "group-perm-only-admins-edit",
    )?.checked;
    const payload = {};
    if (title !== undefined) payload.title = title;
    if (desc !== undefined) payload.description = desc;
    if (onlyAdminsSend !== undefined)
      payload.only_admins_send_messages = onlyAdminsSend;
    if (onlyAdminsEdit !== undefined)
      payload.only_admins_edit_info = onlyAdminsEdit;
    try {
      await FechatAPI.updateGroupInfo(chatId, payload);
      this.showToast("Configurações do grupo atualizadas!", "success");
      await this.loadData();
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  openAddGroupMembersModal(chatId) {
    const modal = document.getElementById("modal-container");
    const existingUids = new Set(
      (this._currentGroupDetails?.members || []).map((m) => m.user_id),
    );
    const availableContacts = (this.contacts || []).filter(
      (c) =>
        !existingUids.has(c.contact_user.id) &&
        !c.contact_user.is_suspended &&
        c.contact_user.is_active !== false,
    );
    if (availableContacts.length === 0) {
      this.showToast(
        "Todos os seus contatos já participam deste grupo ou estão suspensos.",
        "info",
      );
      return;
    }
    modal.innerHTML = `\n      <div class="modal-overlay active">\n        <div class="modal-content" style="max-width:440px; padding:20px;">\n          <div class="modal-header" style="margin-bottom:12px;">\n            <h3 style="font-size:16px; font-weight:700;">Adicionar Participantes</h3>\n            <button class="btn-close" onclick="App.openGroupInfoModal(${chatId})"><i data-lucide="arrow-left"></i></button>\n          </div>\n\n          <p style="color:var(--text-muted); font-size:12.5px; margin-bottom:12px;">\n            Selecione os contatos para adicionar ao grupo:\n          </p>\n\n          <form onsubmit="App.handleAddGroupMembersSubmit(event, ${chatId})">\n            <div style="max-height:240px; overflow-y:auto; display:flex; flex-direction:column; gap:6px; margin-bottom:14px;">\n              ${availableContacts.map((c) => `\n                <label style="display:flex; align-items:center; gap:10px; padding:8px 10px; border-radius:var(--radius-md); background:rgba(255,255,255,0.03); cursor:pointer;">\n                  <input type="checkbox" name="add-group-member" value="${c.contact_user.id}" />\n                  <div class="avatar-wrapper" style="width:32px; height:32px;">\n                    <img src="${c.contact_user.avatar_url || `https://api.dicebear.com/7.x/bottts/svg?seed=${c.contact_user.username}`}" class="avatar-img" />\n                  </div>\n                  <div style="flex:1; min-width:0;">\n                    <div style="font-size:13px; font-weight:600; color:var(--text-main);">${this.escapeHTML(c.nickname || c.contact_user.full_name)}</div>\n                    <div style="font-size:11px; color:var(--text-muted);">@${c.contact_user.username}</div>\n                  </div>\n                </label>\n              `).join("")}\n            </div>\n\n            <div style="display:flex; gap:10px;">\n              <button type="button" class="btn-secondary" style="flex:1;" onclick="App.openGroupInfoModal(${chatId})">Cancelar</button>\n              <button type="submit" class="btn-primary" style="flex:1;">Adicionar Selecionados</button>\n            </div>\n          </form>\n        </div>\n      </div>\n    `;
    this.refreshIcons();
  },
  async handleAddGroupMembersSubmit(e, chatId) {
    e.preventDefault();
    const checkboxes = document.querySelectorAll(
      'input[name="add-group-member"]:checked',
    );
    const userIds = Array.from(checkboxes).map((cb) => parseInt(cb.value));
    if (userIds.length === 0) {
      this.showToast("Selecione pelo menos um contato.", "warning");
      return;
    }
    try {
      await FechatAPI.addGroupMembers(chatId, userIds);
      this.showToast("Participantes adicionados com sucesso!", "success");
      await this.openGroupInfoModal(chatId);
      await this.loadData();
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  async promoteGroupMember(chatId, userId) {
    try {
      await FechatAPI.changeGroupMemberRole(chatId, userId, "admin");
      this.showToast("Participante promovido a Administrador!", "success");
      await this.openGroupInfoModal(chatId);
      await this.loadData();
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  async demoteGroupMember(chatId, userId) {
    try {
      await FechatAPI.changeGroupMemberRole(chatId, userId, "member");
      this.showToast("Administrador rebaixado a Membro.", "info");
      await this.openGroupInfoModal(chatId);
      await this.loadData();
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  async removeGroupMember(chatId, userId, userName) {
    if (window.Swal) {
      const result = await Swal.fire({
        title: "Remover Participante?",
        text: `Deseja realmente remover ${userName} deste grupo?`,
        icon: "warning",
        showCancelButton: true,
        confirmButtonColor: "#ef4444",
        cancelButtonColor: "#475569",
        confirmButtonText: "Sim, Remover",
        cancelButtonText: "Cancelar",
        background: "#131b2e",
        color: "#f8fafc",
      });
      if (!result.isConfirmed) return;
    } else {
      if (!confirm(`Deseja realmente remover ${userName} deste grupo?`)) return;
    }
    try {
      await FechatAPI.removeGroupMember(chatId, userId);
      this.showToast(`${userName} foi removido do grupo.`, "success");
      await this.openGroupInfoModal(chatId);
      await this.loadData();
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  async pinMessageForEveryone(chatId, messageId) {
    try {
      await FechatAPI.pinGroupMessage(chatId, messageId);
      this.showToast(
        messageId
          ? "Mensagem fixada para todos os membros!"
          : "Mensagem desafixada.",
        "success",
      );
      if (this.activeChat && this.activeChat.id === chatId) {
        this.activeChat.pinned_message_id = messageId;
        this.updatePinnedMessageBanner(chatId, messageId);
      }
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  async deleteMessageForEveryone(messageId) {
    if (window.Swal) {
      const result = await Swal.fire({
        title: "Apagar para Todos?",
        text: "Esta mensagem será apagada para todos os participantes da conversa.",
        icon: "warning",
        showCancelButton: true,
        confirmButtonColor: "#ef4444",
        cancelButtonColor: "#475569",
        confirmButtonText: "Sim, Apagar para Todos",
        cancelButtonText: "Cancelar",
        background: "#131b2e",
        color: "#f8fafc",
      });
      if (!result.isConfirmed) return;
    } else {
      if (!confirm("Deseja realmente apagar esta mensagem para todos?")) return;
    }
    try {
      await FechatAPI.deleteMessageForEveryone(messageId);
      this.showToast("Mensagem apagada para todos com sucesso.", "success");
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  updatePinnedMessageBanner(chatId, pinnedMsgId) {
    let bar = document.getElementById("pinned-message-bar");
    if (!pinnedMsgId) {
      if (bar) bar.remove();
      return;
    }
    const header = document.querySelector(".chat-top-header");
    if (!header) return;
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "pinned-message-bar";
      bar.className = "pinned-message-bar";
      bar.onclick = () => App.scrollToMessage(pinnedMsgId);
      header.parentNode.insertBefore(bar, header.nextSibling);
    }
    const isAdmin = Boolean(
      this.activeChat && this.activeChat.my_role === "admin",
    );
    bar.innerHTML = `\n      <div class="pinned-bar-left">\n        <div class="pinned-bar-icon"><i data-lucide="pin" style="width:16px; height:16px;"></i></div>\n        <div class="pinned-bar-content">\n          <span class="pinned-bar-title">📌 Mensagem Fixada</span>\n          <span class="pinned-bar-snippet" id="pinned-bar-snippet-text">Clique para visualizar</span>\n        </div>\n      </div>\n      ${isAdmin ? `\n        <button type="button" class="btn-icon" style="padding:2px;" onclick="event.stopPropagation(); App.pinMessageForEveryone(${chatId}, null)" title="Desafixar mensagem">\n          <i data-lucide="x" style="width:14px; height:14px;"></i>\n        </button>\n      ` : ""}\n    `;
    this.refreshIcons();
  },
  async openGroupInviteLinkModal(chatId) {
    const modal = document.getElementById("modal-container");
    if (!modal) return;
    modal.innerHTML = `\n      <div class="modal-overlay active">\n        <div class="modal-content" style="max-width:480px; padding:24px;">\n          <div style="text-align:center; padding:20px; color:var(--text-muted);">\n            <i data-lucide="loader-2" class="animate-spin" style="width:24px; height:24px; margin-bottom:8px;"></i>\n            <div>Gerando link de convite seguro...</div>\n          </div>\n        </div>\n      </div>\n    `;
    this.refreshIcons();
    try {
      const data = await FechatAPI.getGroupInviteLink(chatId);
      const fullUrl = `${window.location.origin}/#invite/${data.invite_code}`;
      modal.innerHTML = `\n        <div class="modal-overlay active">\n          <div class="modal-content" style="max-width:480px; padding:24px;">\n            <div class="modal-header" style="margin-bottom:16px;">\n              <h3 style="font-size:18px; font-weight:800; display:flex; align-items:center; gap:8px;">\n                <i data-lucide="link" style="color:var(--primary); width:20px; height:20px;"></i>\n                <span>Link de Convite do Grupo</span>\n              </h3>\n              <button class="btn-close" onclick="App.openGroupInfoModal(${chatId})"><i data-lucide="arrow-left"></i></button>\n            </div>\n\n            <p style="color:var(--text-muted); font-size:13px; margin-bottom:16px; line-height:1.5;">\n              Qualquer pessoa cadastrada no Fechat poderá usar este link para entrar neste grupo sem precisar de aprovação de administrador.\n            </p>\n\n            <div style="background:rgba(0,0,0,0.3); border:1px solid var(--border-glass); border-radius:var(--radius-md); padding:12px; margin-bottom:16px;">\n              <div style="font-size:11px; color:var(--text-dim); text-transform:uppercase; font-weight:700; margin-bottom:4px;">Link de Entrada</div>\n              <div style="font-family:monospace; font-size:13px; color:#a5b4fc; word-break:break-all; user-select:all;" id="group-invite-full-url">${fullUrl}</div>\n            </div>\n\n            <div style="display:flex; flex-direction:column; gap:10px;">\n              <button class="btn-primary" style="display:flex; align-items:center; justify-content:center; gap:8px;" onclick="navigator.clipboard.writeText('${fullUrl}'); App.showToast('Link de convite copiado!', 'success');">\n                <i data-lucide="copy" style="width:16px; height:16px;"></i>\n                <span>Copiar Link de Convite</span>\n              </button>\n\n              <button class="btn-secondary" style="display:flex; align-items:center; justify-content:center; gap:8px; color:#fca5a5; border-color:rgba(239,68,68,0.3);" onclick="App.handleRevokeGroupInvite(${chatId})">\n                <i data-lucide="refresh-cw" style="width:16px; height:16px;"></i>\n                <span>Revogar Link e Gerar Novo</span>\n              </button>\n            </div>\n          </div>\n        </div>\n      `;
      this.refreshIcons();
    } catch (err) {
      this.showToast(err.message, "danger");
      this.openGroupInfoModal(chatId);
    }
  },
  async handleRevokeGroupInvite(chatId) {
    if (window.Swal) {
      const result = await Swal.fire({
        title: "Revogar Link de Convite?",
        text: "O link de convite anterior deixará de funcionar imediatamente. Um novo link será gerado.",
        icon: "warning",
        showCancelButton: true,
        confirmButtonColor: "#ef4444",
        cancelButtonColor: "#475569",
        confirmButtonText: "Sim, Revogar Link",
        cancelButtonText: "Cancelar",
        background: "#131b2e",
        color: "#f8fafc",
      });
      if (!result.isConfirmed) return;
    } else {
      if (!confirm("Deseja realmente revogar o link de convite anterior?"))
        return;
    }
    try {
      await FechatAPI.revokeGroupInviteLink(chatId);
      this.showToast(
        "Link de convite revogado com sucesso! Novo link ativo.",
        "success",
      );
      await this.openGroupInviteLinkModal(chatId);
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
  checkUrlInviteHash() {
    const hash = window.location.hash || "";
    if (hash.startsWith("#invite/")) {
      const inviteCode = hash.replace("#invite/", "").trim();
      if (inviteCode) {
        this.openJoinGroupModal(inviteCode);
      }
    }
  },
  async openJoinGroupModal(inviteCode) {
    if (!this.currentUser) return;
    const modal = document.getElementById("modal-container");
    if (!modal) return;
    modal.innerHTML = `\n      <div class="modal-overlay active">\n        <div class="modal-content" style="max-width:440px; padding:24px; text-align:center;">\n          <i data-lucide="loader-2" class="animate-spin" style="width:24px; height:24px; margin-bottom:8px;"></i>\n          <div style="color:var(--text-muted);">Verificando convite de grupo...</div>\n        </div>\n      </div>\n    `;
    this.refreshIcons();
    try {
      const preview = await FechatAPI.getGroupPreviewByInvite(inviteCode);
      const avatarUrl =
        preview.avatar_url ||
        `https://api.dicebear.com/7.x/bottts/svg?seed=${preview.title}`;
      modal.innerHTML = `\n        <div class="modal-overlay active">\n          <div class="modal-content" style="max-width:440px; padding:24px; text-align:center;">\n            <div class="avatar-wrapper" style="width:84px; height:84px; margin:0 auto 14px; box-shadow:0 8px 24px rgba(0,0,0,0.35);">\n              <img src="${avatarUrl}" class="avatar-img" />\n            </div>\n\n            <h3 style="font-size:20px; font-weight:800; font-family:var(--font-heading); color:var(--text-main); margin-bottom:4px;">\n              ${this.escapeHTML(preview.title)}\n            </h3>\n\n            <div style="font-size:13px; color:var(--primary); font-weight:600; margin-bottom:12px;">\n              ${preview.member_count} participante(s)\n            </div>\n\n            ${preview.description ? `\n              <p style="color:var(--text-muted); font-size:13px; line-height:1.5; margin-bottom:20px; background:rgba(255,255,255,0.03); padding:10px; border-radius:var(--radius-md);">\n                ${this.escapeHTML(preview.description)}\n              </p>\n            ` : '<div style="margin-bottom:20px;"></div>'}\n\n            <div style="display:flex; gap:10px;">\n              <button class="btn-secondary" style="flex:1;" onclick="App.closeModal(); window.location.hash = '';">\n                Cancelar\n              </button>\n              <button class="btn-primary" style="flex:1;" onclick="App.handleJoinGroupByInvite('${inviteCode}')">\n                ${preview.is_already_member ? "Abrir Grupo" : "Entrar no Grupo"}\n              </button>\n            </div>\n          </div>\n        </div>\n      `;
      this.refreshIcons();
    } catch (err) {
      modal.innerHTML = `\n        <div class="modal-overlay active">\n          <div class="modal-content" style="max-width:440px; padding:24px; text-align:center;">\n            <div style="width:50px; height:50px; border-radius:50%; background:rgba(239,68,68,0.15); color:#ef4444; display:flex; align-items:center; justify-content:center; margin:0 auto 12px;">\n              <i data-lucide="alert-triangle" style="width:26px; height:26px;"></i>\n            </div>\n            <h3 style="font-size:18px; font-weight:800; color:var(--text-main); margin-bottom:6px;">Convite Inválido</h3>\n            <p style="color:var(--text-muted); font-size:13px; margin-bottom:16px;">${err.message || "O link de convite é inválido, foi revogado ou o grupo foi suspenso."}</p>\n            <button class="btn-primary" style="width:100%;" onclick="App.closeModal(); window.location.hash = '';">Entendido</button>\n          </div>\n        </div>\n      `;
      this.refreshIcons();
    }
  },
  async handleJoinGroupByInvite(inviteCode) {
    try {
      const res = await FechatAPI.joinGroupViaInvite(inviteCode);
      this.showToast(`Você entrou no grupo "${res.chat.title}"!`, "success");
      this.closeModal();
      window.location.hash = "";
      await this.loadData();
      const chat =
        (this.chats || []).find((c) => c.id === res.chat.id) || res.chat;
      this.switchTab("chats");
      await this.openChat(chat);
    } catch (err) {
      this.showToast(err.message, "danger");
    }
  },
};
window.addEventListener("DOMContentLoaded", () => {
  App.init();
});
