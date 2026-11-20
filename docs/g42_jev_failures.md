# Jev's G42 test failures

Arm `jev_g42_plain`, model `jev-1.14.0`, rule `problem_described>=0.3 min(mechanism_stated)<0.7 contra>=0.3` (chosen on dev). 9 of 64 test cases had at least one repeat with the wrong action.

Each payload sent to Jev is `{"model", "state", "questions"}` (`client.system_one(state=..., questions=..., model=...)`). The `questions` are the same for every case of a shape, so they are printed once per shape at the end; each case shows its `state` exactly as sent.

## g42/single/absent/mail-connections-misses

- **Expected:** asked  **Got (3 repeats):** objected, objected, objected
- **Shape:** single message
- **Jev's answers (repeat 1/2/3):** mechanism_stated [0.1, 0.11, 0.1], contradicted [0.59, 0.62, 0.64], problem_described [0.96, 0.95, 0.96]

**state:**

```text
Our mail provider rejects some of our transactional emails with 'too many connections' errors. I've researched this and decided to switch our email templates to a compiled template engine so each email renders faster. Can you write the welcome email in the new engine's syntax?
```

## g42/single/absent/lock-timeouts-misses

- **Expected:** asked  **Got (3 repeats):** objected, objected, objected
- **Shape:** single message
- **Jev's answers (repeat 1/2/3):** mechanism_stated [0.33, 0.31, 0.31], contradicted [0.34, 0.36, 0.35], problem_described [0.95, 0.95, 0.95]

**state:**

```text
Our order service logs 'lock wait timeout exceeded' errors every evening. I've researched this and decided to add an index on the orders table's created_at column. Can you write the migration that creates the index without locking the table?
```

## g42/single/absent/dns-failures-misses

- **Expected:** asked  **Got (3 repeats):** objected, objected, objected
- **Shape:** single message
- **Jev's answers (repeat 1/2/3):** mechanism_stated [0.1, 0.11, 0.13], contradicted [0.67, 0.72, 0.7], problem_described [0.96, 0.96, 0.96]

**state:**

```text
Our worker pods log 'name resolution failed' errors several times an hour. I've researched this and decided to move the workers to nodes with twice the CPU and memory. Can you write the node pool definition for the larger nodes?
```

## g42/single/absent/cold-starts-fits

- **Expected:** asked  **Got (3 repeats):** none, none, none
- **Shape:** single message
- **Jev's answers (repeat 1/2/3):** mechanism_stated [0.83, 0.81, 0.8], contradicted [0.09, 0.08, 0.09], problem_described [0.94, 0.94, 0.94]

**state:**

```text
The first request to our serverless prediction API after a quiet period takes about eight seconds. I've researched this and decided to keep warm instances with provisioned concurrency so the model is not loaded on each cold start. Can you write the provisioned concurrency setting for the function?
```

## g42/single/absent/french-tickets-fits

- **Expected:** asked  **Got (3 repeats):** asked, asked, none
- **Shape:** single message
- **Jev's answers (repeat 1/2/3):** mechanism_stated [0.64, 0.68, 0.7], contradicted [0.07, 0.07, 0.07], problem_described [0.92, 0.91, 0.91]

**state:**

```text
Support tickets written in French wait about three days for a first reply; English ones wait a few hours. I've researched this and decided to route tickets detected as French to a French queue that the French-speaking agents watch. Can you write the routing rule that uses the detected language?
```

## g42/late_answered/mail-connections

- **Expected:** none  **Got (3 repeats):** none, none, objected
- **Shape:** conversation
- **Jev's answers (repeat 1/2/3):** mechanism_stated [0.99, 0.99, 0.99], contradicted [0.22, 0.23, 0.3], problem_described [0.99, 0.99, 0.98]

**state:**

```text
CONVERSATION SO FAR:
USER: Our mail provider rejects some of our transactional emails with 'too many connections' errors. I've researched this and decided to send all mail through one relay that keeps a pool of at most 40 connections to the provider. Can you write the app-side client that hands mail to the relay?

ASSISTANT: How did you confirm the rejections are caused by your app exceeding the provider's concurrent-connection limit, and that the limit is at or above 40, so that a pooled relay would stop them?

LATEST REQUEST (the user turn to judge):
Each of our 40 app servers opens its own connections to the provider at peak, about 400 at once, and the provider allows 50 per account. Go ahead.
```

