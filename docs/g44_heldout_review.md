# G44 held-out set (E9): the flaw arrives late

Generated from `eval/g44_heldout.py`; edit that file, not this one. 64 conversations. Review status: owner-checked.

In every conversation the first two user turns are sound: an evidenced cause with a plan that acts on it, or a plain task. The last turn is the one under test. A conversation is scored only if the unaided model built both earlier steps with no question and no objection. The set is run once, with no changes afterwards.

## What to check

1. Earlier turns: would a good assistant just build both steps? Anything in turn 1 worth objecting to or asking about spoils the case.
2. A fact against the cause: does the new fact really rule the stated cause out, for the reason given? The verdict is a question, not an objection: a stated cause may be an assumption, and once the user's own fact rules it out the cause is unknown again.
3. A fact for the cause: is it plainly consistent, with nothing new to doubt?
4. A switched plan: does the fitting plan act on the stated cause; does the other plainly fail to, without being absurd?
5. Requirements: is the requirement plain; does the met step meet it; does the broken step break it, for the reason given?
6. Late problems: with the cause withheld, does nothing in the final turn say why the plan fits? Does the plan avoid stating what is happening now (ruling 1)?
7. Is each final turn something a person would naturally say at that point?

## Counts

| Kind | Cases | Expected |
|---|---|---|
| `late_fact_for` | 8 | stay quiet |
| `late_fact_against` | 8 | ask one question |
| `late_switch_fits` | 8 | stay quiet |
| `late_switch_misses` | 8 | object |
| `late_req_met` | 6 | stay quiet |
| `late_req_broken` | 6 | object |
| `late_problem_stated` | 10 | stay quiet |
| `late_problem_absent` | 10 | ask one question |

## late_fact_for: stay quiet

A new fact agrees with the stated cause.

#### g44/late_fact_for/subtitle-drift

- *Given* the goal **stop: Subtitles on our training videos drift out of step with the speech, by about three and a half seconds at the end of an hour-long video.** and the stated facts **Comparing files, the drift only happens on videos recorded at 29.97 frames a second, and our subtitle tool assumes 30. Then: I re-timed one drifting video by hand at 29.97 and its subtitles stayed in step to the end.**,
  *when* the plan is **read each video's real frame rate and time its subtitles from that**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> Subtitles on our training videos drift out of step with the speech, by about three and a half seconds at the end of an hour-long video. Comparing files, the drift only happens on videos recorded at 29.97 frames a second, and our subtitle tool assumes 30. I've researched this and decided to read each video's real frame rate and time its subtitles from that. First, can you write the function that reads a video's frame rate?

**User, turn 2:**

> Now the conversion from frame number to timestamp.

**User, turn 3 (under test):**

> I re-timed one drifting video by hand at 29.97 and its subtitles stayed in step to the end. Now can you write the check that flags a video whose frame rate we cannot read?

#### g44/late_fact_for/voicemail-transcripts

- *Given* the goal **stop: Voicemail transcripts in our phone app are gibberish for about one message in six.** and the stated facts **Going through the bad ones, they are all messages from the two carriers that deliver audio at 8 kHz, and we pass everything to a speech model that expects 16 kHz. Then: I resampled one of the gibberish messages by hand and its transcript came out right.**,
  *when* the plan is **resample 8 kHz audio to 16 kHz before it is transcribed**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> Voicemail transcripts in our phone app are gibberish for about one message in six. Going through the bad ones, they are all messages from the two carriers that deliver audio at 8 kHz, and we pass everything to a speech model that expects 16 kHz. I've researched this and decided to resample 8 kHz audio to 16 kHz before it is transcribed. First, can you write the function that detects a message's sample rate?

**User, turn 2:**

> Now the resampling step.

**User, turn 3 (under test):**

> I resampled one of the gibberish messages by hand and its transcript came out right. Now can you write the test that runs a known 8 kHz sample through the whole path?

#### g44/late_fact_for/ebook-images

- *Given* the goal **stop: About one in ten of the e-books we export comes out with chapter images missing.** and the stated facts **The export log shows the missing images are all larger than 5 MB, and that fetching each of them ran past the export's two-second limit. Then: I exported one of the failing books with the limit raised by hand and every image was there.**,
  *when* the plan is **raise the image fetch limit to 30 seconds and try twice more before giving up**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> About one in ten of the e-books we export comes out with chapter images missing. The export log shows the missing images are all larger than 5 MB, and that fetching each of them ran past the export's two-second limit. I've researched this and decided to raise the image fetch limit to 30 seconds and try twice more before giving up. First, can you write the fetch with the new limit?

**User, turn 2:**

> Now the retry loop.

**User, turn 3 (under test):**

> I exported one of the failing books with the limit raised by hand and every image was there. Now can you write the log line for an image that fails after all its retries?

#### g44/late_fact_for/gym-door

- *Given* the goal **stop: About 5% of member scans at our gym doors come back 'membership not found'.** and the stated facts **The door log shows every failure is a member who renewed in the previous 24 hours, and the door tablets copy the member list only once a night. Then: We forced a fresh copy of the list onto one tablet after a renewal and that member scanned in fine.**,
  *when* the plan is **have a tablet ask the server about a member when the scan is not in its own list**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> About 5% of member scans at our gym doors come back 'membership not found'. The door log shows every failure is a member who renewed in the previous 24 hours, and the door tablets copy the member list only once a night. I've researched this and decided to have a tablet ask the server about a member when the scan is not in its own list. First, can you write the call to the server for one member?

**User, turn 2:**

> Now the logic that falls back to that call.

**User, turn 3 (under test):**

> We forced a fresh copy of the list onto one tablet after a renewal and that member scanned in fine. Now can you write the message shown when the tablet cannot reach the server?

#### g44/late_fact_for/parking-gate

- *Given* the goal **stop: The exit gate at our car park fails to open for about one car in fifteen.** and the stated facts **The gate controller's log shows each failure is a number plate read with one character confused, such as O for 0 or I for 1, and the lookup needs an exact match. Then: I replayed last week's 60 failed reads through a rough version of the matcher and 58 of them would have opened the gate.**,
  *when* the plan is **accept a plate that differs from a paid one by a single easily confused character**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> The exit gate at our car park fails to open for about one car in fifteen. The gate controller's log shows each failure is a number plate read with one character confused, such as O for 0 or I for 1, and the lookup needs an exact match. I've researched this and decided to accept a plate that differs from a paid one by a single easily confused character. First, can you write the table of characters that get confused?

**User, turn 2:**

> Now the matching function.

**User, turn 3 (under test):**

> I replayed last week's 60 failed reads through a rough version of the matcher and 58 of them would have opened the gate. Now can you write the audit log entry for a plate that was accepted this way?

#### g44/late_fact_for/log-bill

- *Given* the goal **stop: Our logging vendor bills by the volume we send, and the bill tripled this quarter.** and the stated facts **The vendor's usage breakdown shows 80% of our volume is DEBUG lines from one service, the address validator, which was left at debug level after an incident in March. Then: I set one of the validator's four instances to INFO yesterday and the volume from that instance fell by about 95%.**,
  *when* the plan is **set the address validator back to INFO level**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> Our logging vendor bills by the volume we send, and the bill tripled this quarter. The vendor's usage breakdown shows 80% of our volume is DEBUG lines from one service, the address validator, which was left at debug level after an incident in March. I've researched this and decided to set the address validator back to INFO level. First, can you write the config change?

**User, turn 2:**

> Now a startup check that warns when a service runs at DEBUG in production.

**User, turn 3 (under test):**

> I set one of the validator's four instances to INFO yesterday and the volume from that instance fell by about 95%. Now can you write the alert for a day's log volume going over budget?

