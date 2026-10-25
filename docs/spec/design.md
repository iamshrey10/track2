# SwapLoop Design

Companion to `requirements.md`. Scope is deliberately small: one guild, one
campus list, 2-4 way loops, deterministic logic, SQLite, no paid APIs.

## 1. Principles

- Core logic is pure Python with no Discord imports. It runs from the command
  line and is unit-tested without a network.
- The negotiation engine talks to the outside world only through a
  `Messenger` interface. Discord and the console are two implementations, so
  `python -m swaploop.simulate` and the Discord demo run the same code path.
- Everything is deterministic: same data in, same loop, same messages out.
- Times are weekday + minutes since midnight in America/Phoenix (no DST, so no
  timezone arithmetic is needed).

## 2. Module Layout

```
swaploop/
  config.py        env loading (DISCORD_TOKEN, GUILD_ID, SWAPLOOP_DB, channel names)
  models.py        dataclasses and enums shared by all modules
  timeutil.py      parse/format "Thu", "4-6 PM", minutes <-> "4:30 PM"
  matcher.py       normalize + alias map + match test
  loop_finder.py   build swap graph, enumerate 2-4 cycles, rank
  conflicts.py     time, value and campus checks (pure functions)
  db.py            SQLite schema and repository (the only module that runs SQL)
  engine.py        negotiation state machine, message composition
  messaging.py     Messenger protocol, ConsoleMessenger, RecordingMessenger
  demo.py          seed data, reset
  simulate.py      python -m swaploop.simulate
  discord_app/
    bot.py         client setup, guild command sync, startup checks
    commands.py    /have /need /free /campus /status /demo
    messenger.py   DiscordMessenger: Swap_Room, Demo_Console, DMs
    views.py       Accept/Decline buttons (persistent)
tests/
  test_matcher.py  test_timeutil.py  test_loop_finder.py  test_conflicts.py
  test_db.py       test_engine.py    test_simulate.py     (acceptance)
```

Dependency direction: `discord_app` -> `engine` -> (`loop_finder`,
`conflicts`, `matcher`, `timeutil`, `db`) -> `models`. Nothing in the core
imports `discord_app`.

## 3. SQLite Data Model

All state lives in SQLite (NFR-3). Money is integer USD; times are integer
minutes since midnight; `day` is `Mon`..`Sun`.

```sql
students(
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  discord_id    TEXT UNIQUE,           -- NULL for simulated students
  is_simulated  INTEGER NOT NULL DEFAULT 0,
  campus        TEXT,
  agent_label   TEXT NOT NULL          -- "Agent A", "Agent B", ... by id order
)
have_items(
  id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id),
  name TEXT NOT NULL,                  -- as typed
  canonical TEXT NOT NULL,             -- after Matcher
  condition TEXT NOT NULL,
  value_usd INTEGER NOT NULL,
  loop_id INTEGER REFERENCES loops(id) -- non-NULL while reserved by a loop
)
need_items(
  id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id),
  name TEXT NOT NULL, canonical TEXT NOT NULL,
  loop_id INTEGER REFERENCES loops(id)
)
free_windows(
  id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id),
  day TEXT NOT NULL, start_min INTEGER NOT NULL, end_min INTEGER NOT NULL,
  CHECK (start_min < end_min)
)
loops(
  id INTEGER PRIMARY KEY,
  status        TEXT NOT NULL,         -- PENDING | LOCKED | RELEASED
  signature     TEXT NOT NULL,         -- sorted have_item ids, e.g. "1,4,7,9"
  meeting_day   TEXT, meeting_min INTEGER, meeting_place TEXT,
  conflicts     TEXT NOT NULL,         -- JSON: the computed conflict report
  released_by   INTEGER REFERENCES students(id),
  created_at    TEXT NOT NULL
)
loop_legs(                             -- one row per edge giver -> receiver
  loop_id INTEGER NOT NULL REFERENCES loops(id),
  position INTEGER NOT NULL,           -- 0..n-1 around the cycle
  giver_id INTEGER NOT NULL, receiver_id INTEGER NOT NULL,
  have_item_id INTEGER NOT NULL, need_item_id INTEGER NOT NULL,
  PRIMARY KEY (loop_id, position)
)
confirmations(
  loop_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
  answer TEXT NOT NULL DEFAULT 'PENDING',   -- PENDING | ACCEPTED | DECLINED
  PRIMARY KEY (loop_id, student_id)
)
message_log(
  id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
  channel TEXT NOT NULL,               -- SWAP_ROOM | DEMO_CONSOLE | DM
  recipient_id INTEGER, kind TEXT NOT NULL, body TEXT NOT NULL
)
```

Reservation rule (R7.4): when a loop becomes PENDING, its `have_items.loop_id`
and `need_items.loop_id` are set. The finder only sees unreserved items.
RELEASED clears them; LOCKED keeps them.

