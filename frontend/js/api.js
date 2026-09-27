const FechatAPI = {
  getToken() {
    return localStorage.getItem("fechat_token");
  },
  setToken(token) {
    localStorage.setItem("fechat_token", token);
  },
  clearToken() {
    localStorage.removeItem("fechat_token");
    localStorage.removeItem("fechat_user");
  },
  async fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = (err) => reject(err);
      reader.readAsDataURL(file);
    });
  },
  async initShieldHandshake() {
    return true;
  },
  async register(fullName, username, email, password) {
    const res = await socketClient.callRpc("auth_register", {
      full_name: fullName,
      username: username,
      email: email,
      password: password,
      language: currentLang,
    });
    if (res.access_token) {
      this.setToken(res.access_token);
      socketClient.connect(res.access_token);
    }
    return res;
  },
  async login(loginIdentifier, password) {
    const res = await socketClient.callRpc("auth_login", {
      login: loginIdentifier,
      identifier: loginIdentifier,
      password: password,
    });
    if (res.access_token) {
      this.setToken(res.access_token);
      socketClient.connect(res.access_token);
    }
    return res;
  },
  async getMe() {
    const res = await socketClient.callRpc("auth_me");
    return res.user;
  },
  async uploadAvatar(file) {
    const base64Data = await this.fileToBase64(file);
    const res = await socketClient.callRpc("auth_upload_avatar", {
      avatar_base64: base64Data,
      filename: file.name,
    });
    return res;
  },
  async searchUsers(query) {
    const res = await socketClient.callRpc("search_users", { query: query });
    return res.users || [];
  },
  async updateProfile(profileData) {
    const res = await socketClient.callRpc("update_profile", profileData);
    return res.user;
  },
  async getContacts() {
    const res = await socketClient.callRpc("get_contacts");
    return res.contacts || [];
  },
  async addContact(identifier, nickname = null) {
    const res = await socketClient.callRpc("add_contact", {
      identifier: identifier,
      nickname: nickname,
    });
    return res.contact;
  },
  async toggleBlockContact(contactId) {
    const res = await socketClient.callRpc("toggle_block_contact", {
      contact_id: contactId,
    });
    return res;
  },
  async getBlockStatus(targetUserId) {
    const res = await socketClient.callRpc("get_block_status", {
      user_id: targetUserId,
    });
    return res;
  },
  async blockUser(targetUserId) {
    const res = await socketClient.callRpc("block_user", {
      user_id: targetUserId,
    });
    return res;
  },
  async unblockUser(targetUserId) {
    const res = await socketClient.callRpc("unblock_user", {
      user_id: targetUserId,
    });
    return res;
  },
  async getChats() {
    const res = await socketClient.callRpc("get_chats");
    return res.chats || [];
  },
  async togglePinChat(chatId) {
    const res = await socketClient.callRpc("toggle_pin_chat", {
      chat_id: chatId,
    });
    return res;
  },
  async toggleMuteChat(chatId) {
    const res = await socketClient.callRpc("toggle_mute_chat", {
      chat_id: chatId,
    });
    return res;
  },
  async toggleArchiveChat(chatId) {
    const res = await socketClient.callRpc("toggle_archive_chat", {
      chat_id: chatId,
    });
    return res;
  },
  async deleteChat(chatId) {
    const res = await socketClient.callRpc("delete_chat", { chat_id: chatId });
    return res;
  },
  async exportChatData(chatId) {
    const res = await socketClient.callRpc("export_chat_data", {
      chat_id: chatId,
    });
    return res;
  },
  async createDirectChat(targetUserId) {
    const res = await socketClient.callRpc("create_direct_chat", {
      target_user_id: targetUserId,
    });
    return res.chat;
  },
  async createGroupChat(title, description = null, memberUserIds = []) {
    const res = await socketClient.callRpc("create_group_chat", {
      title: title,
      description: description,
      member_user_ids: memberUserIds,
    });
    return res.chat;
  },
  async getMessages(chatId, limit = 50, offset = 0) {
    const res = await socketClient.callRpc("get_messages", {
      chat_id: chatId,
      limit: limit,
      offset: offset,
    });
    return res.messages || [];
  },
  async sendMessage(
    chatId,
    ciphertextOrEncObj,
    iv = null,
    tag = null,
    messageType = "text",
    mediaUrl = null,
    mediaName = null,
    mediaSize = null,
    frankingTag = null,
    replyToId = null,
    replyToSender = null,
    replyToSnippet = null,
  ) {
    let payload = { chat_id: chatId };
    if (typeof ciphertextOrEncObj === "object" && ciphertextOrEncObj !== null) {
      payload.ciphertext = ciphertextOrEncObj.ciphertext;
      payload.iv = ciphertextOrEncObj.iv;
      payload.tag = ciphertextOrEncObj.tag;
      if (typeof iv === "string" && iv !== "[object Object]") {
        payload.message_type = iv;
        payload.media_url = tag || ciphertextOrEncObj.media_url || null;
        payload.media_name =
          messageType !== "text"
            ? messageType
            : ciphertextOrEncObj.media_name || null;
        payload.media_size = mediaUrl || ciphertextOrEncObj.media_size || null;
        payload.franking_tag =
          mediaName || ciphertextOrEncObj.franking_tag || null;
        payload.reply_to_message_id =
          ciphertextOrEncObj.reply_to_message_id || replyToId || null;
        payload.reply_to_sender_name =
          ciphertextOrEncObj.reply_to_sender_name || replyToSender || null;
        payload.reply_to_snippet =
          ciphertextOrEncObj.reply_to_snippet || replyToSnippet || null;
      } else {
        payload.message_type =
          ciphertextOrEncObj.message_type || messageType || "text";
        payload.media_url = ciphertextOrEncObj.media_url || mediaUrl || null;
        payload.media_name = ciphertextOrEncObj.media_name || mediaName || null;
        payload.media_size = ciphertextOrEncObj.media_size || mediaSize || null;
        payload.franking_tag =
          ciphertextOrEncObj.franking_tag || frankingTag || null;
        payload.reply_to_message_id =
          ciphertextOrEncObj.reply_to_message_id || replyToId || null;
        payload.reply_to_sender_name =
          ciphertextOrEncObj.reply_to_sender_name || replyToSender || null;
        payload.reply_to_snippet =
          ciphertextOrEncObj.reply_to_snippet || replyToSnippet || null;
      }
    } else {
      payload.ciphertext = ciphertextOrEncObj;
      payload.iv = iv;
      payload.tag = tag;
      payload.message_type = messageType || "text";
      payload.media_url = mediaUrl;
      payload.media_name = mediaName;
      payload.media_size = mediaSize;
      payload.franking_tag = frankingTag;
      payload.reply_to_message_id = replyToId;
      payload.reply_to_sender_name = replyToSender;
      payload.reply_to_snippet = replyToSnippet;
    }
    const res = await socketClient.callRpc("send_message", payload);
    return res.message;
  },
  async getGroupDetails(chatId) {
    const res = await socketClient.callRpc("get_group_details", {
      chat_id: chatId,
    });
    return res.group;
  },
  async updateGroupInfo(chatId, data) {
    const res = await socketClient.callRpc("update_group_info", {
      chat_id: chatId,
      ...data,
    });
    return res;
  },
  async addGroupMembers(chatId, userIds) {
    const res = await socketClient.callRpc("add_group_members", {
      chat_id: chatId,
      user_ids: userIds,
    });
    return res;
  },
  async removeGroupMember(chatId, userId) {
    const res = await socketClient.callRpc("remove_group_member", {
      chat_id: chatId,
      user_id: userId,
    });
    return res;
  },
  async changeGroupMemberRole(chatId, userId, role) {
    const res = await socketClient.callRpc("change_group_member_role", {
      chat_id: chatId,
      user_id: userId,
      role: role,
    });
    return res;
  },
  async pinGroupMessage(chatId, messageId) {
    const res = await socketClient.callRpc("pin_group_message", {
      chat_id: chatId,
      message_id: messageId,
    });
    return res;
  },
  async deleteMessageForEveryone(messageId) {
    const res = await socketClient.callRpc("delete_message_for_everyone", {
      message_id: messageId,
    });
    return res;
  },
  async getGroupInviteLink(chatId) {
    const res = await socketClient.callRpc("get_group_invite_link", {
      chat_id: chatId,
    });
    return res;
  },
  async revokeGroupInviteLink(chatId) {
    const res = await socketClient.callRpc("revoke_group_invite_link", {
      chat_id: chatId,
    });
    return res;
  },
  async getGroupPreviewByInvite(inviteCode) {
    const res = await socketClient.callRpc("get_group_preview_by_invite", {
      invite_code: inviteCode,
    });
    return res.group_preview;
  },
  async joinGroupViaInvite(inviteCode) {
    const res = await socketClient.callRpc("join_group_via_invite", {
      invite_code: inviteCode,
    });
    return res;
  },
  fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = (error) => reject(error);
      reader.readAsDataURL(file);
    });
  },
  async uploadChatMedia(file) {
    const base64Data = await this.fileToBase64(file);
    const res = await socketClient.callRpc("upload_chat_media", {
      data_base64: base64Data,
      filename: file.name || `audio_${Date.now()}.webm`,
    });
    return res;
  },
  async markAsRead(chatId) {
    const res = await socketClient.callRpc("mark_read", { chat_id: chatId });
    return res;
  },
  async markChatRead(chatId) {
    return this.markAsRead(chatId);
  },
  async submitReport(
    arg1,
    reason = null,
    plaintextEvidence = null,
    frankingTag = null,
    reportedUserId = null,
    reportedChatId = null,
  ) {
    let payload = {};
    if (typeof arg1 === "object" && arg1 !== null) {
      payload = {
        category: arg1.category || "other",
        reason:
          arg1.reason || "Denúncia submetida pelo usuário via canal seguro",
        plaintext_evidence: arg1.plaintext_evidence || null,
        franking_tag: arg1.franking_tag || null,
        reported_user_id: arg1.reported_user_id || null,
        reported_chat_id: arg1.chat_id || arg1.reported_chat_id || null,
        message_id: arg1.message_id || null,
      };
    } else {
      payload = {
        category: arg1 || "other",
        reason: reason || "Denúncia submetida pelo usuário via canal seguro",
        plaintext_evidence: plaintextEvidence || null,
        franking_tag: frankingTag || null,
        reported_user_id: reportedUserId || null,
        reported_chat_id: reportedChatId || null,
      };
    }
    const res = await socketClient.callRpc("submit_report", payload);
    return res;
  },
  async getAbuseReports() {
    const res = await socketClient.callRpc("get_abuse_reports");
    return res.reports || [];
  },
  async registerJudicialOrder(
    courtOrderNumber,
    issuingCourt,
    officerBadge,
    targetIdentifier,
    actionType,
    notes = "",
  ) {
    const res = await socketClient.callRpc("register_judicial_order", {
      court_order_number: courtOrderNumber,
      issuing_court: issuingCourt,
      officer_badge: officerBadge,
      target_identifier: targetIdentifier,
      action_type: actionType,
      notes: notes,
    });
    return res;
  },
  async getJudicialAudits() {
    const res = await socketClient.callRpc("get_judicial_audits");
    return res.audits || [];
  },
  async getJudicialAuditLogs() {
    return this.getJudicialAudits();
  },
  async suspendUser(targetUserId, reason = "") {
    const res = await socketClient.callRpc("suspend_user", {
      user_id: targetUserId,
      reason: reason,
    });
    return res;
  },
  async unsuspendUser(targetUserId) {
    const res = await socketClient.callRpc("unsuspend_user", {
      user_id: targetUserId,
    });
    return res;
  },
  async getJudicialUsersList(query = "") {
    const res = await socketClient.callRpc("get_judicial_users_list", {
      query: query,
    });
    return res.users || [];
  },
  async getJudicialUserDossier(userId) {
    const res = await socketClient.callRpc("get_judicial_user_dossier", {
      user_id: userId,
    });
    return res;
  },
  async getJudicialChatMessages(chatId, limit = 200) {
    const res = await socketClient.callRpc("get_judicial_chat_messages", {
      chat_id: chatId,
      limit: limit,
    });
    return res;
  },
  async exportJudicialDossier(
    userId,
    courtOrderNumber,
    issuingCourt,
    officerBadge,
    reason,
  ) {
    const res = await socketClient.callRpc("export_judicial_dossier", {
      user_id: userId,
      court_order_number: courtOrderNumber,
      issuing_court: issuingCourt,
      officer_badge: officerBadge,
      reason: reason,
    });
    return res;
  },
  async sendJudicialNotice(userId, title, body, category = "judicial_notice") {
    const res = await socketClient.callRpc("send_judicial_notice", {
      user_id: userId,
      title: title,
      body: body,
      category: category,
    });
    return res;
  },
  async sendCallSignal(payload) {
    const res = await socketClient.callRpc("call_signal", payload);
    return res;
  },
};
window.FechatAPI = FechatAPI;