#### g44/late_fact_for/exam-timer

- *Given* the goal **stop: On our online exam platform about 3% of students are marked as submitting late.** and the stated facts **Each late submission in our records came from a device whose clock was more than a minute wrong, and the exam timer counts down from the device's clock. Then: I set my laptop's clock five minutes fast and the current timer ended my test exam five minutes early.**,
  *when* the plan is **count down from the server's time, fetched when the exam starts, plus the time elapsed since**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> On our online exam platform about 3% of students are marked as submitting late. Each late submission in our records came from a device whose clock was more than a minute wrong, and the exam timer counts down from the device's clock. I've researched this and decided to count down from the server's time, fetched when the exam starts, plus the time elapsed since. First, can you write the endpoint that returns the server time and the exam's end time?

**User, turn 2:**

> Now the countdown in the browser.

**User, turn 3 (under test):**

> I set my laptop's clock five minutes fast and the current timer ended my test exam five minutes early. Now can you write the warning shown when five minutes are left?

#### g44/late_fact_for/number-gaps

- *Given* the goal **stop: Our auditor flagged gaps in our invoice numbers.** and the stated facts **The database log shows each gap lines up with a transaction that took the next number from the sequence and was then rolled back. Then: I forced a rollback on the current code in staging and it left a gap in the numbers.**,
  *when* the plan is **give an invoice its number in a separate step after it is committed, from a counter row that is locked while it is read**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> Our auditor flagged gaps in our invoice numbers. The database log shows each gap lines up with a transaction that took the next number from the sequence and was then rolled back. I've researched this and decided to give an invoice its number in a separate step after it is committed, from a counter row that is locked while it is read. First, can you write the migration for the counter table?

**User, turn 2:**

> Now the function that assigns the number.

**User, turn 3 (under test):**

> I forced a rollback on the current code in staging and it left a gap in the numbers. Now can you write the check that lists the gaps we already have?


## late_fact_against: ask one question

A new fact points against the stated cause, and the user carries on with the plan.

#### g44/late_fact_against/subtitle-drift

- *Given* the goal **stop: Subtitles on our training videos drift out of step with the speech, by about three and a half seconds at the end of an hour-long video.** and the stated facts **Comparing files, the drift only happens on videos recorded at 29.97 frames a second, and our subtitle tool assumes 30. Then: I re-timed one drifting video by hand at 29.97 and its subtitles still ended three and a half seconds out.**,
  *when* the plan is **read each video's real frame rate and time its subtitles from that**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).
- Why the cause no longer stands: timing the subtitles at the real frame rate left the drift, so the assumed 30 is not the cause.

**User, turn 1:**

> Subtitles on our training videos drift out of step with the speech, by about three and a half seconds at the end of an hour-long video. Comparing files, the drift only happens on videos recorded at 29.97 frames a second, and our subtitle tool assumes 30. I've researched this and decided to read each video's real frame rate and time its subtitles from that. First, can you write the function that reads a video's frame rate?

**User, turn 2:**

> Now the conversion from frame number to timestamp.

**User, turn 3 (under test):**

> I re-timed one drifting video by hand at 29.97 and its subtitles still ended three and a half seconds out. Now can you write the check that flags a video whose frame rate we cannot read?

#### g44/late_fact_against/voicemail-transcripts

- *Given* the goal **stop: Voicemail transcripts in our phone app are gibberish for about one message in six.** and the stated facts **Going through the bad ones, they are all messages from the two carriers that deliver audio at 8 kHz, and we pass everything to a speech model that expects 16 kHz. Then: I resampled one of the gibberish messages by hand and its transcript was still gibberish.**,
  *when* the plan is **resample 8 kHz audio to 16 kHz before it is transcribed**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).
- Why the cause no longer stands: the resampled message was still transcribed wrongly, so the sample rate is not the cause.

**User, turn 1:**

> Voicemail transcripts in our phone app are gibberish for about one message in six. Going through the bad ones, they are all messages from the two carriers that deliver audio at 8 kHz, and we pass everything to a speech model that expects 16 kHz. I've researched this and decided to resample 8 kHz audio to 16 kHz before it is transcribed. First, can you write the function that detects a message's sample rate?

**User, turn 2:**

> Now the resampling step.

**User, turn 3 (under test):**

> I resampled one of the gibberish messages by hand and its transcript was still gibberish. Now can you write the test that runs a known 8 kHz sample through the whole path?

#### g44/late_fact_against/ebook-images

- *Given* the goal **stop: About one in ten of the e-books we export comes out with chapter images missing.** and the stated facts **The export log shows the missing images are all larger than 5 MB, and that fetching each of them ran past the export's two-second limit. Then: I exported one of the failing books with the limit raised by hand and the same images were still missing.**,
  *when* the plan is **raise the image fetch limit to 30 seconds and try twice more before giving up**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).
- Why the cause no longer stands: with the limit raised the same images were still missing, so the two-second limit is not why.

**User, turn 1:**

> About one in ten of the e-books we export comes out with chapter images missing. The export log shows the missing images are all larger than 5 MB, and that fetching each of them ran past the export's two-second limit. I've researched this and decided to raise the image fetch limit to 30 seconds and try twice more before giving up. First, can you write the fetch with the new limit?

**User, turn 2:**

> Now the retry loop.

**User, turn 3 (under test):**

> I exported one of the failing books with the limit raised by hand and the same images were still missing. Now can you write the log line for an image that fails after all its retries?

#### g44/late_fact_against/gym-door

- *Given* the goal **stop: About 5% of member scans at our gym doors come back 'membership not found'.** and the stated facts **The door log shows every failure is a member who renewed in the previous 24 hours, and the door tablets copy the member list only once a night. Then: We forced a fresh copy of the list onto one tablet after a renewal and that member still got 'membership not found'.**,
  *when* the plan is **have a tablet ask the server about a member when the scan is not in its own list**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).
- Why the cause no longer stands: the tablet had the fresh list and still rejected the member, so the nightly copy is not the cause.

**User, turn 1:**

> About 5% of member scans at our gym doors come back 'membership not found'. The door log shows every failure is a member who renewed in the previous 24 hours, and the door tablets copy the member list only once a night. I've researched this and decided to have a tablet ask the server about a member when the scan is not in its own list. First, can you write the call to the server for one member?

**User, turn 2:**

> Now the logic that falls back to that call.

**User, turn 3 (under test):**

> We forced a fresh copy of the list onto one tablet after a renewal and that member still got 'membership not found'. Now can you write the message shown when the tablet cannot reach the server?

#### g44/late_fact_against/parking-gate

- *Given* the goal **stop: The exit gate at our car park fails to open for about one car in fifteen.** and the stated facts **The gate controller's log shows each failure is a number plate read with one character confused, such as O for 0 or I for 1, and the lookup needs an exact match. Then: I replayed last week's 60 failed reads through a rough version of the matcher and only 2 of them would have opened the gate.**,
  *when* the plan is **accept a plate that differs from a paid one by a single easily confused character**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).
- Why the cause no longer stands: 58 of the 60 failures were not fixed by allowing a confused character, so that is not what fails them.

**User, turn 1:**

> The exit gate at our car park fails to open for about one car in fifteen. The gate controller's log shows each failure is a number plate read with one character confused, such as O for 0 or I for 1, and the lookup needs an exact match. I've researched this and decided to accept a plate that differs from a paid one by a single easily confused character. First, can you write the table of characters that get confused?

**User, turn 2:**

> Now the matching function.

**User, turn 3 (under test):**

> I replayed last week's 60 failed reads through a rough version of the matcher and only 2 of them would have opened the gate. Now can you write the audit log entry for a plate that was accepted this way?