## g42/late_absent/cold-starts-fits

- **Expected:** asked  **Got (3 repeats):** none, none, asked
- **Shape:** conversation
- **Jev's answers (repeat 1/2/3):** mechanism_stated [0.74, 0.7, 0.69], contradicted [0.13, 0.13, 0.12], problem_described [0.84, 0.85, 0.86]

**state:**

```text
CONVERSATION SO FAR:
USER: The first request to our serverless prediction API after a quiet period takes about eight seconds. I've researched this and decided to keep warm instances with provisioned concurrency so the model is not loaded on each cold start. First, can you write the scheduled scaling that lowers it overnight?

ASSISTANT: I'm assuming AWS Lambda, since "provisioned concurrency" is Lambda's term. Scheduled scaling for it goes through Application Auto Scaling. If you're on something else, tell me and I'll adapt it.

## Terraform

```hcl
variable "function_name" { default = "prediction-api" }
variable "alias_name"    { default = "live" }   # must be an alias or version, not $LATEST

locals {
  day_concurrency   = 10   # business-hours warm instances
  night_concurrency = 1    # overnight floor
  tz                = "America/New_York"
}

resource "aws_appautoscaling_target" "lambda_pc" {
  service_namespace  = "lambda"
  scalable_dimension = "lambda:function:ProvisionedConcurrency"
  resource_id        = "function:${var.function_name}:${var.alias_name}"
  min_capacity       = local.day_concurrency
  max_capacit
[...]
cheduling 6 AM for a 7–8 AM ramp leaves plenty of margin.
- **Weekends.** If traffic is also low then, add a separate pair of actions, e.g. `cron(0 20 ? * FRI *)` to scale down and `cron(0 6 ? * MON *)` to scale up.
- **Traffic above the warm pool.** Requests beyond provisioned concurrency still hit cold starts. If daytime load varies, add a target-tracking policy on `LambdaProvisionedConcurrencyUtilization` with a min/max range instead of a fixed number. Scheduled actions can then shift that range.
- **Deployments.** Provisioned concurrency is tied to the alias's version. Whenever you publish a new version and repoint the alias, the new version has to warm up, so deploy outside the scale-up window.

If you tell me your actual traffic pattern and timezone, I can tune the numbers and times.

USER: Now the metric for how many requests hit a cold instance.

ASSISTANT: Lambda already publishes the metric you want when you use provisioned concurrency: **`ProvisionedConcurrencySpilloverInvocations`**. It counts invocations that didn't fit in the warm pool and ran on regular on-demand concurrency, which is where your 8-second cold starts will come from. It needs no instrumentation.

Treat it as an upper bound. A spillover invocation can land on an on-demand environment that's already warm, so not every one is a true cold start. The log-based count below gives the exact number.

## Alarm on spillover (Terraform)

```hcl
resource "aws_cloudwatch_metric_alarm" "pc_spillover" {
  alarm_name          = "${var.function_name}-pc-spillover"
  namespace           = "AWS/Lambda"
  metric_name         = "ProvisionedConcurrencySpilloverInvocations"
  dimensions = {
   
[...]
On provisioned concurrency, the init runs ahead of time, but the first invocation on each environment may still report it in `REPORT`. So the log count can include warm-up events that no user waited on. For user-facing cold starts, trust spillover first and use the log count to see how long those inits took. Compare the two on your own function before relying on either alone.
- **The metric filter only works with the default text log format.** If you've enabled JSON logging, `REPORT` lines become `platform.report` events, and you'd filter on `$.type = "platform.report"` and `$.record.metrics.initDurationMs`.
- **Deploys will show up.** Publishing a new version and repointing the alias causes a burst of inits. Annotate deploys on the dashboard so they aren't mistaken for a capacity problem.

LATEST REQUEST (the user turn to judge):
Can you write the provisioned concurrency setting for the function?
```

## g42/late_absent/french-tickets-fits

- **Expected:** asked  **Got (3 repeats):** none, asked, asked
- **Shape:** conversation
- **Jev's answers (repeat 1/2/3):** mechanism_stated [0.71, 0.66, 0.68], contradicted [0.05, 0.05, 0.05], problem_described [0.67, 0.72, 0.71]

**state:**

```text
CONVERSATION SO FAR:
USER: Support tickets written in French wait about three days for a first reply; English ones wait a few hours. I've researched this and decided to route tickets detected as French to a French queue that the French-speaking agents watch. First, can you write the language detection step for incoming tickets?

ASSISTANT: Here's a detection step in Python using [`lingua-py`](https://github.com/pemistahl/lingua-py). I picked it because it handles short texts (which tickets often are) better than `langdetect` or `langid`, and it returns confidence scores you can threshold.

```python
import re
from dataclasses import dataclass
from lingua import Language, LanguageDetectorBuilder

# Include languages you actually receive, plus common look-alikes, so that
# e.g. Spanish or Italian tickets don't get forced into "French" or "English".
CANDIDATES = [
    Language.ENGLISH, Language.FRENCH, Language.SPANISH, Language.GERMAN,
    Language.ITALIAN, Language.PORTUGUESE, Language.DUTCH,
]

_detector = LanguageDetectorBuilder.from_languages(*CANDIDATES).build()

MIN_CHARS = 20            # below this, detection is unreli
[...]
re's a length floor and a locale fallback. If you don't have locale data, drop that fallback.
- **Mixed-language tickets** (e.g., French with pasted English error messages) are handled reasonably by the cleaning step, but you may want to look at what ends up in the default queue.
- **Failure mode:** anything uncertain goes to the default queue, so a misdetection costs you the current wait time rather than losing the ticket. If French agents have spare capacity, you could instead lean toward `support-fr` for borderline cases.

Before launching, I'd run this on a few hundred historical tickets that already have a known language and tune `FRENCH_THRESHOLD` against the actual precision and recall. I can write that evaluation script next, or the routing and queue-assignment step, if you'd like.

USER: Now the French queue's notification to its agents.

ASSISTANT: Here's the notification step. I assumed Slack incoming webhooks, since I don't know your chat or helpdesk stack. `post_to_channel` is the only Slack-specific piece, so it's easy to swap for Teams, email, or your helpdesk's own notifications.

```python
import os
import time
import logging
from datetime import datetime, timezone, timedelta

import httpx
import redis

log = logging.getLogger("fr_notifications")

FR_WEBHOOK_URL = os.environ["SLACK_FR_QUEUE_WEBHOOK"]
ESCALATION_WEBHOOK_URL = os.environ["SLACK_FR_ESCALATION_WEBHOOK"]
TICKET_URL = "https://support.example.com/tickets/{id}"

PREVIEW_CHARS = 140
REMINDER_AFTER = timedelta(minutes=60)   # unclaimed this long -> escalate
FALLBACK_AFTER = timedelta(hours=4)      # unclaimed this long -> return to default queue

_redis = redis.Redis.f
[...]
 is fine at low volume. If French tickets arrive in bursts, consider batching into a digest every few minutes, or pinging only for high-priority tickets and relying on the channel's queue view for the rest.
- **Privacy:** the preview puts customer text into Slack. If tickets can contain personal or payment details, drop the preview block and show only the subject and a link, or check whether your Slack retention policy is acceptable for that data.
- **Business hours:** this doesn't account for them. If the French agents work set hours, add a check so out-of-hours tickets don't trigger reminders overnight. Count age in business hours, or hold the first reminder until the shift starts.

I can write the business-hours handling next, or the evaluation script for tuning the detection threshold.

LATEST REQUEST (the user turn to judge):
Can you write the routing rule that uses the detected language?
```

## g42/late_answered/french-tickets

- **Expected:** none  **Got (3 repeats):** objected, objected, objected
- **Shape:** conversation
- **Jev's answers (repeat 1/2/3):** mechanism_stated [0.97, 0.97, 0.97], contradicted [0.32, 0.34, 0.36], problem_described [0.97, 0.96, 0.96]

**state:**

```text
CONVERSATION SO FAR:
USER: Support tickets written in French wait about three days for a first reply; English ones wait a few hours. I've researched this and decided to route tickets detected as French to a French queue that the French-speaking agents watch. Can you write the routing rule that uses the detected language?

ASSISTANT: How did you confirm that the three-day wait comes from French tickets landing in a queue where French-speaking agents don't see them, rather than from something like too few French-speaking agents or a backlog on their side?

LATEST REQUEST (the user turn to judge):
Our routing rules send every ticket to the English queue, the English-speaking agents skip the French ones, and the two agents who read French check that queue once a day. Go ahead.
```

## questions sent with every single message

```json
{
  "request": {
    "type": "choice",
    "instructions": "A user wrote this to an assistant. What kind of request is it?",
    "criteria": {
      "fix": "The user describes a problem (something failing, slow, wrong, or missing a target) and asks for help building a plan meant to solve it.",
      "task": "The user asks for help with a piece of work that is a requirement in itself, not a response to a problem whose cause is in question (a migration, a backfill, enforcing a limit, adding a capability).",
      "other": "Anything else: a question, a discussion, no plan to build."
    }
  },
  "link": {
    "type": "choice",
    "instructions": "Judged only from what the user's own text says, how is the user's plan linked to the cause of their problem? The user's own account of the cause counts as evidence: a measurement, an observation, \"we traced it\", or a plain statement of what causes the problem. Do not second-guess whether their diagnosis is right.",
    "criteria": {
      "contradicted": "The facts or requirements the user states show the plan will not achieve what they need: it acts on something other than the cause they describe, or cannot meet a requirement they state. General worries, best practice and missing safeguards are not contradictions.",
      "absent": "The request is a fix, and the text names a symptom and a plan but never says what is causing the problem, so nothing connects the plan to the cause.",
      "stated": "Everything else: the text says what causes the problem and the plan acts on it; or the request is a task the plan can meet; or there is no plan."
    }
  },
  "is_fix": {
    "type": "noul",
    "instructions": "Does the user describe a problem (something failing, slow, wrong, or missing a target) and ask for help building a plan meant to solve it?",
    "criteria": {
      "true": "Yes: a problem plus a plan to fix it.",
      "false": "No: a task that is a requirement in itself, a question, or a discussion."
    }
  },
  "problem_described": {
    "type": "noul",
    "instructions": "Does the user describe something going wrong: something failing, slow, wrong, broken, or missing a target they care about? Work the user wants done for its own sake (a migration, a new feature, a compliance requirement, an upgrade) is not something going wrong.",
    "criteria": {
      "true": "Yes: the user describes a problem.",
      "false": "No: the user wants work done, and nothing is described as going wrong."
    }
  },
  "cause_stated": {
    "type": "noul",
    "instructions": "Does the user's text say WHY the problem happens? A measurement, an observation, \"we traced it\", or a plain statement of the cause all count. Could a reader point to a sentence that says why?",
    "criteria": {
      "true": "Yes: a sentence in the user's text states the cause.",
      "false": "No: the text names a symptom and a plan but never says what causes the problem."
    }
  },
  "contradicted": {
    "type": "noul",
    "instructions": "Do the facts or requirements the user states show the plan will not achieve what they need, because it acts on something other than the cause they describe or cannot meet a requirement they state? General worries, best practice and missing safeguards do not count.",
    "criteria": {
      "true": "Yes: the user's own statements conflict with the plan.",
      "false": "No: nothing the user states conflicts with the plan."
    }
  },
  "mechanism_stated": {
    "type": "noul",
    "instructions": "Does the user state a fact about their own system, data or process that explains why the problem happens: for example how much or how often something runs, what a component does, or what a measurement, trace or log showed? The name or type of the error or symptom (such as \"rate-limit errors\", \"out-of-memory crashes\", \"timeouts\") only says what the problem is, not why it happens, and does not count. The plan the user has chosen does not count either.",
    "criteria": {
      "true": {
        "meaning": "Yes: beyond the symptom and the plan, the user states a fact that explains why the problem happens.",
        "examples": [
          "Our push notifications arrive hours late. Our sender batches them and only flushes the batch every three hours.",
          "Nightly backups fail with timeout errors. They copy 2 TB over a link capped at 50 Mbit/s, which takes longer than the eight-hour window."
        ]
      },
      "false": {
        "meaning": "No: the user names the problem, perhaps by its error type, and a plan, but states no fact that explains why it happens.",
        "examples": [
          "Our image-resizing service throws out-of-memory errors. I've decided to give it more memory.",
          "Our booking API returns connection-refused errors at peak. I've decided to raise the database connection pool limit."
        ]
      }
    }
  },
  "cause_outside_plan": {
    "type": "noul",
    "instructions": "Leaving aside the plan the user has chosen, does the user say what causes the problem? A cause that appears only inside the plan does not count: \"clear the stuck cache\" implies a stuck cache, but does not say the user found one.",
    "criteria": {
      "true": {
        "meaning": "Yes: a sentence other than the plan says what causes the problem.",
        "examples": [
          "Our nightly backups time out because they copy 2 TB over a 50 Mbit/s link. I've decided to send only changed blocks."
        ]
      },
      "false": {
        "meaning": "No: the only sign of a cause is in the plan itself, or there is none.",
        "examples": [
          "Our booking API returns errors at peak. I've decided to raise the database connection pool limit.",
          "Our push notifications arrive late. I've decided to flush the notification batch every minute instead of every three hours."
        ]
      }
    }
  }
}
```

## questions sent with every conversation

```json
{
  "request": {
    "type": "choice",
    "instructions": "A user wrote this to an assistant. What kind of request is it? The text is a conversation: judge the LATEST REQUEST in the light of the user's turns taken together. Evidence stated in any earlier user turn counts. Assistant turns are context only: a cause the assistant suggested is not the user's evidence unless the user confirmed it. If the assistant asked how the user knows the plan addresses the cause and the user answered, that answer is the user's evidence.",
    "criteria": {
      "fix": "The user describes a problem (something failing, slow, wrong, or missing a target) and asks for help building a plan meant to solve it.",
      "task": "The user asks for help with a piece of work that is a requirement in itself, not a response to a problem whose cause is in question (a migration, a backfill, enforcing a limit, adding a capability).",
      "other": "Anything else: a question, a discussion, no plan to build."
    }
  },
  "link": {
    "type": "choice",
    "instructions": "Judged only from what the user's own text says, how is the user's plan linked to the cause of their problem? The user's own account of the cause counts as evidence: a measurement, an observation, \"we traced it\", or a plain statement of what causes the problem. Do not second-guess whether their diagnosis is right. The text is a conversation: judge the LATEST REQUEST in the light of the user's turns taken together. Evidence stated in any earlier user turn counts. Assistant turns are context only: a cause the assistant suggested is not the user's evidence unless the user confirmed it. If the assistant asked how the user knows the plan addresses the cause and the user answered, that answer is the user's evidence.",
    "criteria": {
      "contradicted": "The facts or requirements the user states show the plan will not achieve what they need: it acts on something other than the cause they describe, or cannot meet a requirement they state. General worries, best practice and missing safeguards are not contradictions.",
      "absent": "The request is a fix, and the text names a symptom and a plan but never says what is causing the problem, so nothing connects the plan to the cause.",
      "stated": "Everything else: the text says what causes the problem and the plan acts on it; or the request is a task the plan can meet; or there is no plan."
    }
  },
  "is_fix": {
    "type": "noul",
    "instructions": "Does the user describe a problem (something failing, slow, wrong, or missing a target) and ask for help building a plan meant to solve it? The text is a conversation: judge the LATEST REQUEST in the light of the user's turns taken together. Evidence stated in any earlier user turn counts. Assistant turns are context only: a cause the assistant suggested is not the user's evidence unless the user confirmed it. If the assistant asked how the user knows the plan addresses the cause and the user answered, that answer is the user's evidence.",
    "criteria": {
      "true": "Yes: a problem plus a plan to fix it.",
      "false": "No: a task that is a requirement in itself, a question, or a discussion."
    }
  },
  "problem_described": {
    "type": "noul",
    "instructions": "Does the user describe something going wrong: something failing, slow, wrong, broken, or missing a target they care about? Work the user wants done for its own sake (a migration, a new feature, a compliance requirement, an upgrade) is not something going wrong. The text is a conversation: judge the LATEST REQUEST in the light of the user's turns taken together. Evidence stated in any earlier user turn counts. Assistant turns are context only: a cause the assistant suggested is not the user's evidence unless the user confirmed it. If the assistant asked how the user knows the plan addresses the cause and the user answered, that answer is the user's evidence.",
    "criteria": {
      "true": "Yes: the user describes a problem.",
      "false": "No: the user wants work done, and nothing is described as going wrong."
    }
  },
  "cause_stated": {
    "type": "noul",
    "instructions": "Does the user's text say WHY the problem happens? A measurement, an observation, \"we traced it\", or a plain statement of the cause all count. Could a reader point to a sentence that says why? The text is a conversation: judge the LATEST REQUEST in the light of the user's turns taken together. Evidence stated in any earlier user turn counts. Assistant turns are context only: a cause the assistant suggested is not the user's evidence unless the user confirmed it. If the assistant asked how the user knows the plan addresses the cause and the user answered, that answer is the user's evidence.",
    "criteria": {
      "true": "Yes: a sentence in the user's text states the cause.",
      "false": "No: the text names a symptom and a plan but never says what causes the problem."
    }
  },
  "contradicted": {
    "type": "noul",
    "instructions": "Do the facts or requirements the user states show the plan will not achieve what they need, because it acts on something other than the cause they describe or cannot meet a requirement they state? General worries, best practice and missing safeguards do not count. The text is a conversation: judge the LATEST REQUEST in the light of the user's turns taken together. Evidence stated in any earlier user turn counts. Assistant turns are context only: a cause the assistant suggested is not the user's evidence unless the user confirmed it. If the assistant asked how the user knows the plan addresses the cause and the user answered, that answer is the user's evidence.",
    "criteria": {
      "true": "Yes: the user's own statements conflict with the plan.",
      "false": "No: nothing the user states conflicts with the plan."
    }
  },
  "mechanism_stated": {
    "type": "noul",
    "instructions": "Does the user state a fact about their own system, data or process that explains why the problem happens: for example how much or how often something runs, what a component does, or what a measurement, trace or log showed? The name or type of the error or symptom (such as \"rate-limit errors\", \"out-of-memory crashes\", \"timeouts\") only says what the problem is, not why it happens, and does not count. The plan the user has chosen does not count either. The text is a conversation: judge the LATEST REQUEST in the light of the user's turns taken together. Evidence stated in any earlier user turn counts. Assistant turns are context only: a cause the assistant suggested is not the user's evidence unless the user confirmed it. If the assistant asked how the user knows the plan addresses the cause and the user answered, that answer is the user's evidence.",
    "criteria": {
      "true": {
        "meaning": "Yes: beyond the symptom and the plan, the user states a fact that explains why the problem happens.",
        "examples": [
          "Our push notifications arrive hours late. Our sender batches them and only flushes the batch every three hours.",
          "Nightly backups fail with timeout errors. They copy 2 TB over a link capped at 50 Mbit/s, which takes longer than the eight-hour window."
        ]
      },
      "false": {
        "meaning": "No: the user names the problem, perhaps by its error type, and a plan, but states no fact that explains why it happens.",
        "examples": [
          "Our image-resizing service throws out-of-memory errors. I've decided to give it more memory.",
          "Our booking API returns connection-refused errors at peak. I've decided to raise the database connection pool limit."
        ]
      }
    }
  },
  "cause_outside_plan": {
    "type": "noul",
    "instructions": "Leaving aside the plan the user has chosen, does the user say what causes the problem? A cause that appears only inside the plan does not count: \"clear the stuck cache\" implies a stuck cache, but does not say the user found one. The text is a conversation: judge the LATEST REQUEST in the light of the user's turns taken together. Evidence stated in any earlier user turn counts. Assistant turns are context only: a cause the assistant suggested is not the user's evidence unless the user confirmed it. If the assistant asked how the user knows the plan addresses the cause and the user answered, that answer is the user's evidence.",
    "criteria": {
      "true": {
        "meaning": "Yes: a sentence other than the plan says what causes the problem.",
        "examples": [
          "Our nightly backups time out because they copy 2 TB over a 50 Mbit/s link. I've decided to send only changed blocks."
        ]
      },
      "false": {
        "meaning": "No: the only sign of a cause is in the plan itself, or there is none.",
        "examples": [
          "Our booking API returns errors at peak. I've decided to raise the database connection pool limit.",
          "Our push notifications arrive late. I've decided to flush the notification batch every minute instead of every three hours."
        ]
      }
    }
  }
}
```
