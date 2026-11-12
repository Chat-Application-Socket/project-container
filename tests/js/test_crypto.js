const assert = require("assert");
const ChatCrypto = require("../../static/crypto.js");

async function run() {
  const keyHex = ChatCrypto.generateKeyHex();
  assert.strictEqual(keyHex.length, 64, "256-bit key must be 64 hex chars");

  const secret = "Top secret private room message!";

  // 1. Test Web Crypto AES-GCM-256
  if (ChatCrypto.hasSubtle()) {
    const encAes = await ChatCrypto.encryptMessage(secret, keyHex, false);
    assert.strictEqual(encAes.encrypted, true);
    assert.strictEqual(encAes.enc_mode, "aes-gcm");
    assert.notStrictEqual(encAes.ciphertext, secret);
    const decAes = await ChatCrypto.decryptMessage(encAes, keyHex);
    assert.strictEqual(decAes, secret);

    const wrongKey = ChatCrypto.generateKeyHex();
    const badDec = await ChatCrypto.decryptMessage(encAes, wrongKey);
    assert.strictEqual(badDec, "[Unable to decrypt message]");
  }

  // 2. Test portable stream-v1 fallback cipher (used on plain LAN HTTP)
  const encStream = await ChatCrypto.encryptMessage(secret, keyHex, true);
  assert.strictEqual(encStream.encrypted, true);
  assert.strictEqual(encStream.enc_mode, "stream-v1");
  assert.notStrictEqual(encStream.ciphertext, secret);
  const decStream = await ChatCrypto.decryptMessage(encStream, keyHex);
  assert.strictEqual(decStream, secret);

  console.log("All ChatCrypto E2EE tests passed!");
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