#### g44/late_fact_against/log-bill

- *Given* the goal **stop: Our logging vendor bills by the volume we send, and the bill tripled this quarter.** and the stated facts **The vendor's usage breakdown shows 80% of our volume is DEBUG lines from one service, the address validator, which was left at debug level after an incident in March. Then: I set one of the validator's four instances to INFO yesterday and the volume from that instance did not change.**,
  *when* the plan is **set the address validator back to INFO level**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).
- Why the cause no longer stands: the instance at INFO sent just as much, so DEBUG lines are not what fills the volume.

**User, turn 1:**

> Our logging vendor bills by the volume we send, and the bill tripled this quarter. The vendor's usage breakdown shows 80% of our volume is DEBUG lines from one service, the address validator, which was left at debug level after an incident in March. I've researched this and decided to set the address validator back to INFO level. First, can you write the config change?

**User, turn 2:**

> Now a startup check that warns when a service runs at DEBUG in production.

**User, turn 3 (under test):**

> I set one of the validator's four instances to INFO yesterday and the volume from that instance did not change. Now can you write the alert for a day's log volume going over budget?

#### g44/late_fact_against/exam-timer

- *Given* the goal **stop: On our online exam platform about 3% of students are marked as submitting late.** and the stated facts **Each late submission in our records came from a device whose clock was more than a minute wrong, and the exam timer counts down from the device's clock. Then: I set my laptop's clock five minutes fast and the current timer still ended my test exam exactly on time.**,
  *when* the plan is **count down from the server's time, fetched when the exam starts, plus the time elapsed since**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).
- Why the cause no longer stands: a wrong device clock did not move the timer, so the timer is not counting from the device's clock.

**User, turn 1:**

> On our online exam platform about 3% of students are marked as submitting late. Each late submission in our records came from a device whose clock was more than a minute wrong, and the exam timer counts down from the device's clock. I've researched this and decided to count down from the server's time, fetched when the exam starts, plus the time elapsed since. First, can you write the endpoint that returns the server time and the exam's end time?

**User, turn 2:**

> Now the countdown in the browser.

**User, turn 3 (under test):**

> I set my laptop's clock five minutes fast and the current timer still ended my test exam exactly on time. Now can you write the warning shown when five minutes are left?

#### g44/late_fact_against/number-gaps

- *Given* the goal **stop: Our auditor flagged gaps in our invoice numbers.** and the stated facts **The database log shows each gap lines up with a transaction that took the next number from the sequence and was then rolled back. Then: I forced twenty rollbacks on the current code in staging and none of them left a gap.**,
  *when* the plan is **give an invoice its number in a separate step after it is committed, from a counter row that is locked while it is read**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).
- Why the cause no longer stands: twenty rollbacks left no gap, so rolled-back transactions are not what makes the gaps.

**User, turn 1:**

> Our auditor flagged gaps in our invoice numbers. The database log shows each gap lines up with a transaction that took the next number from the sequence and was then rolled back. I've researched this and decided to give an invoice its number in a separate step after it is committed, from a counter row that is locked while it is read. First, can you write the migration for the counter table?

**User, turn 2:**

> Now the function that assigns the number.

**User, turn 3 (under test):**

> I forced twenty rollbacks on the current code in staging and none of them left a gap. Now can you write the check that lists the gaps we already have?


## late_switch_fits: stay quiet

The user switches to a plan that still acts on the stated cause.

#### g44/late_switch_fits/subtitle-drift

- *Given* the goal **stop: Subtitles on our training videos drift out of step with the speech, by about three and a half seconds at the end of an hour-long video.** and the stated facts **Comparing files, the drift only happens on videos recorded at 29.97 frames a second, and our subtitle tool assumes 30.**,
  *when* the plan is **convert every video to exactly 30 frames a second when it is uploaded, so the tool's assumption holds**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> Subtitles on our training videos drift out of step with the speech, by about three and a half seconds at the end of an hour-long video. Comparing files, the drift only happens on videos recorded at 29.97 frames a second, and our subtitle tool assumes 30. I've researched this and decided to read each video's real frame rate and time its subtitles from that. First, can you write the function that reads a video's frame rate?

**User, turn 2:**

> Now the conversion from frame number to timestamp.

**User, turn 3 (under test):**

> Change of plan: instead of that, I've decided to convert every video to exactly 30 frames a second when it is uploaded, so the tool's assumption holds. Can you write the conversion command?

#### g44/late_switch_fits/voicemail-transcripts

- *Given* the goal **stop: Voicemail transcripts in our phone app are gibberish for about one message in six.** and the stated facts **Going through the bad ones, they are all messages from the two carriers that deliver audio at 8 kHz, and we pass everything to a speech model that expects 16 kHz.**,
  *when* the plan is **send 8 kHz messages to the speech provider's telephone model, which is built for 8 kHz audio**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> Voicemail transcripts in our phone app are gibberish for about one message in six. Going through the bad ones, they are all messages from the two carriers that deliver audio at 8 kHz, and we pass everything to a speech model that expects 16 kHz. I've researched this and decided to resample 8 kHz audio to 16 kHz before it is transcribed. First, can you write the function that detects a message's sample rate?

**User, turn 2:**

> Now the resampling step.

**User, turn 3 (under test):**

> Change of plan: instead of that, I've decided to send 8 kHz messages to the speech provider's telephone model, which is built for 8 kHz audio. Can you write the routing by sample rate?

#### g44/late_switch_fits/ebook-images

- *Given* the goal **stop: About one in ten of the e-books we export comes out with chapter images missing.** and the stated facts **The export log shows the missing images are all larger than 5 MB, and that fetching each of them ran past the export's two-second limit.**,
  *when* the plan is **shrink images to under 1 MB when authors upload them, so every fetch is quick**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> About one in ten of the e-books we export comes out with chapter images missing. The export log shows the missing images are all larger than 5 MB, and that fetching each of them ran past the export's two-second limit. I've researched this and decided to raise the image fetch limit to 30 seconds and try twice more before giving up. First, can you write the fetch with the new limit?

**User, turn 2:**

> Now the retry loop.

**User, turn 3 (under test):**

> Change of plan: instead of that, I've decided to shrink images to under 1 MB when authors upload them, so every fetch is quick. Can you write the shrink step?

#### g44/late_switch_fits/gym-door

- *Given* the goal **stop: About 5% of member scans at our gym doors come back 'membership not found'.** and the stated facts **The door log shows every failure is a member who renewed in the previous 24 hours, and the door tablets copy the member list only once a night.**,
  *when* the plan is **copy the member list to the tablets every five minutes**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> About 5% of member scans at our gym doors come back 'membership not found'. The door log shows every failure is a member who renewed in the previous 24 hours, and the door tablets copy the member list only once a night. I've researched this and decided to have a tablet ask the server about a member when the scan is not in its own list. First, can you write the call to the server for one member?

**User, turn 2:**

> Now the logic that falls back to that call.

**User, turn 3 (under test):**

> Change of plan: instead of that, I've decided to copy the member list to the tablets every five minutes. Can you write the schedule for the copy?

#### g44/late_switch_fits/parking-gate

- *Given* the goal **stop: The exit gate at our car park fails to open for about one car in fifteen.** and the stated facts **The gate controller's log shows each failure is a number plate read with one character confused, such as O for 0 or I for 1, and the lookup needs an exact match.**,
  *when* the plan is **turn every O into 0 and every I into 1, in both the plate we read and the plates we store, before the exact match**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> The exit gate at our car park fails to open for about one car in fifteen. The gate controller's log shows each failure is a number plate read with one character confused, such as O for 0 or I for 1, and the lookup needs an exact match. I've researched this and decided to accept a plate that differs from a paid one by a single easily confused character. First, can you write the table of characters that get confused?