`students.agent_label` is assigned from the student's row order ("Agent A" for
the first, then B, C, ...), so labels are stable and anonymous.

## 4. Swap Graph and Loop Finder

Graph rule: **edge X -> Y means X has an item Y needs, so X gives it to Y.**

Inputs: unreserved Have_Items and Need_Items, each carrying a canonical name.

Build:
1. For every ordered pair of distinct students (X, Y), look for an unreserved
   Have_Item of X and an unreserved Need_Item of Y with equal canonical names.
2. If several Have_Items match, take the lowest item id. If several
   Need_Items match, take the lowest id. The edge stores
   `(have_item_id, need_item_id)`.

Enumerate (bounded DFS, depth <= 4):
1. For each start student `s` in ascending id order, DFS over edges, visiting
   only students with id > `s` besides returning to `s`. This yields each
   simple cycle exactly once, rooted at its smallest student id, with no
   rotation duplicates.
2. Record a cycle when an edge returns to `s` and the path length is 2, 3 or 4.
   Stop extending at length 4.
3. A cycle uses each student once, so each participant gives exactly one item
   and receives exactly one.

Rank (R7.3), sort key ascending:
1. number of participants (shortest first)
2. total Value_Gap = sum over participants of |value given - value received|
3. tuple of have_item ids (final tie-break, keeps output repeatable)

Selecting loops: `plan_loops` walks the ranked list, skips any cycle whose
`signature` matches a RELEASED loop, skips cycles that touch an item already
claimed by an earlier pick in this pass, and skips cycles the conflict checks
mark infeasible (section 5). Each pick is a candidate for a new PENDING loop.

Seed check: the graph has exactly four edges, one per student in a ring, so
exactly one 4-cycle exists and no 2- or 3-cycles.

## 5. Conflict Rules

All three are pure functions over a candidate loop and student data. They
return a structured result; the engine turns it into messages.

### Time (R8)

Per participant, windows are grouped by day. For each day:
1. Collect all window boundaries and sweep the elementary segments between
   them. For each segment, count distinct participants covering it.
2. Merge adjacent segments covered by the same participant set.

Resolution, in order:
- **Shared**: some interval is covered by all participants and lasts at least
  30 minutes. Pick the longest, earliest on ties. Meeting time = midpoint.
  No conflict.
- **Time_Conflict**: otherwise, look for the interval of at least 30 minutes
  with the highest coverage count (minimum 2). Longest, then earliest, break
  ties. That is the proposed window; meeting time = its midpoint. The
  participants not covering it are `dissenters`; their agents ask their
  students to accept it.
- **Infeasible**: no 30-minute interval covered by at least 2 participants
  (this includes students with no windows registered). The loop is dropped
  from planning; its items stay free.

Seed: Shreyas Thu 4-6, Bhavisha Thu 3-5, Shravani Thu 4-7 overlap 4-5 PM
(60 min); Rohan has only Tue 2-5. Result: Time_Conflict, proposed Thu 4-5 PM,
meeting 4:30 PM, dissenter Rohan.

### Value (R9)

For each participant: `given` = value of the item they give, `received` =
value of the item they receive, `gap = |given - received|`.

A participant is **flagged** when they are the one losing out and the gap is
large: `received < given` and (`gap > 25` or `gap > 0.5 * given`). Their agent
asks them to accept the gap or add an item. A participant who receives more
than they give is never flagged (see Assumption 1).

Seed: Rohan gives 60, receives 15, gap 45 > 25 and > 30: flagged. The other
three receive more than they give: not flagged.

### Campus (R10)

- All participants on one campus: meeting spot = first entry of that campus's
  list. Tempe: Memorial Union, Hayden Library.
- Campuses differ: use the campus held by most participants (ties: first
  alphabetically) and propose its first spot. Participants on other campuses
  are asked to confirm.
- A campus with no spot list falls back to the Tempe list and is treated as a
  campus conflict.

Seed: all Tempe, so Memorial Union and no question.

## 6. Message Flow

Message kinds: `LISTING` (Swap_Room), `AGENT_NOTE` (Swap_Room, agent-to-agent
coordination), `PROMPT` (to a student, with buttons), `INFO` (to a student),
`FINAL_PLAN` (Swap_Room and each participant).

Privacy: before a loop locks, every message uses agent labels for other
people ("Agent B"). Names appear only in `FINAL_PLAN`. Listings and notes share
item, condition, value, campus and the relevant window, never a full schedule.

Every message the engine sends goes through `Messenger.send(...)`, is written
to `message_log`, and is mirrored to the Swap_Room as an audit line (R17).
Because pre-lock text is already label-only, the audit mirror needs no
redaction.

Engine entry points (called by Discord handlers, the simulator and tests):

