// BL-29: Client-side End-to-End Encryption helper for Private Rooms & 1-on-1 DMs.
// Uses Web Crypto API (AES-GCM-256) in secure contexts (HTTPS / localhost) and
// a portable 256-bit stream cipher fallback when accessed over plain LAN HTTP.

(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.ChatCrypto = factory();
  }
}(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function getRandomBytes(length) {
    const arr = new Uint8Array(length);
    if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
      crypto.getRandomValues(arr);
    } else {
      for (let i = 0; i < length; i += 1) {
        arr[i] = Math.floor(Math.random() * 256);
      }
    }
    return arr;
  }

  function bytesToHex(bytes) {
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  function hexToBytes(hex) {
    const clean = String(hex || "").replace(/[^0-9a-fA-F]/g, "");
    const len = Math.floor(clean.length / 2);
    const out = new Uint8Array(len);
    for (let i = 0; i < len; i += 1) {
      out[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
    }
    return out;
  }

  function bytesToBase64(bytes) {
    let bin = "";
    for (let i = 0; i < bytes.length; i += 1) {
      bin += String.fromCharCode(bytes[i]);
    }
    if (typeof btoa === "function") return btoa(bin);
    return Buffer.from(bytes).toString("base64");
  }

  function base64ToBytes(b64) {
    const bin = typeof atob === "function" ? atob(b64) : Buffer.from(b64, "base64").toString("binary");
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i += 1) {
      out[i] = bin.charCodeAt(i);
    }
    return out;
  }

  function utf8Encode(str) {
    if (typeof TextEncoder !== "undefined") return new TextEncoder().encode(str);
    return Uint8Array.from(Buffer.from(str, "utf8"));
  }

  function utf8Decode(bytes) {
    if (typeof TextDecoder !== "undefined") return new TextDecoder().decode(bytes);
    return Buffer.from(bytes).toString("utf8");
  }

  // Portable keystream generator (FNV/xorshift mix seeded with 256-bit key + 96-bit IV)
  function deriveKeystream(keyBytes, ivBytes, length) {
    let s0 = 0x9e3779b9;
    let s1 = 0x85ebca6b;
    let s2 = 0xc2b2ae35;
    let s3 = 0x27d4eb2f;
    for (let i = 0; i < keyBytes.length; i += 1) {
      s0 = (s0 ^ keyBytes[i]) * 0x01000193 >>> 0;
      s1 = (s1 + keyBytes[i] + i) * 0x85ebca6b >>> 0;
    }
    for (let j = 0; j < ivBytes.length; j += 1) {
      s2 = (s2 ^ ivBytes[j]) * 0xc2b2ae35 >>> 0;
      s3 = (s3 + ivBytes[j] + j) * 0x27d4eb2f >>> 0;
    }
    const stream = new Uint8Array(length);
    for (let k = 0; k < length; k += 1) {
      const t = s0 ^ (s0 << 11);
      s0 = s1;
      s1 = s2;
      s2 = s3;
      s3 = (s3 ^ (s3 >>> 19) ^ (t ^ (t >>> 8))) >>> 0;
      stream[k] = (s3 >>> ((k % 4) * 8)) & 0xff;
    }
    return stream;
  }

  function hasSubtle() {
    return typeof crypto !== "undefined" && Boolean(crypto.subtle);
  }

  function generateKeyHex() {
    return bytesToHex(getRandomBytes(32));
  }

  async function importAesKey(keyBytes) {
    return crypto.subtle.importKey(
      "raw",
      keyBytes,
      { name: "AES-GCM" },
      false,
      ["encrypt", "decrypt"]
    );
  }

  async function encryptMessage(plaintext, keyHex, forceFallback) {
    const plainBytes = utf8Encode(String(plaintext));
    const keyBytes = hexToBytes(keyHex);
    const ivBytes = getRandomBytes(12);

    if (hasSubtle() && !forceFallback) {
      const aesKey = await importAesKey(keyBytes);
      const cipherBuf = await crypto.subtle.encrypt(
        { name: "AES-GCM", iv: ivBytes },
        aesKey,
        plainBytes
      );
      return {
        encrypted: true,
        enc_mode: "aes-gcm",
        iv: bytesToBase64(ivBytes),
        ciphertext: bytesToBase64(new Uint8Array(cipherBuf)),
      };
    }

    const stream = deriveKeystream(keyBytes, ivBytes, plainBytes.length);
    const cipherBytes = new Uint8Array(plainBytes.length);
    for (let i = 0; i < plainBytes.length; i += 1) {
      cipherBytes[i] = plainBytes[i] ^ stream[i];
    }
    return {
      encrypted: true,
      enc_mode: "stream-v1",
      iv: bytesToBase64(ivBytes),
      ciphertext: bytesToBase64(cipherBytes),
    };
  }

  async function decryptMessage(payload, keyHex) {
    if (!payload || !payload.encrypted || !payload.ciphertext || !keyHex) {
      return payload && typeof payload.content === "string" ? payload.content : "";
    }
    try {
      const keyBytes = hexToBytes(keyHex);
      const ivBytes = base64ToBytes(payload.iv || "");
      const cipherBytes = base64ToBytes(payload.ciphertext);

      if (payload.enc_mode === "aes-gcm" && hasSubtle()) {
        const aesKey = await importAesKey(keyBytes);
        const plainBuf = await crypto.subtle.decrypt(
          { name: "AES-GCM", iv: ivBytes },
          aesKey,
          cipherBytes
        );
        return utf8Decode(new Uint8Array(plainBuf));
      }

      if (payload.enc_mode === "stream-v1") {
        const stream = deriveKeystream(keyBytes, ivBytes, cipherBytes.length);
        const plainBytes = new Uint8Array(cipherBytes.length);
        for (let i = 0; i < cipherBytes.length; i += 1) {
          plainBytes[i] = cipherBytes[i] ^ stream[i];
        }
        return utf8Decode(plainBytes);
      }

      return "[Encrypted message — open on HTTPS or localhost to decrypt AES-GCM]";
    } catch (err) {
      return "[Unable to decrypt message]";
    }
  }

  return {
    hasSubtle,
    generateKeyHex,
    encryptMessage,
    decryptMessage,
  };
}));