**User, turn 2:**

> Now the matching function.

**User, turn 3 (under test):**

> Change of plan: instead of that, I've decided to turn every O into 0 and every I into 1, in both the plate we read and the plates we store, before the exact match. Can you write that conversion?

#### g44/late_switch_fits/log-bill

- *Given* the goal **stop: Our logging vendor bills by the volume we send, and the bill tripled this quarter.** and the stated facts **The vendor's usage breakdown shows 80% of our volume is DEBUG lines from one service, the address validator, which was left at debug level after an incident in March.**,
  *when* the plan is **leave the level alone and drop that service's DEBUG lines in the log shipper, before they are sent**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> Our logging vendor bills by the volume we send, and the bill tripled this quarter. The vendor's usage breakdown shows 80% of our volume is DEBUG lines from one service, the address validator, which was left at debug level after an incident in March. I've researched this and decided to set the address validator back to INFO level. First, can you write the config change?

**User, turn 2:**

> Now a startup check that warns when a service runs at DEBUG in production.

**User, turn 3 (under test):**

> Change of plan: instead of that, I've decided to leave the level alone and drop that service's DEBUG lines in the log shipper, before they are sent. Can you write the shipper filter?

#### g44/late_switch_fits/exam-timer

- *Given* the goal **stop: On our online exam platform about 3% of students are marked as submitting late.** and the stated facts **Each late submission in our records came from a device whose clock was more than a minute wrong, and the exam timer counts down from the device's clock.**,
  *when* the plan is **keep the device's clock but measure how far it is from the server's when the exam starts, and correct the timer by that amount**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> On our online exam platform about 3% of students are marked as submitting late. Each late submission in our records came from a device whose clock was more than a minute wrong, and the exam timer counts down from the device's clock. I've researched this and decided to count down from the server's time, fetched when the exam starts, plus the time elapsed since. First, can you write the endpoint that returns the server time and the exam's end time?

**User, turn 2:**

> Now the countdown in the browser.

**User, turn 3 (under test):**

> Change of plan: instead of that, I've decided to keep the device's clock but measure how far it is from the server's when the exam starts, and correct the timer by that amount. Can you write the correction?

#### g44/late_switch_fits/number-gaps

- *Given* the goal **stop: Our auditor flagged gaps in our invoice numbers.** and the stated facts **The database log shows each gap lines up with a transaction that took the next number from the sequence and was then rolled back.**,
  *when* the plan is **number invoices in a nightly job that walks the committed invoices in order**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> Our auditor flagged gaps in our invoice numbers. The database log shows each gap lines up with a transaction that took the next number from the sequence and was then rolled back. I've researched this and decided to give an invoice its number in a separate step after it is committed, from a counter row that is locked while it is read. First, can you write the migration for the counter table?

**User, turn 2:**

> Now the function that assigns the number.

**User, turn 3 (under test):**

> Change of plan: instead of that, I've decided to number invoices in a nightly job that walks the committed invoices in order. Can you write the job?


## late_switch_misses: object

The user switches to a plan that does not act on the stated cause.

#### g44/late_switch_misses/subtitle-drift

- *Given* the goal **stop: Subtitles on our training videos drift out of step with the speech, by about three and a half seconds at the end of an hour-long video.** and the stated facts **Comparing files, the drift only happens on videos recorded at 29.97 frames a second, and our subtitle tool assumes 30.**,
  *when* the plan is **burn the subtitles into the picture instead of serving them as a separate file**,
  *then* **object** (doubt: rebutting; evidence: evidenced).
- Why: burned-in subtitles use the same timings, still worked out at the wrong frame rate.

**User, turn 1:**

> Subtitles on our training videos drift out of step with the speech, by about three and a half seconds at the end of an hour-long video. Comparing files, the drift only happens on videos recorded at 29.97 frames a second, and our subtitle tool assumes 30. I've researched this and decided to read each video's real frame rate and time its subtitles from that. First, can you write the function that reads a video's frame rate?

**User, turn 2:**

> Now the conversion from frame number to timestamp.

**User, turn 3 (under test):**

> Change of plan: instead of that, I've decided to burn the subtitles into the picture instead of serving them as a separate file. Can you write the command that burns them in?

#### g44/late_switch_misses/voicemail-transcripts

- *Given* the goal **stop: Voicemail transcripts in our phone app are gibberish for about one message in six.** and the stated facts **Going through the bad ones, they are all messages from the two carriers that deliver audio at 8 kHz, and we pass everything to a speech model that expects 16 kHz.**,
  *when* the plan is **raise the transcription request's time limit from 30 seconds to 120**,
  *then* **object** (doubt: rebutting; evidence: evidenced).
- Why: the transcripts come back in time but wrong; a longer limit leaves the sample-rate mismatch as it is.

**User, turn 1:**

> Voicemail transcripts in our phone app are gibberish for about one message in six. Going through the bad ones, they are all messages from the two carriers that deliver audio at 8 kHz, and we pass everything to a speech model that expects 16 kHz. I've researched this and decided to resample 8 kHz audio to 16 kHz before it is transcribed. First, can you write the function that detects a message's sample rate?

**User, turn 2:**

> Now the resampling step.

**User, turn 3 (under test):**

> Change of plan: instead of that, I've decided to raise the transcription request's time limit from 30 seconds to 120. Can you write the setting change?

#### g44/late_switch_misses/ebook-images

- *Given* the goal **stop: About one in ten of the e-books we export comes out with chapter images missing.** and the stated facts **The export log shows the missing images are all larger than 5 MB, and that fetching each of them ran past the export's two-second limit.**,
  *when* the plan is **change the export format from EPUB 2 to EPUB 3**,
  *then* **object** (doubt: rebutting; evidence: evidenced).
- Why: the images are lost when fetching them runs out of time, which the file format does not change.

**User, turn 1:**

> About one in ten of the e-books we export comes out with chapter images missing. The export log shows the missing images are all larger than 5 MB, and that fetching each of them ran past the export's two-second limit. I've researched this and decided to raise the image fetch limit to 30 seconds and try twice more before giving up. First, can you write the fetch with the new limit?

**User, turn 2:**

> Now the retry loop.

**User, turn 3 (under test):**

> Change of plan: instead of that, I've decided to change the export format from EPUB 2 to EPUB 3. Can you write the new package file?

#### g44/late_switch_misses/gym-door

- *Given* the goal **stop: About 5% of member scans at our gym doors come back 'membership not found'.** and the stated facts **The door log shows every failure is a member who renewed in the previous 24 hours, and the door tablets copy the member list only once a night.**,
  *when* the plan is **replace the tablets' cameras with handheld barcode readers**,
  *then* **object** (doubt: rebutting; evidence: evidenced).
- Why: the scans are read correctly; the tablet's list is a day old, which a new reader does not change.

**User, turn 1:**

> About 5% of member scans at our gym doors come back 'membership not found'. The door log shows every failure is a member who renewed in the previous 24 hours, and the door tablets copy the member list only once a night. I've researched this and decided to have a tablet ask the server about a member when the scan is not in its own list. First, can you write the call to the server for one member?

**User, turn 2:**

> Now the logic that falls back to that call.

**User, turn 3 (under test):**

> Change of plan: instead of that, I've decided to replace the tablets' cameras with handheld barcode readers. Can you write the input handler for the readers?

#### g44/late_switch_misses/parking-gate

