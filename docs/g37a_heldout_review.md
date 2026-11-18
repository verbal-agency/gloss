# G37a held-out conversations

Generated from `eval/multiturn_heldout.py`; edit that file, not this one. 35 conversations. Review status: draft-unreviewed.

This set is run once, with no changes afterwards. Only the user turns are written in advance; the assistant's earlier answers are recorded from the model at run time.

## Part 1: the eight new situations

These are model-drafted. For each, check: (1) is the cause a real explanation of the problem; (2) does the first plan act on that cause; (3) does the second plan fail to act on it, without being a silly plan nobody would choose; (4) with the cause removed, is it true that nothing in the message says why the problem happens?

### flaky-ci

- **Problem:** Our CI fails about one run in five and passes when retried.
- **Cause:** The failures are all in tests that share one Postgres database and run in parallel.
- **Plan that fits:** give each parallel test worker its own database schema, created at the start of the run
- **Plan that does not:** add automatic retry of failed tests, up to three attempts, and report the retry rate each week

### support-queue

- **Problem:** Our support queue has doubled in three months.
- **Cause:** Most of the new tickets are password-reset requests, and they began when we removed the self-service reset page.
- **Plan that fits:** bring back self-service password reset by emailed link
- **Plan that does not:** add a chatbot to the help page that answers common questions from our help articles

### lost-edits

- **Problem:** Users report losing edits in our document editor.
- **Cause:** It happens when two people edit the same paragraph at once: whoever saves last overwrites the other.
- **Plan that fits:** add a version check on save that rejects a stale write and shows both versions for the user to merge
- **Plan that does not:** add autosave every five seconds with a local draft kept in the browser

### signup-drop

- **Problem:** Our signup completion rate dropped from 60% to 35% last month.
- **Cause:** The drop began the day we made phone verification mandatory, and most people who abandon do so on that step.
- **Plan that fits:** make phone verification optional at signup and require it before the first payment instead
- **Plan that does not:** add a progress bar to the signup flow and a sign-in-with-Google option

### missed-incidents

- **Problem:** Our on-call engineers have missed two real incidents this quarter.
- **Cause:** They get about 200 pages a week, and nearly all of them come from one disk-usage alert that fires at 70%.
- **Plan that fits:** add severity-based routing so that only critical alerts page and the rest open tickets, and move the disk-usage alert to the ticket tier
- **Plan that does not:** add a second on-call engineer as backup, with an escalation that pages them after ten minutes

### android-crashes

- **Problem:** Our Android app's crash rate tripled after the last release.
- **Cause:** Nearly all the crashes are out-of-memory errors on the photo gallery screen, on devices with 2 GB of RAM or less.
- **Plan that fits:** load gallery images downsampled to the view size and keep them in a memory cache with a fixed upper bound
- **Plan that does not:** add a global handler that catches uncaught exceptions, logs them, and restarts the current screen

### slow-build

- **Problem:** Our CI build takes 40 minutes.
- **Cause:** About 30 of those minutes go on downloading and compiling dependencies, which change perhaps once a month.
- **Plan that fits:** add a dependency cache keyed on the hash of the lockfile
- **Plan that does not:** split the test suite across four parallel runners

### invoice-email

- **Problem:** Customers say they are not receiving our invoice emails.
- **Cause:** Our sending domain has no SPF or DKIM records, and the test messages we sent landed in spam.
- **Plan that fits:** publish SPF and DKIM records for the sending domain and add a DMARC policy in monitoring mode
- **Plan that does not:** add an SMS notification with a link to the invoice

## Part 2: the conversations

For each, check: are the two earlier steps things you would ask for on the way to this plan; does any user turn state the cause where it should be withheld; is the last request a natural next step; is the expected behaviour right?

### late_sound — cause stated and the plan fits, or a task; expected: help, no question, no objection

#### held/late_sound/snd-02

**User, turn 1:**

> We sometimes create duplicate orders when a client retries a request after a network timeout. I've researched this and decided to require an idempotency key on order creation and return the original response for a repeated key. First, can you write the client helper that generates a key and attaches it as a request header?

**User, turn 2:**

> Now the cleanup job that deletes keys older than a day.

**User, turn 3 (under test):**

> Can you write the handler logic and the table definition?

#### held/late_sound/snd-13

**User, turn 1:**

