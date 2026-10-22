// Message view model for the chat page (SAD component C3: Message View Model).
//
// BL-08: Render received messages live, in order, without page refresh.
//
// Keeps the list of received messages in the right order so the UI can insert
// each new message at the correct position:
// - Messages are kept in the order they arrive (REQ-12 / Test Plan REQ-12).
// - If the server includes a per-room sequence number `seq` (SAD ADR-3), that
//   number decides the order, so a late packet still lands in the right place.
// - A message whose `id` was already seen is ignored, so a duplicate delivery
//   never shows twice.
//
// This file has no DOM code so it can be unit tested with Node.js
// (tests/js/test_message_store.js) and used in the browser as window.MessageStore.

(function (root) {
  "use strict";

  function hasSeq(msg) {
    return typeof msg.seq === "number" && isFinite(msg.seq);
  }

  function MessageStore() {
    this.messages = [];
    this.seenIds = new Set();
  }

  // Add a received message.
  // Returns the index where it was inserted, or -1 if it was ignored
  // (not an object, or a duplicate id).
  MessageStore.prototype.add = function (msg) {
    if (!msg || typeof msg !== "object") return -1;

    if (msg.id !== undefined && msg.id !== null) {
      const key = String(msg.id);
      if (this.seenIds.has(key)) return -1;
      this.seenIds.add(key);
    }

    // Default: arrival order (append). With seq, walk back past any message
    // that has a larger seq so the list stays sorted by seq.
    let index = this.messages.length;
    if (hasSeq(msg)) {
      while (index > 0) {
        const previous = this.messages[index - 1];
        if (hasSeq(previous) && previous.seq > msg.seq) {
          index -= 1;
        } else {
          break;
        }
      }
    }

    this.messages.splice(index, 0, msg);
    return index;
  };

  // Messages in display order (a copy, so callers cannot reorder the store)
  MessageStore.prototype.getOrdered = function () {
    return this.messages.slice();
  };

  MessageStore.prototype.size = function () {
    return this.messages.length;
  };

  // Forget every message (used when the user connects again with a new session)
  MessageStore.prototype.clear = function () {
    this.messages = [];
    this.seenIds.clear();
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { MessageStore: MessageStore };
  } else {
    root.MessageStore = MessageStore;
  }
})(typeof window !== "undefined" ? window : this);