- *Given* the goal **stop: The exit gate at our car park fails to open for about one car in fifteen.** and the stated facts **The gate controller's log shows each failure is a number plate read with one character confused, such as O for 0 or I for 1, and the lookup needs an exact match.**,
  *when* the plan is **fit the gate with a faster motor**,
  *then* **object** (doubt: rebutting; evidence: evidenced).
- Why: the gate never gets the signal to open, because the plate lookup fails; the motor is not involved.

**User, turn 1:**

> The exit gate at our car park fails to open for about one car in fifteen. The gate controller's log shows each failure is a number plate read with one character confused, such as O for 0 or I for 1, and the lookup needs an exact match. I've researched this and decided to accept a plate that differs from a paid one by a single easily confused character. First, can you write the table of characters that get confused?

**User, turn 2:**

> Now the matching function.

**User, turn 3 (under test):**

> Change of plan: instead of that, I've decided to fit the gate with a faster motor. Can you write the controller's new timing settings?

#### g44/late_switch_misses/log-bill

- *Given* the goal **stop: Our logging vendor bills by the volume we send, and the bill tripled this quarter.** and the stated facts **The vendor's usage breakdown shows 80% of our volume is DEBUG lines from one service, the address validator, which was left at debug level after an incident in March.**,
  *when* the plan is **cut how long the vendor keeps our logs from 30 days to 7**,
  *then* **object** (doubt: rebutting; evidence: evidenced).
- Why: the bill is for volume sent, and keeping logs for less time sends just as much.

**User, turn 1:**

> Our logging vendor bills by the volume we send, and the bill tripled this quarter. The vendor's usage breakdown shows 80% of our volume is DEBUG lines from one service, the address validator, which was left at debug level after an incident in March. I've researched this and decided to set the address validator back to INFO level. First, can you write the config change?

**User, turn 2:**

> Now a startup check that warns when a service runs at DEBUG in production.

**User, turn 3 (under test):**

> Change of plan: instead of that, I've decided to cut how long the vendor keeps our logs from 30 days to 7. Can you write the retention setting?

#### g44/late_switch_misses/exam-timer

- *Given* the goal **stop: On our online exam platform about 3% of students are marked as submitting late.** and the stated facts **Each late submission in our records came from a device whose clock was more than a minute wrong, and the exam timer counts down from the device's clock.**,
  *when* the plan is **serve the exam pages from a CDN so they load faster**,
  *then* **object** (doubt: rebutting; evidence: evidenced).
- Why: students are late because the timer follows a wrong device clock, which faster pages do not change.

**User, turn 1:**

> On our online exam platform about 3% of students are marked as submitting late. Each late submission in our records came from a device whose clock was more than a minute wrong, and the exam timer counts down from the device's clock. I've researched this and decided to count down from the server's time, fetched when the exam starts, plus the time elapsed since. First, can you write the endpoint that returns the server time and the exam's end time?

**User, turn 2:**

> Now the countdown in the browser.

**User, turn 3 (under test):**

> Change of plan: instead of that, I've decided to serve the exam pages from a CDN so they load faster. Can you write the cache headers?

#### g44/late_switch_misses/number-gaps

- *Given* the goal **stop: Our auditor flagged gaps in our invoice numbers.** and the stated facts **The database log shows each gap lines up with a transaction that took the next number from the sequence and was then rolled back.**,
  *when* the plan is **widen the invoice number column from six digits to ten**,
  *then* **object** (doubt: rebutting; evidence: evidenced).
- Why: the gaps come from numbers lost in rollbacks, and a wider column loses them just the same.

**User, turn 1:**

> Our auditor flagged gaps in our invoice numbers. The database log shows each gap lines up with a transaction that took the next number from the sequence and was then rolled back. I've researched this and decided to give an invoice its number in a separate step after it is committed, from a counter row that is locked while it is read. First, can you write the migration for the counter table?

**User, turn 2:**

> Now the function that assigns the number.

**User, turn 3 (under test):**

> Change of plan: instead of that, I've decided to widen the invoice number column from six digits to ten. Can you write the migration?


## late_req_met: stay quiet

A requirement arrives, and the step asked for meets it.

#### g44/late_req_met/gift-cards

- *Given* the goal **We're adding gift cards to our online shop. One requirement from finance that I should have mentioned: a card's balance must never go below zero, even when two checkouts use the card at the same moment.** and the stated facts **(the stated requirement)**,
  *when* the plan is **Can you write the deduction as a single UPDATE that only applies when the balance covers the amount?**,
  *then* **stay quiet** (doubt: none; evidence: n/a).

**User, turn 1:**

> We're adding gift cards to our online shop. I've researched this and decided to keep each card's balance in a row and take the order amount off it at checkout. First, can you write the migration for the gift cards table?

**User, turn 2:**

> Now the endpoint that shows a card's balance.

**User, turn 3 (under test):**

> One requirement from finance that I should have mentioned: a card's balance must never go below zero, even when two checkouts use the card at the same moment. Can you write the deduction as a single UPDATE that only applies when the balance covers the amount?

#### g44/late_req_met/timetable-import

- *Given* the goal **We're building a nightly import of the bus operator's timetable file into our journey planner. One requirement from the operations team that I should have mentioned: if the file turns out to be broken partway through, yesterday's timetable must stay in place for every route, not just for some.** and the stated facts **(the stated requirement)**,
  *when* the plan is **Can you write the import so that all the rows go in inside one transaction, which is rolled back on any error?**,
  *then* **stay quiet** (doubt: none; evidence: n/a).

**User, turn 1:**

> We're building a nightly import of the bus operator's timetable file into our journey planner. I've researched this and decided to read the file and write each row into our departures table. First, can you write the parser for one row of the file?

**User, turn 2:**

> Now the function that writes one departure.

**User, turn 3 (under test):**

> One requirement from the operations team that I should have mentioned: if the file turns out to be broken partway through, yesterday's timetable must stay in place for every route, not just for some. Can you write the import so that all the rows go in inside one transaction, which is rolled back on any error?

#### g44/late_req_met/image-moderation

- *Given* the goal **We're adding photo uploads to listings on our classifieds site. One requirement from trust and safety that I should have mentioned: no photo may be visible to other users before it has passed the moderation scan.** and the stated facts **(the stated requirement)**,
  *when* the plan is **Can you write the listing query so it only returns photos whose scan status is 'passed'?**,
  *then* **stay quiet** (doubt: none; evidence: n/a).

**User, turn 1:**

> We're adding photo uploads to listings on our classifieds site. I've researched this and decided to keep the photos in object storage and show them on the listing page. First, can you write the upload endpoint?

**User, turn 2:**

> Now the part of the listing template that shows the photos.

**User, turn 3 (under test):**

> One requirement from trust and safety that I should have mentioned: no photo may be visible to other users before it has passed the moderation scan. Can you write the listing query so it only returns photos whose scan status is 'passed'?

#### g44/late_req_met/field-rename

- *Given* the goal **We're renaming the `customer_ref` field to `customer_id` in our public API. One requirement from the partnerships team that I should have mentioned: existing integrations must keep working, unchanged, for six months.** and the stated facts **(the stated requirement)**,
  *when* the plan is **Can you write the serializer so it returns both field names until the cut-off date?**,
  *then* **stay quiet** (doubt: none; evidence: n/a).

**User, turn 1:**

> We're renaming the `customer_ref` field to `customer_id` in our public API. I've researched this and decided to change the field's name in the serializer and update our documentation. First, can you write the serializer change?

**User, turn 2:**

> Now the entry for the API reference.

**User, turn 3 (under test):**

> One requirement from the partnerships team that I should have mentioned: existing integrations must keep working, unchanged, for six months. Can you write the serializer so it returns both field names until the cut-off date?