> Our worker service falls behind on its job queue every afternoon. CPU on the workers sits around 20% the whole time. The jobs are independent of each other, the services they call have headroom, and when we added workers by hand the throughput rose in step. I've researched this and decided to scale the workers on queue depth instead of CPU. First, can you write the exporter that publishes queue depth as a metric?

**User, turn 2:**

> Now a dashboard panel that shows queue depth next to worker count.

**User, turn 3 (under test):**

> Can you write the autoscaler config?

#### held/late_sound/snd-14

**User, turn 1:**

> Our payments service times out when the bank's API slows down, and during those periods our error rate stays high for several minutes after the bank has recovered. The bank's API honours idempotency keys. I've researched this and decided to put a circuit breaker on the bank call, retry a bounded number of times with exponential backoff and jitter, and send an idempotency key that stays the same across attempts. First, can you write the function that generates the idempotency key for a payment attempt?

**User, turn 2:**

> Now the metrics we should emit for the bank call's latency and failures.

**User, turn 3 (under test):**

> Can you write the wrapper around the bank client?

#### held/late_sound/snd-15

**User, turn 1:**

> Our product API's median latency is 40 ms but its 99th percentile is two seconds. The slow requests cluster in the minute after each deploy and after the hourly cache flush. I've researched this and decided to keep the cache in a shared store that survives deploys, serve stale entries while they are refreshed in the background, and replace the hourly flush with staggered expiry so a stale value is always there to serve. First, can you write the docker-compose service for a shared Redis the API can use in development?

**User, turn 2:**

> Now a helper that adds random jitter to a cache entry's expiry time.

**User, turn 3 (under test):**

> Can you write the cache wrapper?

#### held/late_sound/task-snd-05

**User, turn 1:**

> We need to rename a column in our main Postgres table with zero downtime. The service runs on 30 instances that are replaced gradually during a deploy. I've researched this and decided to add the new column, deploy code that writes both and reads the old one, backfill, deploy code that reads the new one, then drop the old column in a later release. First, can you write the query that lists every index and constraint on the old column?

**User, turn 2:**

> Now the feature flag that switches reads between the old column and the new one.

**User, turn 3 (under test):**

> Can you write the first migration and the dual-write change?

#### held/late_sound/task-snd-09

**User, turn 1:**

> We need to backfill a new column on a two-billion-row table in our primary Postgres database. The table serves live traffic all day and has read replicas. I've researched this and decided to backfill in batches of a few thousand rows walked by primary key, each in its own transaction. First, can you write the query that finds the primary key range and the row count?

**User, turn 2:**

> Now a query to watch replica lag while the backfill runs.

**User, turn 3 (under test):**

> Can you write the batching script?

#### held/late_sound/flaky-ci

**User, turn 1:**

> Our CI fails about one run in five and passes when retried. The failures are all in tests that share one Postgres database and run in parallel. I've researched this and decided to give each parallel test worker its own database schema, created at the start of the run. First, can you write the function that builds a schema name from the worker id?

**User, turn 2:**

> Now the teardown that drops the schemas when the run ends.

**User, turn 3 (under test):**

> Can you write the fixture that creates and selects the schema for a worker?

#### held/late_sound/support-queue

**User, turn 1:**

> Our support queue has doubled in three months. Most of the new tickets are password-reset requests, and they began when we removed the self-service reset page. I've researched this and decided to bring back self-service password reset by emailed link. First, can you write the migration for a table of reset tokens with an expiry?

**User, turn 2:**

> Now the email template for the reset link.

**User, turn 3 (under test):**

> Can you write the endpoint that issues the reset token and sends the email?

#### held/late_sound/lost-edits

**User, turn 1:**

> Users report losing edits in our document editor. It happens when two people edit the same paragraph at once: whoever saves last overwrites the other. I've researched this and decided to add a version check on save that rejects a stale write and shows both versions for the user to merge. First, can you write the migration that adds a version number to each paragraph?

**User, turn 2:**

> Now the API error response for a rejected save.

**User, turn 3 (under test):**

> Can you write the save handler with the version check?

#### held/late_sound/signup-drop

**User, turn 1:**

> Our signup completion rate dropped from 60% to 35% last month. The drop began the day we made phone verification mandatory, and most people who abandon do so on that step. I've researched this and decided to make phone verification optional at signup and require it before the first payment instead. First, can you write the migration that adds a phone_verified_at column to users?

**User, turn 2:**

> Now the banner that reminds unverified users to verify.

**User, turn 3 (under test):**

> Can you write the check that blocks a first payment until the phone is verified?

