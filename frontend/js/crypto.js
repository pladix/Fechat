const FechatCrypto = {
  keyCache: new Map(),
  sha256Cache: new Map(),
  wireKeyHex: null,
  bufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
  },
  base64ToBuffer(base64) {
    const binary = window.atob(base64);
    const len = binary.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  },
  hexToBuffer(hex) {
    const len = hex.length;
    const bytes = new Uint8Array(len / 2);
    for (let i = 0; i < len; i += 2) {
      bytes[i / 2] = parseInt(hex.substr(i, 2), 16);
    }
    return bytes.buffer;
  },
  async importKey(hexKey) {
    if (this.keyCache.has(hexKey)) {
      return this.keyCache.get(hexKey);
    }
    const rawKey = this.hexToBuffer(hexKey);
    const cryptoKey = await window.crypto.subtle.importKey(
      "raw",
      rawKey,
      { name: "AES-GCM" },
      false,
      ["encrypt", "decrypt"],
    );
    this.keyCache.set(hexKey, cryptoKey);
    return cryptoKey;
  },
  async encrypt(plaintext, hexKey) {
    try {
      const cryptoKey = await this.importKey(hexKey);
      const iv = window.crypto.getRandomValues(new Uint8Array(12));
      const encodedText = new TextEncoder().encode(plaintext);
      const encryptedBuffer = await window.crypto.subtle.encrypt(
        { name: "AES-GCM", iv: iv, tagLength: 128 },
        cryptoKey,
        encodedText,
      );
      const encryptedBytes = new Uint8Array(encryptedBuffer);
      const ciphertextPart = encryptedBytes.slice(
        0,
        encryptedBytes.length - 16,
      );
      const tagPart = encryptedBytes.slice(encryptedBytes.length - 16);
      return {
        ciphertext: this.bufferToBase64(ciphertextPart),
        iv: this.bufferToBase64(iv),
        tag: this.bufferToBase64(tagPart),
      };
    } catch (e) {
      console.error("Erro ao criptografar com AES-256-GCM:", e);
      throw e;
    }
  },
  async decrypt(ciphertextB64, ivB64, tagB64, hexKey, throwOnError = false) {
    try {
      const cryptoKey = await this.importKey(hexKey);
      const ciphertextBuf = new Uint8Array(this.base64ToBuffer(ciphertextB64));
      const ivBuf = new Uint8Array(this.base64ToBuffer(ivB64));
      const tagBuf = new Uint8Array(this.base64ToBuffer(tagB64));
      const combined = new Uint8Array(ciphertextBuf.length + tagBuf.length);
      combined.set(ciphertextBuf, 0);
      combined.set(tagBuf, ciphertextBuf.length);
      const decryptedBuffer = await window.crypto.subtle.decrypt(
        { name: "AES-GCM", iv: ivBuf, tagLength: 128 },
        cryptoKey,
        combined,
      );
      return new TextDecoder().decode(decryptedBuffer);
    } catch (e) {
      if (throwOnError) {
        throw e;
      }
      return "[🔒 Mensagem criptografada - Chave protegida]";
    }
  },
  async derivePreauthWireKey() {
    return await this.sha256("fechat_preauth_wire_shield_2026");
  },
  async deriveSessionWireKey(token) {
    if (!token) return await this.derivePreauthWireKey();
    return await this.sha256("fechat_wsep_tunnel_v1_salt_2026" + token);
  },
  setWireKeyHex(keyHex) {
    this.wireKeyHex = keyHex;
  },
  async sealWirePacket(payload, customKeyHex = null) {
    const key =
      customKeyHex || this.wireKeyHex || (await this.derivePreauthWireKey());
    const jsonStr = JSON.stringify(payload);
    const enc = await this.encrypt(jsonStr, key);
    return { _shield: "aes256gcm", c: enc.ciphertext, iv: enc.iv, t: enc.tag };
  },
  async unsealWirePacket(packet, customKeyHex = null) {
    if (
      !packet ||
      typeof packet !== "object" ||
      packet._shield !== "aes256gcm"
    ) {
      return packet;
    }
    const keysToTry = [];
    if (customKeyHex) keysToTry.push(customKeyHex);
    if (this.wireKeyHex && !keysToTry.includes(this.wireKeyHex))
      keysToTry.push(this.wireKeyHex);
    const preauthKey = await this.derivePreauthWireKey();
    if (!keysToTry.includes(preauthKey)) keysToTry.push(preauthKey);
    for (const k of keysToTry) {
      try {
        const decJson = await this.decrypt(
          packet.c,
          packet.iv,
          packet.t,
          k,
          true,
        );
        return JSON.parse(decJson);
      } catch (_) {}
    }
    return packet;
  },
  async sha256(text) {
    if (this.sha256Cache.has(text)) {
      return this.sha256Cache.get(text);
    }
    const msgBuffer = new TextEncoder().encode(text);
    const hashBuffer = await crypto.subtle.digest("SHA-256", msgBuffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hex = hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
    this.sha256Cache.set(text, hex);
    return hex;
  },
};