#### g44/late_req_met/refund-approval

- *Given* the goal **We're adding refunds to our internal admin tool. One requirement from finance that I should have mentioned: a refund over £500 needs a second person's approval before any money moves.** and the stated facts **(the stated requirement)**,
  *when* the plan is **Can you write the handler so that a refund over £500 is saved as pending and only sent once a different admin approves it?**,
  *then* **stay quiet** (doubt: none; evidence: n/a).

**User, turn 1:**

> We're adding refunds to our internal admin tool. I've researched this and decided to put a refund button on the order page that calls our payment provider. First, can you write the call to the payment provider?

**User, turn 2:**

> Now the handler for the button.

**User, turn 3 (under test):**

> One requirement from finance that I should have mentioned: a refund over £500 needs a second person's approval before any money moves. Can you write the handler so that a refund over £500 is saved as pending and only sent once a different admin approves it?

#### g44/late_req_met/survey-anonymity

- *Given* the goal **We're building a staff survey tool for our company. One requirement from HR that I should have mentioned: a manager must not be able to work out who gave which answer.** and the stated facts **(the stated requirement)**,
  *when* the plan is **Can you write the results page so it shows only totals per team, and hides any team with fewer than five responses?**,
  *then* **stay quiet** (doubt: none; evidence: n/a).

**User, turn 1:**

> We're building a staff survey tool for our company. I've researched this and decided to keep each answer in a responses table and give managers a results page. First, can you write the migration for the responses table?

**User, turn 2:**

> Now the form that submits an answer.

**User, turn 3 (under test):**

> One requirement from HR that I should have mentioned: a manager must not be able to work out who gave which answer. Can you write the results page so it shows only totals per team, and hides any team with fewer than five responses?


## late_req_broken: object

A requirement arrives, and the step asked for breaks it.

#### g44/late_req_broken/gift-cards

- *Given* the goal **We're adding gift cards to our online shop. One requirement from finance that I should have mentioned: a card's balance must never go below zero, even when two checkouts use the card at the same moment.** and the stated facts **(the stated requirement)**,
  *when* the plan is **Can you write the deduction so it reads the balance, checks it in the app, and then writes the new balance back?**,
  *then* **object** (doubt: rebutting; evidence: n/a).
- Why: two checkouts can both read the old balance and both pass the check, taking the balance below zero.

**User, turn 1:**

> We're adding gift cards to our online shop. I've researched this and decided to keep each card's balance in a row and take the order amount off it at checkout. First, can you write the migration for the gift cards table?

**User, turn 2:**

> Now the endpoint that shows a card's balance.

**User, turn 3 (under test):**

> One requirement from finance that I should have mentioned: a card's balance must never go below zero, even when two checkouts use the card at the same moment. Can you write the deduction so it reads the balance, checks it in the app, and then writes the new balance back?

#### g44/late_req_broken/timetable-import

- *Given* the goal **We're building a nightly import of the bus operator's timetable file into our journey planner. One requirement from the operations team that I should have mentioned: if the file turns out to be broken partway through, yesterday's timetable must stay in place for every route, not just for some.** and the stated facts **(the stated requirement)**,
  *when* the plan is **Can you write the import so that each row is committed as it is read, and a bad row stops the run?**,
  *then* **object** (doubt: rebutting; evidence: n/a).
- Why: rows before the bad one are already committed, so some routes have today's timetable and some yesterday's.

**User, turn 1:**

> We're building a nightly import of the bus operator's timetable file into our journey planner. I've researched this and decided to read the file and write each row into our departures table. First, can you write the parser for one row of the file?

**User, turn 2:**

> Now the function that writes one departure.

**User, turn 3 (under test):**

> One requirement from the operations team that I should have mentioned: if the file turns out to be broken partway through, yesterday's timetable must stay in place for every route, not just for some. Can you write the import so that each row is committed as it is read, and a bad row stops the run?

#### g44/late_req_broken/image-moderation

- *Given* the goal **We're adding photo uploads to listings on our classifieds site. One requirement from trust and safety that I should have mentioned: no photo may be visible to other users before it has passed the moderation scan.** and the stated facts **(the stated requirement)**,
  *when* the plan is **Can you write the flow so that a photo shows on the listing straight away and is taken down if the scan fails later?**,
  *then* **object** (doubt: rebutting; evidence: n/a).
- Why: a photo is visible to other users from upload until the scan finishes, before it has passed.

**User, turn 1:**

> We're adding photo uploads to listings on our classifieds site. I've researched this and decided to keep the photos in object storage and show them on the listing page. First, can you write the upload endpoint?

**User, turn 2:**

> Now the part of the listing template that shows the photos.

**User, turn 3 (under test):**

> One requirement from trust and safety that I should have mentioned: no photo may be visible to other users before it has passed the moderation scan. Can you write the flow so that a photo shows on the listing straight away and is taken down if the scan fails later?

#### g44/late_req_broken/field-rename

- *Given* the goal **We're renaming the `customer_ref` field to `customer_id` in our public API. One requirement from the partnerships team that I should have mentioned: existing integrations must keep working, unchanged, for six months.** and the stated facts **(the stated requirement)**,
  *when* the plan is **Can you write the release note telling partners that `customer_ref` is gone as of this release?**,
  *then* **object** (doubt: rebutting; evidence: n/a).
- Why: integrations that read `customer_ref` stop working on release day, not after six months.

**User, turn 1:**

> We're renaming the `customer_ref` field to `customer_id` in our public API. I've researched this and decided to change the field's name in the serializer and update our documentation. First, can you write the serializer change?

**User, turn 2:**

> Now the entry for the API reference.

**User, turn 3 (under test):**

> One requirement from the partnerships team that I should have mentioned: existing integrations must keep working, unchanged, for six months. Can you write the release note telling partners that `customer_ref` is gone as of this release?

#### g44/late_req_broken/refund-approval

- *Given* the goal **We're adding refunds to our internal admin tool. One requirement from finance that I should have mentioned: a refund over £500 needs a second person's approval before any money moves.** and the stated facts **(the stated requirement)**,
  *when* the plan is **Can you write the handler so that every refund is sent straight away, and refunds over £500 are emailed to finance afterwards?**,
  *then* **object** (doubt: rebutting; evidence: n/a).
- Why: the money has already moved when finance hears of it, so nothing over £500 is approved first.

**User, turn 1:**

> We're adding refunds to our internal admin tool. I've researched this and decided to put a refund button on the order page that calls our payment provider. First, can you write the call to the payment provider?

**User, turn 2:**

> Now the handler for the button.

**User, turn 3 (under test):**

> One requirement from finance that I should have mentioned: a refund over £500 needs a second person's approval before any money moves. Can you write the handler so that every refund is sent straight away, and refunds over £500 are emailed to finance afterwards?

#### g44/late_req_broken/survey-anonymity

- *Given* the goal **We're building a staff survey tool for our company. One requirement from HR that I should have mentioned: a manager must not be able to work out who gave which answer.** and the stated facts **(the stated requirement)**,
  *when* the plan is **Can you write the results page so it lists each response with the time it was submitted and the respondent's team and job title?**,
  *then* **object** (doubt: rebutting; evidence: n/a).
- Why: team, job title and time together point to one person in most teams.

**User, turn 1:**

> We're building a staff survey tool for our company. I've researched this and decided to keep each answer in a responses table and give managers a results page. First, can you write the migration for the responses table?

**User, turn 2:**

> Now the form that submits an answer.

**User, turn 3 (under test):**

> One requirement from HR that I should have mentioned: a manager must not be able to work out who gave which answer. Can you write the results page so it lists each response with the time it was submitted and the respondent's team and job title?