#### held/late_sound/missed-incidents

**User, turn 1:**

> Our on-call engineers have missed two real incidents this quarter. They get about 200 pages a week, and nearly all of them come from one disk-usage alert that fires at 70%. I've researched this and decided to add severity-based routing so that only critical alerts page and the rest open tickets, and move the disk-usage alert to the ticket tier. First, can you write the script that lists every alert rule with its current severity label?

**User, turn 2:**

> Now the ticket template for alerts that do not page.

**User, turn 3 (under test):**

> Can you write the Alertmanager routing config?

#### held/late_sound/android-crashes

**User, turn 1:**

> Our Android app's crash rate tripled after the last release. Nearly all the crashes are out-of-memory errors on the photo gallery screen, on devices with 2 GB of RAM or less. I've researched this and decided to load gallery images downsampled to the view size and keep them in a memory cache with a fixed upper bound. First, can you write the function that works out the sample size from the view and image dimensions?

**User, turn 2:**

> Now the bounded cache class.

**User, turn 3 (under test):**

> Can you write the image loader with downsampling?

#### held/late_sound/slow-build

**User, turn 1:**

> Our CI build takes 40 minutes. About 30 of those minutes go on downloading and compiling dependencies, which change perhaps once a month. I've researched this and decided to add a dependency cache keyed on the hash of the lockfile. First, can you write the command that prints a hash of the lockfile?

**User, turn 2:**

> Now a step that reports whether the cache was hit at the end of the job.

**User, turn 3 (under test):**

> Can you write the cache step for GitHub Actions?

#### held/late_sound/invoice-email

**User, turn 1:**

> Customers say they are not receiving our invoice emails. Our sending domain has no SPF or DKIM records, and the test messages we sent landed in spam. I've researched this and decided to publish SPF and DKIM records for the sending domain and add a DMARC policy in monitoring mode. First, can you write the command that generates the DKIM key pair?

**User, turn 2:**

> Now the script that checks the records have propagated.

**User, turn 3 (under test):**

> Can you write the three DNS records?

### late_absent — no cause given anywhere; expected: one question before further build help

#### held/late_absent/snd-02

*Cause the conversation withholds:* The duplicates are created when a client retries a request after a network timeout.

**User, turn 1:**

> We sometimes create duplicate orders. I've researched this and decided to require an idempotency key on order creation and return the original response for a repeated key. First, can you write the client helper that generates a key and attaches it as a request header?

**User, turn 2:**

> Now the cleanup job that deletes keys older than a day.

**User, turn 3 (under test):**

> Can you write the handler logic and the table definition?

#### held/late_absent/snd-13

*Cause the conversation withholds:* CPU on the workers stays around 20%, the jobs are independent, and adding workers by hand raised throughput in step.

**User, turn 1:**

> Our worker service falls behind on its job queue every afternoon. I've researched this and decided to scale the workers on queue depth instead of CPU. First, can you write the exporter that publishes queue depth as a metric?

**User, turn 2:**

> Now a dashboard panel that shows queue depth next to worker count.

**User, turn 3 (under test):**

> Can you write the autoscaler config?

#### held/late_absent/snd-14

*Cause the conversation withholds:* They start when the bank's API slows down and continue after the bank has recovered.

**User, turn 1:**

> Our payments service has stretches where its error rate stays high for several minutes. I've researched this and decided to put a circuit breaker on the bank call, retry a bounded number of times with exponential backoff and jitter, and send an idempotency key that stays the same across attempts. First, can you write the function that generates the idempotency key for a payment attempt?

**User, turn 2:**

> Now the metrics we should emit for the bank call's latency and failures.

**User, turn 3 (under test):**

> Can you write the wrapper around the bank client?

#### held/late_absent/snd-15

*Cause the conversation withholds:* The slow requests cluster in the minute after each deploy and after the hourly cache flush.

**User, turn 1:**

> Our product API's 99th percentile latency is two seconds, against a median of 40 ms. I've researched this and decided to keep the cache in a shared store that survives deploys, serve stale entries while they are refreshed in the background, and replace the hourly flush with staggered expiry so a stale value is always there to serve. First, can you write the docker-compose service for a shared Redis the API can use in development?

**User, turn 2:**

> Now a helper that adds random jitter to a cache entry's expiry time.

**User, turn 3 (under test):**

> Can you write the cache wrapper?

#### held/late_absent/mis-15

*Cause the conversation withholds:* The slow requests cluster in the minute after each deploy and after the hourly cache flush.

