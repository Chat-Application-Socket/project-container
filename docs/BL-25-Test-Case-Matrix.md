# BL-25 Test Case Execution Matrix

Source: `docs/Test Plan Details.docx`.

**Status rule:** Only mark a case Pass or Fail when its specific expected result has supporting evidence. Related automated tests alone do not prove every test-plan case passed.

| Test Case ID | Actual Result / Evidence | Status |
|---|---|---|
| UT-01A | Not yet recorded | Not Run |
| UT-01B | Not yet recorded | Not Run |
| UT-01C | Not yet recorded | Not Run |
| UT-02A | Automated test test_blank_and_whitespace_username_refused passed; blank and whitespace-only usernames were refused. | Pass |
| UT-02B | Automated test test_valid_connection_receives_ack passed; valid username connected and received acknowledgement. | Pass |
| UT-02C | Not yet recorded | Not Run |
| UT-03A | Automated test test_broadcast_reaches_same_room_only passed: a room1 recipient received one message and the room2 outsider received none. Test used two room1 users, not the plan’s three mock clients. | Pass |
| UT-03B | Not yet recorded | Not Run |
| UT-03C | Not yet recorded | Not Run |
| UT-04A | Automated test test_timestamp_is_server_generated_utc passed; a server-generated UTC timestamp was included. | Pass |
| UT-04B | Automated test test_timestamp_is_server_generated_utc passed; the supplied 1999 timestamp was replaced by the server timestamp. | Pass |
| UT-04C | Actual timestamp was 2026-10-28T12:00:00+00:00; the plan requires the format to end in Z. | Fail |
| UT-05A | Automated test test_validator_rejects_empty_string passed; empty string rejected with the expected message. | Pass |
| UT-05B | Automated test test_validator_rejects_whitespace_only passed for whitespace-only input. | Pass |
| UT-05C | Automated test test_validator_accepts_and_trims_normal_text passed; input '  hi ' was accepted and trimmed to 'hi'. | Pass |
| UT-06A | Automated test test_client_emits_join_room_and_server_adds_client passed; server membership and joined acknowledgement were verified. | Pass |
| UT-06B | Automated test test_invalid_and_over_30_char_room_rejected passed; empty and 31-character names were rejected with error E303. | Pass |
| UT-06C | Not yet recorded | Not Run |
| UT-07A | Automated test test_join_and_leave_notices_shown_to_room_members passed; existing member received Bob's join notice. | Pass |
| UT-07B | Automated test test_join_and_leave_notices_shown_to_room_members passed; existing member received Bob's leave notice. | Pass |
| UT-07C | Not yet recorded | Not Run |
| UT-08A | Not yet recorded | Not Run |
| UT-08B | Automated test test_disconnect_removes_user passed; disconnected user's entry is removed from connected-user tracking. Room-specific get_users behavior was not directly tested. | Pass |
| UT-08C | Not yet recorded | Not Run |
| UT-09A | Not yet recorded | Not Run |
| UT-09B | Not yet recorded | Not Run |
| UT-09C | Not yet recorded | Not Run |
| UT-10A | Automated test test_joining_new_room_leaves_old_room passed; switching rooms updates the user's tracked room and removes membership from the old room. | Pass |
| UT-10B | Not yet recorded | Not Run |
| UT-10C | Automated test test_joining_new_room_leaves_old_room passed; the user is tracked in room2 and no longer listed in room1 after switching. | Pass |
| IT-01A | One client connected; page showed Connected and server connection was observed. | Pass |
| IT-01B | Two browser tabs connected with distinct guest identities/connection IDs. | Pass |
| IT-01C | Not yet recorded | Not Run |
| IT-02A | Not yet recorded | Not Run |
| IT-02B | Automated test test_two_clients_two_entries_in_connected_users passed; two valid clients were registered separately. Invalid-client isolation was not tested by this case. | Not Run |
| IT-02C | Not yet recorded | Not Run |
| IT-03A | Not yet recorded | Not Run |
| IT-03B | Manual browser check: messages sent in Testing and Design appeared only in their respective rooms. | Pass |
| IT-03C | Not yet recorded | Not Run |
| IT-04A | Not yet recorded | Not Run |
| IT-04B | Not yet recorded | Not Run |
| IT-04C | Not yet recorded | Not Run |
| IT-05A | Not yet recorded | Not Run |
| IT-05B | Automated test test_server_rejects_blank_message_and_does_not_broadcast passed; blank messages were rejected and not broadcast. | Pass |
| IT-05C | Not yet recorded | Not Run |
| IT-06A | Not yet recorded | Not Run |
| IT-06B | Automated test test_messages_scoped_to_the_room passed; same-room recipient received the message and other-room recipient did not. Manual browser room-isolation check also passed. | Pass |
| IT-06C | Not yet recorded | Not Run |
| IT-07A | Not yet recorded | Not Run |
| IT-07B | Not yet recorded | Not Run |
| IT-07C | Automated test test_disconnect_fires_leave_notice_to_room passed; remaining member received Bob's leave notice after disconnect. | Pass |
| IT-08A | Not yet recorded | Not Run |
| IT-08B | Automated test test_leave_button_action passed; leaving removes Alice from room membership. Browser presence-list update was not verified. | Pass |
| IT-08C | Automated test test_disconnect_fires_leave_notice_to_room passed; remaining member receives a leave notice after disconnect. Browser presence-list update was not verified. | Pass |
| IT-09A | Not yet recorded | Not Run |
| IT-09B | Not yet recorded | Not Run |
| IT-09C | Not yet recorded | Not Run |
| IT-10A | Not yet recorded | Not Run |
| IT-10B | Not yet recorded | Not Run |
| IT-10C | Not yet recorded | Not Run |
| ST-01A | App connected successfully and allowed chat. | Pass |
| ST-01B | With the server stopped, the browser showed that the site could not be reached; expected page and Unable to connect to server message were not shown. | Fail |
| ST-02A | Not yet recorded | Not Run |
| ST-02B | Not yet recorded | Not Run |
| ST-03A | Not yet recorded | Not Run |
| ST-03B | Not yet recorded | Not Run |
| ST-04A | Not yet recorded | Not Run |
| ST-04B | Not yet recorded | Not Run |
| ST-05A | Not yet recorded | Not Run |
| ST-05B | Automated server-side test test_valid_message_after_blank_attempts_is_delivered passed; valid text was delivered after blank attempts. Browser UI behavior not verified. | Pass |
| ST-06A | Not yet recorded | Not Run |
| ST-06B | Not yet recorded | Not Run |
| ST-07A | Not yet recorded | Not Run |
| ST-07B | Not yet recorded | Not Run |
| ST-08A | Not yet recorded | Not Run |
| ST-08B | Not yet recorded | Not Run |
| ST-09A | Not yet recorded | Not Run |
| ST-09B | Not yet recorded | Not Run |
| ST-10A | Not yet recorded | Not Run |
| ST-10B | Not yet recorded | Not Run |
| NT-01 | Not yet recorded | Not Run |
| NT-02 | Not yet recorded | Not Run |
| NT-03 | Not yet recorded | Not Run |
| NT-04 | Not yet recorded | Not Run |
| NT-05 | Not yet recorded | Not Run |
| NT-06 | Not yet recorded | Not Run |
| NT-07 | Not yet recorded | Not Run |
| NT-08 | Not yet recorded | Not Run |
| NT-09 | Not yet recorded | Not Run |
| NT-10 | Not yet recorded | Not Run |
| NT-11 | Not yet recorded | Not Run |
| NT-12 | Not yet recorded | Not Run |
| NT-13 | Not yet recorded | Not Run |
| NT-14 | Not yet recorded | Not Run |
| NT-15 | Not yet recorded | Not Run |
| NT-16 | Not yet recorded | Not Run |
| NT-17 | Not yet recorded | Not Run |
| NT-18 | Not yet recorded | Not Run |