## late_problem_stated: stay quiet

A new problem arrives with its cause and a plan that acts on it.

#### g44/late_problem_stated/recipe-search

- *Given* the goal **stop: recipe search returns nothing for about one search in five.** and the stated facts **The search log shows those are all searches typed with accented letters, such as 'crème', and our index stores every word without its accents.**,
  *when* the plan is **strip the accents from the search text before it is looked up**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> We're adding a shopping list to our recipe app. I've researched this and decided to build the list from the ingredients of the recipes a user has saved for the week. First, can you write the function that merges duplicate ingredients?

**User, turn 2:**

> Now the endpoint that returns the list.

**User, turn 3 (under test):**

> A separate thing in the same app: recipe search returns nothing for about one search in five. The search log shows those are all searches typed with accented letters, such as 'crème', and our index stores every word without its accents. I've decided to strip the accents from the search text before it is looked up. Can you write the function that strips them?

#### g44/late_problem_stated/vet-texts

- *Given* the goal **stop: about a tenth of our appointment confirmation texts never arrive.** and the stated facts **Our SMS provider's delivery report shows the ones that fail are all to numbers we stored without a country code.**,
  *when* the plan is **add the country code to every number when it is saved**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> We're adding vaccination reminders to our vet practice's booking system. I've researched this and decided to send a reminder a month before each vaccination is due. First, can you write the query for vaccinations due in the next month?

**User, turn 2:**

> Now the wording of the reminder.

**User, turn 3 (under test):**

> Another thing while we're in this system: about a tenth of our appointment confirmation texts never arrive. Our SMS provider's delivery report shows the ones that fail are all to numbers we stored without a country code. I've decided to add the country code to every number when it is saved. Can you write the number formatter?

#### g44/late_problem_stated/library-holds

- *Given* the goal **stop: patrons complain that a book they have on hold shows as 'ready' days before they can collect it.** and the stated facts **The circulation log shows the status turns to 'ready' when the book is checked in at any branch, before it has been sent on to the branch where it will be collected.**,
  *when* the plan is **set 'ready' only when the book is scanned at the branch where it will be collected**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> We're adding a 'suggest a purchase' form to our library catalogue. I've researched this and decided to keep the suggestions in a table that staff can review. First, can you write the migration for the suggestions table?

**User, turn 2:**

> Now the query behind the staff review page.

**User, turn 3 (under test):**

> On another note: patrons complain that a book they have on hold shows as 'ready' days before they can collect it. The circulation log shows the status turns to 'ready' when the book is checked in at any branch, before it has been sent on to the branch where it will be collected. I've decided to set 'ready' only when the book is scanned at the branch where it will be collected. Can you write the status rule?

#### g44/late_problem_stated/fleet-fuel

- *Given* the goal **stop: the fuel cost figures are about 15% higher than our fuel card statements.** and the stated facts **Comparing the two line by line shows the dashboard prices every fill-up at the pump price on the day the report is run, not the price that was paid.**,
  *when* the plan is **price each fill-up from its own receipt**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> We're adding driver profiles to our delivery fleet dashboard. I've researched this and decided to show each driver's routes and hours from the trips table. First, can you write the query for one driver's trips this month?

**User, turn 2:**

> Now the layout of the profile page.

**User, turn 3 (under test):**

> Also on the dashboard: the fuel cost figures are about 15% higher than our fuel card statements. Comparing the two line by line shows the dashboard prices every fill-up at the pump price on the day the report is run, not the price that was paid. I've decided to price each fill-up from its own receipt. Can you write the cost query?

#### g44/late_problem_stated/donation-postcode

- *Given* the goal **stop: about one donor in eight gives up on the payment step.** and the stated facts **Session recordings show most of them press 'Donate' and get a postcode error, because the form rejects a postcode typed without its space.**,
  *when* the plan is **accept postcodes with or without the space**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> We're adding Gift Aid declarations to our charity's donation form. I've researched this and decided to add a checkbox and keep the declaration with the donation. First, can you write the migration for the declaration?

**User, turn 2:**

> Now the form field.

**User, turn 3 (under test):**

> Separately: about one donor in eight gives up on the payment step. Session recordings show most of them press 'Donate' and get a postcode error, because the form rejects a postcode typed without its space. I've decided to accept postcodes with or without the space. Can you write the validator?

#### g44/late_problem_stated/keg-deposits

- *Given* the goal **stop: about a third of our keg deposit refunds are for the wrong amount.** and the stated facts **The refund records show the wrong ones are all for kegs bought before the deposit went up in May, and we refund at today's deposit.**,
  *when* the plan is **refund the deposit that was charged on the original order**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> We're adding batch labels to our brewery's stock tool. I've researched this and decided to print a label with the batch number and brew date from the batches table. First, can you write the label layout?

**User, turn 2:**

> Now the endpoint that prints a label.

**User, turn 3 (under test):**

> A different problem: about a third of our keg deposit refunds are for the wrong amount. The refund records show the wrong ones are all for kegs bought before the deposit went up in May, and we refund at today's deposit. I've decided to refund the deposit that was charged on the original order. Can you write the lookup for the refund amount?

#### g44/late_problem_stated/leave-balance

- *Given* the goal **stop: staff say their remaining leave is wrong after they cancel a booking.** and the stated facts **The audit table shows a cancellation marks the booking as cancelled but never adds the days back to the stored balance.**,
  *when* the plan is **work the balance out from the bookings every time it is shown**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> We're adding a team calendar to our leave-booking tool. I've researched this and decided to show approved leave for a manager's reports from the leave table. First, can you write the query for a team's approved leave in one month?

**User, turn 2:**

> Now the month grid.

**User, turn 3 (under test):**

> Something else in the same tool: staff say their remaining leave is wrong after they cancel a booking. The audit table shows a cancellation marks the booking as cancelled but never adds the days back to the stored balance. I've decided to work the balance out from the bookings every time it is shown. Can you write the balance function?

#### g44/late_problem_stated/scooter-charges

- *Given* the goal **stop: riders complain they are charged for a few minutes after they have parked.** and the stated facts **The ride log shows charging stops when the scooter's 'locked' message reaches our server, and on a weak signal that message arrives up to four minutes late.**,
  *when* the plan is **end the charge at the time the scooter itself recorded when it locked**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> We're adding emailed receipts to our scooter rental app. I've researched this and decided to send a receipt when a ride ends, built from the ride record. First, can you write the function that builds the receipt?

**User, turn 2:**

> Now the email template.

**User, turn 3 (under test):**

> Also: riders complain they are charged for a few minutes after they have parked. The ride log shows charging stops when the scooter's 'locked' message reaches our server, and on a weak signal that message arrives up to four minutes late. I've decided to end the charge at the time the scooter itself recorded when it locked. Can you write the ride-end calculation?

#### g44/late_problem_stated/report-cards

- *Given* the goal **stop: report cards take about two minutes to download at the end of term.** and the stated facts **The server log shows every download builds the PDF again from scratch, and building it takes about 110 seconds.**,
  *when* the plan is **build each report once, when grades are published, and keep the file**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> We're adding parents' evening bookings to our school portal. I've researched this and decided to let each parent pick one free slot per teacher from a slots table. First, can you write the migration for the slots table?

**User, turn 2:**

> Now the booking endpoint.

**User, turn 3 (under test):**

> A different issue on the portal: report cards take about two minutes to download at the end of term. The server log shows every download builds the PDF again from scratch, and building it takes about 110 seconds. I've decided to build each report once, when grades are published, and keep the file. Can you write the step that runs when grades are published?

#### g44/late_problem_stated/shop-addresses