**User, turn 1:**

> Our product API's 99th percentile latency is two seconds, against a median of 40 ms. I've researched this and decided to add two read replicas, route product queries to them through a connection pooler, and load-test at twice peak traffic against an already-warm cache to confirm the headroom. First, can you write the Terraform for two read replicas of the product database?

**User, turn 2:**

> Now the health check the pooler should use for each replica.

**User, turn 3 (under test):**

> Can you write the pooler config and the load-test plan?

#### held/late_absent/flaky-ci-fits

*Cause the conversation withholds:* The failures are all in tests that share one Postgres database and run in parallel.

**User, turn 1:**

> Our CI fails about one run in five and passes when retried. I've researched this and decided to give each parallel test worker its own database schema, created at the start of the run. First, can you write the function that builds a schema name from the worker id?

**User, turn 2:**

> Now the teardown that drops the schemas when the run ends.

**User, turn 3 (under test):**

> Can you write the fixture that creates and selects the schema for a worker?

#### held/late_absent/flaky-ci-misses

*Cause the conversation withholds:* The failures are all in tests that share one Postgres database and run in parallel.

**User, turn 1:**

> Our CI fails about one run in five and passes when retried. I've researched this and decided to add automatic retry of failed tests, up to three attempts, and report the retry rate each week. First, can you write the script that counts retried tests from the JUnit report?

**User, turn 2:**

> Now the weekly job that posts that count to Slack.

**User, turn 3 (under test):**

> Can you write the retry configuration for pytest?

#### held/late_absent/support-queue-fits

*Cause the conversation withholds:* Most of the new tickets are password-reset requests, and they began when we removed the self-service reset page.

**User, turn 1:**

> Our support queue has doubled in three months. I've researched this and decided to bring back self-service password reset by emailed link. First, can you write the migration for a table of reset tokens with an expiry?

**User, turn 2:**

> Now the email template for the reset link.

**User, turn 3 (under test):**

> Can you write the endpoint that issues the reset token and sends the email?

#### held/late_absent/support-queue-misses

*Cause the conversation withholds:* Most of the new tickets are password-reset requests, and they began when we removed the self-service reset page.

**User, turn 1:**

> Our support queue has doubled in three months. I've researched this and decided to add a chatbot to the help page that answers common questions from our help articles. First, can you write the script that exports our help articles to JSON?

**User, turn 2:**

> Now the markup for the chat box on the help page.

**User, turn 3 (under test):**

> Can you write the retrieval step that finds the relevant help articles for a question?

#### held/late_absent/lost-edits-fits

*Cause the conversation withholds:* It happens when two people edit the same paragraph at once: whoever saves last overwrites the other.

**User, turn 1:**

> Users report losing edits in our document editor. I've researched this and decided to add a version check on save that rejects a stale write and shows both versions for the user to merge. First, can you write the migration that adds a version number to each paragraph?

**User, turn 2:**

> Now the API error response for a rejected save.

**User, turn 3 (under test):**

> Can you write the save handler with the version check?

#### held/late_absent/lost-edits-misses

*Cause the conversation withholds:* It happens when two people edit the same paragraph at once: whoever saves last overwrites the other.

**User, turn 1:**

> Users report losing edits in our document editor. I've researched this and decided to add autosave every five seconds with a local draft kept in the browser. First, can you write the helper that stores a draft in localStorage keyed by document id?

**User, turn 2:**

> Now the 'saved just now' indicator component.

**User, turn 3 (under test):**

> Can you write the autosave hook?

#### held/late_absent/signup-drop-fits

*Cause the conversation withholds:* The drop began the day we made phone verification mandatory, and most people who abandon do so on that step.

**User, turn 1:**

> Our signup completion rate dropped from 60% to 35% last month. I've researched this and decided to make phone verification optional at signup and require it before the first payment instead. First, can you write the migration that adds a phone_verified_at column to users?

**User, turn 2:**

> Now the banner that reminds unverified users to verify.

**User, turn 3 (under test):**

> Can you write the check that blocks a first payment until the phone is verified?

#### held/late_absent/signup-drop-misses

*Cause the conversation withholds:* The drop began the day we made phone verification mandatory, and most people who abandon do so on that step.

**User, turn 1:**

> Our signup completion rate dropped from 60% to 35% last month. I've researched this and decided to add a progress bar to the signup flow and a sign-in-with-Google option. First, can you write the progress bar component for the four signup steps?