| Call | What it does |
| --- | --- |
| `add_have/add_need/add_free/set_campus` | validate, store, post listing for new Have_Item, then `search()` |
| `search()` | run the finder, create PENDING loops, start negotiation |
| `answer(loop_id, student_id, accepted)` | record a confirmation, lock or release |
| `status(student_id)` | formatted registration |

Negotiation for one new loop:
1. Reserve items, insert `loops`, `loop_legs`, and PENDING `confirmations`.
2. Compute time, value and campus results; store them as JSON in `loops`.
3. Post an `AGENT_NOTE` per conflict in the Swap_Room, as one agent speaking
   to the others (e.g. Rohan's agent: "my student is not free in the shared
   window; proposing Thu 4-5 PM, asking my student").
4. Send each participant one `PROMPT` with Accept / Decline: what they give,
   what they get, the meeting time and place. If that student owns a conflict,
   the prompt also states it ("Thu 4:30 PM is outside your window", "you give
   $60 and receive $15, a $45 gap") and Accept means accepting it.
5. `answer(...)`: first answer per student counts, repeats are ignored, answers
   on a non-PENDING loop get an "already closed" reply.
6. All ACCEPTED: status LOCKED, post `FINAL_PLAN` (names, who gives what to
   whom, meeting time and place) to the Swap_Room and every participant.
7. Any DECLINED: status RELEASED, free the items, tell the other participants,
   call `search()` again. The released loop's signature is skipped, so the same
   people are not asked the same question again (Assumption 3).

### Demo seed walk-through

1. `/demo seed` loads the four students (R13), labels A-D in order
   Shreyas, Rohan, Bhavisha, Shravani, and posts four anonymous listings.
2. `search()` finds the single cycle Shreyas -> Shravani -> Bhavisha -> Rohan
   -> Shreyas (A -> D -> C -> B -> A).
3. Conflicts: Time_Conflict (Rohan, proposed Thu 4-5 PM, meeting 4:30 PM),
   Value flag (Rohan, $60 vs $15), campus Memorial Union (no conflict).
4. Swap_Room shows the loop as labels plus two agent notes (time, value).
5. Demo_Console shows four prompts with buttons labeled per student.
6. Operator accepts for Shreyas, Shravani, Bhavisha, then Rohan (whose prompt
   carries the Thursday and value-gap acceptance).
7. Loop locks: Thu 4:30 PM at Memorial Union. Final plan posts with names.

## 7. Demo Mode

- Simulated students have `discord_id = NULL`. The `DiscordMessenger` routes
  their prompts to #demo-console; real users get DMs. A failed DM falls back to
  #demo-console so a closed-DM setting cannot stall the demo.
- Button labels read "Rohan: Accept" and "Rohan: Decline". `custom_id` encodes
  `loop_id:student_id:answer`, using discord.py dynamic items, so buttons keep
  working after a bot restart.
- `/demo seed` runs a full reset first (so labels always start at Agent A),
  posts the label-to-name key in #demo-console, loads the four seed students,
  posts listings, and runs `search()`. `/demo reset` clears every table (R14)
  and posts a confirmation. Loop ids are never reused after a reset, so
  buttons left over from an earlier run cannot answer a new loop.
- Backup: `python -m swaploop.simulate` builds an in-memory database, runs the
  same seed with a `ConsoleMessenger` that prints each message and answers
  prompts in the fixed order above. A test asserts the simulator's final
  loop, conflicts and plan equal the expected seed result, and that two runs
  print identical output.
- Startup fails fast with a clear log line if `DISCORD_TOKEN` or `GUILD_ID` is
  missing (R1.3). Logs never print token values.

## 8. Item Matching

`normalize(name)`: lowercase, trim, collapse whitespace, then singularize the
last word with simple rules (`ies`->`y`, `sses`/`xes`/`ches`/`shes`->drop `es`, trailing `s`
unless `ss`/`us`/`is`). `canonicalize` then applies the alias map, e.g.
`calc textbook` -> `calculus textbook`, `fridge` -> `mini-fridge`. Two items
match when their canonical names are equal. The alias map is a source-level
dict.

## 9. Assumptions That Shape the Design

1. **Value flag only for the loser.** The requirement's 50% rule would also
   flag Shravani (gives $20, receives $40, gap $20 > $10). The demo expects only
   Rohan, and someone receiving more has nothing to accept, so only the
   participant who receives less than they give can be flagged. `Value_Gap`
   stays absolute for ranking.
2. **One prompt per student.** Conflict acceptance and final confirmation are
   combined into one Accept/Decline prompt, so a loop locks after all four
   answer. Rohan's accept is the last click in the demo order.
3. **Declined loops are not re-proposed.** R12 allows the same loop to come
   back; this design skips a loop whose `signature` was released, so a
   decliner is not asked the same thing immediately.
4. **Audit mirror is label-only.** Mirroring student DMs to the Swap_Room
   (R17) would leak names against R6.2, so pre-lock text uses agent labels
   everywhere.