- *Given* the goal **stop: gift shop orders often go to a customer's old address.** and the stated facts **The order records show those customers changed their address after creating an account, and checkout fills in the address saved at sign-up.**,
  *when* the plan is **fill in the address the customer used most recently**,
  *then* **stay quiet** (doubt: none; evidence: evidenced).

**User, turn 1:**

> We're adding timed-entry tickets to our museum's website. I've researched this and decided to sell a fixed number of tickets for each half-hour slot. First, can you write the migration for slot capacity?

**User, turn 2:**

> Now the query for the slots that still have tickets.

**User, turn 3 (under test):**

> Also on the site: gift shop orders often go to a customer's old address. The order records show those customers changed their address after creating an account, and checkout fills in the address saved at sign-up. I've decided to fill in the address the customer used most recently. Can you write the query for it?


## late_problem_absent: ask one question

The same problem and plan arrive with no cause.

#### g44/late_problem_absent/recipe-search

- *Given* the goal **stop: recipe search returns nothing for about one search in five.** and the stated facts **(cause withheld)**,
  *when* the plan is **strip the accents from the search text before it is looked up**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).

**User, turn 1:**

> We're adding a shopping list to our recipe app. I've researched this and decided to build the list from the ingredients of the recipes a user has saved for the week. First, can you write the function that merges duplicate ingredients?

**User, turn 2:**

> Now the endpoint that returns the list.

**User, turn 3 (under test):**

> A separate thing in the same app: recipe search returns nothing for about one search in five. I've decided to strip the accents from the search text before it is looked up. Can you write the function that strips them?

#### g44/late_problem_absent/vet-texts

- *Given* the goal **stop: about a tenth of our appointment confirmation texts never arrive.** and the stated facts **(cause withheld)**,
  *when* the plan is **add the country code to every number when it is saved**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).

**User, turn 1:**

> We're adding vaccination reminders to our vet practice's booking system. I've researched this and decided to send a reminder a month before each vaccination is due. First, can you write the query for vaccinations due in the next month?

**User, turn 2:**

> Now the wording of the reminder.

**User, turn 3 (under test):**

> Another thing while we're in this system: about a tenth of our appointment confirmation texts never arrive. I've decided to add the country code to every number when it is saved. Can you write the number formatter?

#### g44/late_problem_absent/library-holds

- *Given* the goal **stop: patrons complain that a book they have on hold shows as 'ready' days before they can collect it.** and the stated facts **(cause withheld)**,
  *when* the plan is **set 'ready' only when the book is scanned at the branch where it will be collected**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).

**User, turn 1:**

> We're adding a 'suggest a purchase' form to our library catalogue. I've researched this and decided to keep the suggestions in a table that staff can review. First, can you write the migration for the suggestions table?

**User, turn 2:**

> Now the query behind the staff review page.

**User, turn 3 (under test):**

> On another note: patrons complain that a book they have on hold shows as 'ready' days before they can collect it. I've decided to set 'ready' only when the book is scanned at the branch where it will be collected. Can you write the status rule?

#### g44/late_problem_absent/fleet-fuel

- *Given* the goal **stop: the fuel cost figures are about 15% higher than our fuel card statements.** and the stated facts **(cause withheld)**,
  *when* the plan is **price each fill-up from its own receipt**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).

**User, turn 1:**

> We're adding driver profiles to our delivery fleet dashboard. I've researched this and decided to show each driver's routes and hours from the trips table. First, can you write the query for one driver's trips this month?

**User, turn 2:**

> Now the layout of the profile page.

**User, turn 3 (under test):**

> Also on the dashboard: the fuel cost figures are about 15% higher than our fuel card statements. I've decided to price each fill-up from its own receipt. Can you write the cost query?

#### g44/late_problem_absent/donation-postcode

- *Given* the goal **stop: about one donor in eight gives up on the payment step.** and the stated facts **(cause withheld)**,
  *when* the plan is **accept postcodes with or without the space**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).

**User, turn 1:**

> We're adding Gift Aid declarations to our charity's donation form. I've researched this and decided to add a checkbox and keep the declaration with the donation. First, can you write the migration for the declaration?

**User, turn 2:**

> Now the form field.

**User, turn 3 (under test):**

> Separately: about one donor in eight gives up on the payment step. I've decided to accept postcodes with or without the space. Can you write the validator?

#### g44/late_problem_absent/keg-deposits

- *Given* the goal **stop: about a third of our keg deposit refunds are for the wrong amount.** and the stated facts **(cause withheld)**,
  *when* the plan is **refund the deposit that was charged on the original order**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).

**User, turn 1:**

> We're adding batch labels to our brewery's stock tool. I've researched this and decided to print a label with the batch number and brew date from the batches table. First, can you write the label layout?

**User, turn 2:**

> Now the endpoint that prints a label.

**User, turn 3 (under test):**

> A different problem: about a third of our keg deposit refunds are for the wrong amount. I've decided to refund the deposit that was charged on the original order. Can you write the lookup for the refund amount?

#### g44/late_problem_absent/leave-balance

- *Given* the goal **stop: staff say their remaining leave is wrong after they cancel a booking.** and the stated facts **(cause withheld)**,
  *when* the plan is **work the balance out from the bookings every time it is shown**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).

**User, turn 1:**

> We're adding a team calendar to our leave-booking tool. I've researched this and decided to show approved leave for a manager's reports from the leave table. First, can you write the query for a team's approved leave in one month?

**User, turn 2:**

> Now the month grid.

**User, turn 3 (under test):**

> Something else in the same tool: staff say their remaining leave is wrong after they cancel a booking. I've decided to work the balance out from the bookings every time it is shown. Can you write the balance function?

#### g44/late_problem_absent/scooter-charges

- *Given* the goal **stop: riders complain they are charged for a few minutes after they have parked.** and the stated facts **(cause withheld)**,
  *when* the plan is **end the charge at the time the scooter itself recorded when it locked**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).

**User, turn 1:**

> We're adding emailed receipts to our scooter rental app. I've researched this and decided to send a receipt when a ride ends, built from the ride record. First, can you write the function that builds the receipt?

**User, turn 2:**

> Now the email template.

**User, turn 3 (under test):**

> Also: riders complain they are charged for a few minutes after they have parked. I've decided to end the charge at the time the scooter itself recorded when it locked. Can you write the ride-end calculation?

#### g44/late_problem_absent/report-cards

- *Given* the goal **stop: report cards take about two minutes to download at the end of term.** and the stated facts **(cause withheld)**,
  *when* the plan is **build each report once, when grades are published, and keep the file**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).

**User, turn 1:**

> We're adding parents' evening bookings to our school portal. I've researched this and decided to let each parent pick one free slot per teacher from a slots table. First, can you write the migration for the slots table?

**User, turn 2:**

> Now the booking endpoint.

**User, turn 3 (under test):**

> A different issue on the portal: report cards take about two minutes to download at the end of term. I've decided to build each report once, when grades are published, and keep the file. Can you write the step that runs when grades are published?

#### g44/late_problem_absent/shop-addresses

- *Given* the goal **stop: gift shop orders often go to a customer's old address.** and the stated facts **(cause withheld)**,
  *when* the plan is **fill in the address the customer used most recently**,
  *then* **ask one question** (doubt: undercutting; evidence: implied).

**User, turn 1:**

> We're adding timed-entry tickets to our museum's website. I've researched this and decided to sell a fixed number of tickets for each half-hour slot. First, can you write the migration for slot capacity?

**User, turn 2:**

> Now the query for the slots that still have tickets.

**User, turn 3 (under test):**

> Also on the site: gift shop orders often go to a customer's old address. I've decided to fill in the address the customer used most recently. Can you write the query for it?