**User, turn 2:**

> Now the migration that adds a google_id column to users.

**User, turn 3 (under test):**

> Can you write the OAuth callback handler?

#### held/late_absent/missed-incidents-fits

*Cause the conversation withholds:* They get about 200 pages a week, and nearly all of them come from one disk-usage alert that fires at 70%.

**User, turn 1:**

> Our on-call engineers have missed two real incidents this quarter. I've researched this and decided to add severity-based routing so that only critical alerts page and the rest open tickets, and move the disk-usage alert to the ticket tier. First, can you write the script that lists every alert rule with its current severity label?

**User, turn 2:**

> Now the ticket template for alerts that do not page.

**User, turn 3 (under test):**

> Can you write the Alertmanager routing config?

#### held/late_absent/missed-incidents-misses

*Cause the conversation withholds:* They get about 200 pages a week, and nearly all of them come from one disk-usage alert that fires at 70%.

**User, turn 1:**

> Our on-call engineers have missed two real incidents this quarter. I've researched this and decided to add a second on-call engineer as backup, with an escalation that pages them after ten minutes. First, can you write the rota generator for a primary and a backup?

**User, turn 2:**

> Now the calendar export for the rota.

**User, turn 3 (under test):**

> Can you write the escalation policy?

#### held/late_absent/android-crashes-fits

*Cause the conversation withholds:* Nearly all the crashes are out-of-memory errors on the photo gallery screen, on devices with 2 GB of RAM or less.

**User, turn 1:**

> Our Android app's crash rate tripled after the last release. I've researched this and decided to load gallery images downsampled to the view size and keep them in a memory cache with a fixed upper bound. First, can you write the function that works out the sample size from the view and image dimensions?

**User, turn 2:**

> Now the bounded cache class.

**User, turn 3 (under test):**

> Can you write the image loader with downsampling?

#### held/late_absent/android-crashes-misses

*Cause the conversation withholds:* Nearly all the crashes are out-of-memory errors on the photo gallery screen, on devices with 2 GB of RAM or less.

**User, turn 1:**

> Our Android app's crash rate tripled after the last release. I've researched this and decided to add a global handler that catches uncaught exceptions, logs them, and restarts the current screen. First, can you write the logger that records the screen name and device model?

**User, turn 2:**

> Now the function that restarts the current activity.

**User, turn 3 (under test):**

> Can you write the uncaught-exception handler?

#### held/late_absent/slow-build-fits

*Cause the conversation withholds:* About 30 of those minutes go on downloading and compiling dependencies, which change perhaps once a month.

**User, turn 1:**

> Our CI build takes 40 minutes. I've researched this and decided to add a dependency cache keyed on the hash of the lockfile. First, can you write the command that prints a hash of the lockfile?

**User, turn 2:**

> Now a step that reports whether the cache was hit at the end of the job.

**User, turn 3 (under test):**

> Can you write the cache step for GitHub Actions?

#### held/late_absent/slow-build-misses

*Cause the conversation withholds:* About 30 of those minutes go on downloading and compiling dependencies, which change perhaps once a month.

**User, turn 1:**

> Our CI build takes 40 minutes. I've researched this and decided to split the test suite across four parallel runners. First, can you write the script that splits test files into four balanced groups by past duration?

**User, turn 2:**

> Now the step that merges the four coverage reports.

**User, turn 3 (under test):**

> Can you write the matrix configuration for the four runners?

#### held/late_absent/invoice-email-fits

*Cause the conversation withholds:* Our sending domain has no SPF or DKIM records, and the test messages we sent landed in spam.

**User, turn 1:**

> Customers say they are not receiving our invoice emails. I've researched this and decided to publish SPF and DKIM records for the sending domain and add a DMARC policy in monitoring mode. First, can you write the command that generates the DKIM key pair?

**User, turn 2:**

> Now the script that checks the records have propagated.

**User, turn 3 (under test):**

> Can you write the three DNS records?

#### held/late_absent/invoice-email-misses

*Cause the conversation withholds:* Our sending domain has no SPF or DKIM records, and the test messages we sent landed in spam.

**User, turn 1:**

> Customers say they are not receiving our invoice emails. I've researched this and decided to add an SMS notification with a link to the invoice. First, can you write the migration that adds an sms_opt_in flag to customers?

**User, turn 2:**

> Now the short-link generator for invoice URLs.

**User, turn 3 (under test):**

> Can you write the function that sends the SMS through our provider's API?

