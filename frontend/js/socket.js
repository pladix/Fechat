class FechatSocketClient {
  constructor() {
    this.socket = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 15;
    this.reconnectDelay = 1500;
    this.pingInterval = null;
    this.pendingRpcs = new Map();
    this.connectPromise = null;
    this.currentToken = null;
    this.handlers = {
      onMessage: [],
      onPresence: [],
      onTyping: [],
      onMessagesRead: [],
      onBlock: [],
      onGroupUpdate: [],
      onMessagePinned: [],
      onMessageDeleted: [],
      onGroupSuspended: [],
      onCallSignal: [],
    };
  }
  isConnected() {
    return this.socket && this.socket.readyState === WebSocket.OPEN;
  }
  isConnecting() {
    return this.socket && this.socket.readyState === WebSocket.CONNECTING;
  }
  async updateTunnelKey(token = null) {
    this.currentToken =
      token ||
      (window.FechatAPI
        ? FechatAPI.getToken()
        : localStorage.getItem("fechat_token"));
    if (window.FechatCrypto) {
      const wireKey = await FechatCrypto.deriveSessionWireKey(
        this.currentToken,
      );
      FechatCrypto.setWireKeyHex(wireKey);
    }
  }
  async sendSealed(payload) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      if (window.FechatCrypto) {
        const sealed = await FechatCrypto.sealWirePacket(payload);
        this.socket.send(JSON.stringify(sealed));
      } else {
        this.socket.send(JSON.stringify(payload));
      }
    }
  }
  async ensureConnected(token = null) {
    if (this.isConnected()) {
      return Promise.resolve();
    }
    if (this.connectPromise) {
      return this.connectPromise;
    }
    await this.updateTunnelKey(token);
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = this.currentToken
      ? `${protocol}//${host}/ws/chat?token=${encodeURIComponent(this.currentToken)}`
      : `${protocol}//${host}/ws/chat`;
    this.connectPromise = new Promise((resolve, reject) => {
      try {
        if (
          this.socket &&
          this.socket.readyState !== WebSocket.CLOSED &&
          this.socket.readyState !== WebSocket.CLOSING
        ) {
          try {
            this.socket.close();
          } catch (_) {}
        }
        this.socket = new WebSocket(wsUrl);
        const openTimer = setTimeout(() => {
          if (!this.isConnected()) {
            this.connectPromise = null;
            reject(new Error("Tempo limite esgotado ao conectar WebSocket"));
          }
        }, 8e3);
        this.socket.onopen = () => {
          clearTimeout(openTimer);
          this.reconnectAttempts = 0;
          this.startPing();
          this.connectPromise = null;
          resolve();
        };
        this.socket.onmessage = async (event) => {
          try {
            const raw = JSON.parse(event.data);
            let payload = raw;
            if (raw && typeof raw === "object" && raw._shield === "aes256gcm") {
              payload = window.FechatCrypto
                ? await FechatCrypto.unsealWirePacket(raw)
                : raw;
            }
            if (payload) {
              this.dispatch(payload);
            }
          } catch (_) {}
        };
        this.socket.onclose = (event) => {
          this.stopPing();
          this.connectPromise = null;
          if (
            event.code !== 1e3 &&
            event.code !== 4001 &&
            event.code !== 4003 &&
            this.reconnectAttempts < this.maxReconnectAttempts
          ) {
            setTimeout(() => {
              this.reconnectAttempts++;
              this.connect(this.currentToken);
            }, this.reconnectDelay);
          }
        };
        this.socket.onerror = () => {
          clearTimeout(openTimer);
          this.connectPromise = null;
        };
      } catch (err) {
        this.connectPromise = null;
        reject(err);
      }
    });
    return this.connectPromise;
  }
  async callRpc(action, payload = {}, timeoutMs = 8e3) {
    await this.ensureConnected();
    if (!this.isConnected()) {
      throw new Error(`Túnel WebSocket desconectado ao executar '${action}'`);
    }
    return new Promise(async (resolve, reject) => {
      const rpcId =
        "rpc_" + Math.random().toString(36).substring(2, 10) + "_" + Date.now();
      const timer = setTimeout(() => {
        if (this.pendingRpcs.has(rpcId)) {
          this.pendingRpcs.delete(rpcId);
          reject(
            new Error(
              `Tempo esgotado ao aguardar resposta RPC para '${action}'`,
            ),
          );
        }
      }, timeoutMs);
      this.pendingRpcs.set(rpcId, {
        resolve: async (data) => {
          if (data && data.access_token) {
            await this.updateTunnelKey(data.access_token);
          }
          resolve(data);
        },
        reject: reject,
        timer: timer,
      });
      const requestPayload = {
        type: "rpc_request",
        rpc_id: rpcId,
        action: action,
        payload: payload,
      };
      try {
        await this.sendSealed(requestPayload);
      } catch (err) {
        clearTimeout(timer);
        this.pendingRpcs.delete(rpcId);
        reject(err);
      }
    });
  }
  connect(token) {
    this.ensureConnected(token).catch(() => {});
  }
  startPing() {
    this.stopPing();
    this.pingInterval = setInterval(async () => {
      if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        await this.sendSealed({ type: "ping" });
      }
    }, 2e4);
  }
  stopPing() {
    if (this.pingInterval) clearInterval(this.pingInterval);
  }
  async sendTyping(chatId, isTyping) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      await this.sendSealed({
        type: "typing",
        chat_id: chatId,
        is_typing: isTyping,
      });
    }
  }
  on(event, callback) {
    const key =
      event === "call_signal" || event === "call"
        ? "onCallSignal"
        : event === "message"
          ? "onMessage"
          : event === "presence"
            ? "onPresence"
            : event === "typing"
              ? "onTyping"
              : event === "read"
                ? "onMessagesRead"
                : event === "block"
                  ? "onBlock"
                  : event === "group_update"
                    ? "onGroupUpdate"
                    : this.handlers[event]
                      ? event
                      : `on${event.charAt(0).toUpperCase() + event.slice(1)}`;
    if (!this.handlers[key]) {
      this.handlers[key] = [];
    }
    this.handlers[key].push(callback);
  }
  dispatch(payload) {
    if (!payload || typeof payload !== "object") return;
    if (payload.type === "rpc_response" && payload.rpc_id) {
      const pending = this.pendingRpcs.get(payload.rpc_id);
      if (pending) {
        clearTimeout(pending.timer);
        this.pendingRpcs.delete(payload.rpc_id);
        if (payload.success) {
          pending.resolve(payload.data);
        } else {
          const err = new Error(
            payload.error || "Erro no processamento do WebSocket RPC.",
          );
          err.statusCode = payload.status_code || 400;
          err.incidentId = payload.incident_id;
          err.clientIp = payload.client_ip;
          pending.reject(err);
        }
      }
      return;
    }
    if (payload.type === "new_message") {
      this.handlers.onMessage.forEach((cb) => cb(payload.data || payload));
    } else if (
      payload.type === "presence_update" ||
      payload.type === "presence"
    ) {
      this.handlers.onPresence.forEach((cb) => cb(payload.data || payload));
    } else if (
      payload.type === "typing_indicator" ||
      payload.type === "typing"
    ) {
      this.handlers.onTyping.forEach((cb) => cb(payload.data || payload));
    } else if (payload.type === "read") {
      this.handlers.onMessagesRead.forEach((cb) => cb(payload.data || payload));
    } else if (payload.type === "block_update") {
      this.handlers.onBlock.forEach((cb) => cb(payload.data || payload));
    } else if (
      payload.type === "group_info_updated" ||
      payload.type === "group_members_updated"
    ) {
      this.handlers.onGroupUpdate.forEach((cb) => cb(payload.data || payload));
    } else if (payload.type === "message_pinned") {
      this.handlers.onMessagePinned.forEach((cb) =>
        cb(payload.data || payload),
      );
    } else if (payload.type === "message_deleted_for_everyone") {
      this.handlers.onMessageDeleted.forEach((cb) =>
        cb(payload.data || payload),
      );
    } else if (payload.type === "group_suspended") {
      this.handlers.onGroupSuspended = this.handlers.onGroupSuspended || [];
      this.handlers.onGroupSuspended.forEach((cb) =>
        cb(payload.data || payload),
      );
    } else if (payload.type === "call_signal") {
      this.handlers.onCallSignal = this.handlers.onCallSignal || [];
      this.handlers.onCallSignal.forEach((cb) => cb(payload.data || payload));
    }
  }
  disconnect() {
    this.stopPing();
    if (this.socket) {
      this.socket.close(1e3, "Logout pelo usuário");
      this.socket = null;
    }
  }
}
const socketClient = new FechatSocketClient();
window.socketClient = socketClient;
