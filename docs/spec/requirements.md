# Requirements Document

## Introduction

SwapLoop is a Discord-based, multi-party item-swapping system for college students. Each student is represented by a personal software Agent that registers the items they have and need, their free meeting windows, and their campus. Agents cooperate to find directed swap loops (cycles where each participant gives an item the next participant needs), resolve time, value, and campus conflicts, and ask each student to confirm before the loop locks. No money changes hands.

The graph rule used consistently throughout: an edge X → Y means "X has an item that Y needs, so X gives it to Y." A swap loop is a directed cycle in this graph.

The system is designed for a hackathon demo runnable by one person in about 12 hours of build time, with a deterministic seed scenario as the end-to-end acceptance test.

## Glossary

- **SwapLoop_Bot**: The Discord bot that hosts all per-student Agents and coordinates the matching, loop-finding, conflict-resolution, and confirmation flows.
- **Agent**: A per-student software agent that owns one student's Have_Item, Need_Item, Free_Window, and Campus, and negotiates on that student's behalf.
- **Have_Item**: An item a student owns and offers to trade, recorded with a condition and an approximate value in USD.
- **Need_Item**: An item a student wants to receive in trade.
- **Free_Window**: A day and a start-end time range during which a student is available to meet. Time zone is America/Phoenix.
- **Campus**: The campus name where a student is located (e.g., Tempe).
- **Swap_Graph**: The directed graph in which an edge X → Y means "X has an item that Y needs, so X gives it to Y."
- **Swap_Loop**: A directed cycle in the Swap_Graph representing a complete multi-party trade.
- **Loop_Finder**: The deterministic component that builds the Swap_Graph and enumerates 2-, 3-, and 4-way cycles.
- **Matcher**: The component that normalizes item names and resolves aliases so Have_Items and Need_Items can be matched.
- **Pending_Loop**: A Swap_Loop that has been found and is awaiting confirmation from all participants.
- **Value_Gap**: The absolute difference between the approximate value a student gives and the value the student receives within a Swap_Loop.
- **Time_Conflict**: A condition where the intersection of all participants' Free_Windows contains fewer than 30 minutes.
- **Swap_Room**: The #swap-room Discord channel where Agents post anonymous item listings and final confirmed plans.
- **Demo_Console**: The #demo-console Discord channel where one operator answers Agent questions for simulated students via labeled buttons.
- **GUILD_ID**: The environment variable identifying the single Discord guild to which slash commands are registered.

## Requirements

### Requirement 1: Guild-Scoped Slash Command Registration

**User Story:** As a developer, I want slash commands registered to a single guild so that they appear immediately for the demo without a global propagation delay.

#### Acceptance Criteria

1. WHEN the SwapLoop_Bot starts with a valid GUILD_ID and DISCORD_TOKEN, THE SwapLoop_Bot SHALL register all slash commands to the guild identified by GUILD_ID.
2. THE SwapLoop_Bot SHALL expose the slash commands /have, /need, /free, /campus, /status, and /demo with /demo supporting seed and reset subcommands.
3. IF the GUILD_ID or DISCORD_TOKEN environment variable is missing, THEN THE SwapLoop_Bot SHALL refuse to start and SHALL log a message naming the missing variable.

### Requirement 2: Item Registration Commands

**User Story:** As a student, I want to register items I have and items I need so that my Agent can find swaps for me.

#### Acceptance Criteria

1. WHEN a student invokes /have with an item name, a condition, and an approximate value in USD, THE Agent SHALL store a Have_Item for that student.
2. WHEN a student invokes /need with an item name, THE Agent SHALL store a Need_Item for that student.
3. WHEN a Have_Item or Need_Item is stored, THE Agent SHALL confirm the registration to the student with a message restating the stored item name, condition, and value (for Have_Item).

### Requirement 3: Availability and Campus Commands

**User Story:** As a student, I want to declare when I am free and which campus I am on so that meetings can be scheduled.

#### Acceptance Criteria

1. WHEN a student invokes /free with a day and a start-end time, THE Agent SHALL store a Free_Window for that student in the America/Phoenix time zone.
2. WHEN a student invokes /campus with a name, THE Agent SHALL store the Campus for that student.
3. IF the start time is not earlier than the end time for a /free invocation, THEN THE Agent SHALL reject the Free_Window and SHALL ask the student to re-enter it.

### Requirement 4: Status Command

**User Story:** As a student, I want to see my current registration so that I can verify my data is correct.

#### Acceptance Criteria

1. WHEN a student invokes /status, THE Agent SHALL reply with that student's Have_Items, Need_Items, Free_Windows, and Campus.

### Requirement 5: Item Name Normalization and Matching

**User Story:** As a developer, I want item names normalized and aliased so that the same item is matched across students even when worded differently.

#### Acceptance Criteria

1. WHEN a Have_Item or Need_Item name is received, THE Matcher SHALL normalize the name by lowercasing, trimming, and singularizing.
2. WHERE an alias is defined in the alias map, THE Matcher SHALL map the input name to the canonical name (e.g., "calc textbook" to "calculus textbook", "fridge" to "mini-fridge").
3. THE Matcher SHALL consider a Have_Item and a Need_Item matched WHEN their normalized canonical names are equal.

### Requirement 6: Anonymous Public Posting

**User Story:** As a student, I want my items posted anonymously so that my identity is protected until a loop is confirmed.

#### Acceptance Criteria

1. WHEN an Agent has a registered Have_Item, THE Agent SHALL post a listing to the Swap_Room using an anonymous label (Agent A, Agent B, and so on) that includes the item, condition, approximate value, Campus, and Free_Windows.
2. THE Agent SHALL NOT include a student's name or full schedule in a Swap_Room listing until a Swap_Loop containing that student is confirmed.

### Requirement 7: Loop Finder

**User Story:** As a developer, I want a deterministic loop finder so that swap loops are found without AI and produce repeatable results.

#### Acceptance Criteria

1. THE Loop_Finder SHALL build the Swap_Graph from all Have_Items and Need_Items, with an edge X → Y existing when X has an item that matches Y's Need_Item.
2. THE Loop_Finder SHALL enumerate all 2-, 3-, and 4-way directed cycles in the Swap_Graph.
3. WHEN multiple cycles exist, THE Loop_Finder SHALL prefer the shortest cycle first, then the cycle with the smallest total Value_Gap.
4. THE Loop_Finder SHALL ensure a Have_Item belongs to only one Pending_Loop at a time.

### Requirement 8: Time Conflict Resolution

**User Story:** As a student, I want meeting times that work for everyone so that the swap can actually happen.

#### Acceptance Criteria

1. WHILE forming a Pending_Loop, THE Agent SHALL compute the intersection of all participants' Free_Windows.
2. IF the intersection contains at least 30 minutes, THEN THE Agent SHALL set the meeting time to the midpoint of the shared window.
3. IF the intersection contains fewer than 30 minutes (Time_Conflict), THEN THE Agent SHALL propose the window most participants share and SHALL ask the other participants' Agents to request that their students accept the proposed window.

### Requirement 9: Value Gap Resolution

**User Story:** As a student, I want to know when a trade is uneven so that I can decide whether to accept it.

#### Acceptance Criteria

1. WHILE forming a Pending_Loop, THE Agent SHALL compute each participant's Value_Gap as the difference between the value given and the value received.
2. IF a participant's Value_Gap exceeds $25 or 50% of the value given, THEN that participant's Agent SHALL ask the student to accept the gap or add an item.

### Requirement 10: Campus Conflict Resolution

**User Story:** As a student, I want a meeting place when participants are on different campuses so that we know where to meet.

#### Acceptance Criteria

1. WHILE forming a Pending_Loop, IF participants' Campuses differ, THEN THE Agent SHALL propose a meeting spot from a fixed list per campus (Tempe: Memorial Union, Hayden Library).

### Requirement 11: Confirmation Flow

**User Story:** As a student, I want to confirm a swap before it is finalized so that I am not committed to a trade I do not want.

#### Acceptance Criteria

1. WHEN a Pending_Loop is formed and all conflicts are resolved, THE Agent SHALL ask each participant with Accept and Decline buttons.
2. THE Pending_Loop SHALL lock only WHEN every participant accepts.
3. WHEN the Pending_Loop locks, THE Agent SHALL post the final plan (who gives what to whom, meeting time, and place) to the Swap_Room and to each participant.

### Requirement 12: Decline Handling

**User Story:** As a developer, I want declines to release items so that they can be matched in other loops.

#### Acceptance Criteria

1. IF any participant declines a Pending_Loop, THEN THE Agent SHALL release the Pending_Loop and its Have_Items and SHALL search for loops again.

### Requirement 13: Demo Seed

**User Story:** As a demonstrator, I want a single command to load four simulated students so that I can run the full demo scenario.

#### Acceptance Criteria

1. WHEN the demonstrator invokes /demo seed, THE SwapLoop_Bot SHALL load four simulated students with the following data:
   - Shreyas: Have_Item calculus textbook (good, $40); Need_Item mini-fridge; Free_Window Thu 4-6 PM; Campus Tempe.
   - Rohan: Have_Item mini-fridge (good, $60); Need_Item bike lock; Free_Window Tue 2-5 PM only; Campus Tempe.
   - Bhavisha: Have_Item bike lock (good, $15); Need_Item desk lamp; Free_Window Thu 3-5 PM; Campus Tempe.
   - Shravani: Have_Item desk lamp (good, $20); Need_Item calculus textbook; Free_Window Thu 4-7 PM; Campus Tempe.
2. THE Demo_Console SHALL present Agent questions with buttons labeled by student so that one operator can answer for all four simulated students.

### Requirement 14: Demo Reset

**User Story:** As a demonstrator, I want to clear all data so that I can restart the demo cleanly.

#### Acceptance Criteria

1. WHEN the demonstrator invokes /demo reset, THE SwapLoop_Bot SHALL clear all students, Have_Items, Need_Items, Free_Windows, Campuses, and Pending_Loops.

### Requirement 15: Command-Line Simulation

**User Story:** As a developer, I want a command-line simulation so that I can test the full flow without Discord as a backup for the demo.

#### Acceptance Criteria

1. WHEN `python -m swaploop.simulate` is run, THE SwapLoop_Bot SHALL execute the demo seed and full negotiation without Discord and SHALL print all Agent messages to standard output.
2. THE command-line simulation SHALL produce the same Swap_Loop, conflict resolutions, and final plan as the Discord demo for the same seed.

### Requirement 16: Secrets and Configuration

**User Story:** As a developer, I want secrets kept out of code so that the project is safe to share.

#### Acceptance Criteria

1. THE SwapLoop_Bot SHALL read DISCORD_TOKEN and GUILD_ID only from environment variables.
2. THE SwapLoop_Bot SHALL NOT write secrets to logs or source files.

### Requirement 17: Audit Logging

**User Story:** As a developer, I want every Agent message logged so that the demo is auditable.

#### Acceptance Criteria

1. WHEN an Agent sends any message to a participant or to the Swap_Room, THE SwapLoop_Bot SHALL log that message to the Swap_Room.

### Requirement 18: Unit Tests

**User Story:** As a developer, I want unit tests for core logic so that regressions are caught before the demo.

#### Acceptance Criteria

1. THE project SHALL include pytest unit tests for the Matcher, the Loop_Finder, and each conflict check (time, value, and campus).

### Requirement 19: Demo Seed Acceptance Test

**User Story:** As a demonstrator, I want the seed scenario to produce a known result so that I can verify the whole system works.

#### Acceptance Criteria

1. WHEN /demo seed is run, THE Loop_Finder SHALL find exactly one 4-way Swap_Loop: Shreyas → Shravani → Bhavisha → Rohan → Shreyas.
2. WHEN the loop is formed, THE Agent SHALL detect a Time_Conflict for Rohan and SHALL propose Thu 4-5 PM, the window the other three participants share.
3. WHEN the loop is formed, THE Agent SHALL detect a Value_Gap for Rohan (gives $60, receives $15).
4. WHEN Rohan accepts Thursday and the Value_Gap, THE Agent SHALL lock the loop for Thu 4:30 PM at Memorial Union and SHALL post the final plan.

## Non-Functional Requirements

- **NFR-1 (Reliability):** THE SwapLoop_Bot SHALL produce a repeatable demo result for the seed scenario across runs.
- **NFR-2 (Build Time):** THE system SHALL be implementable by one developer in approximately 12 hours.
- **NFR-3 (Persistence):** THE SwapLoop_Bot SHALL store all state in SQLite.
- **NFR-4 (Documentation):** THE project SHALL include a README with setup steps and demo steps.
- **NFR-5 (Stack):** THE project SHALL use Python 3.11+, discord.py 2.x, SQLite, and pytest, with no paid APIs.

## Out of Scope

- Natural-language parsing of item names with an LLM (optional later add-on behind a feature flag; out of MVP).
- Money or payments of any kind.
- Real-time notifications beyond Discord messages.
- Swap loops larger than 4-way.
- Scheduling across time zones beyond America/Phoenix.
- Multiple guild support.
- Production deployment, scaling, or uptime guarantees.
- Authentication beyond Discord's built-in identity.

## Assumptions

- The demo is run by one person who controls all four simulated students via the Demo_Console; real DMs are used only for real (non-seeded) users.
- Item condition is a free-text label (e.g., "good", "fair") used only for display, not for matching.
- Approximate value is an integer USD amount used only for Value_Gap checks, not for any payment.
- The alias map is a small, hard-coded dictionary maintained in source; it is not user-editable in the MVP.
- "Singularize" uses a simple rule-based transformation; perfect grammatical correctness is not required.
- The fixed campus meeting-spot list contains only Tempe entries (Memorial Union, Hayden Library) for the MVP; other campuses are not needed for the demo.
- Free_Window days are represented as weekday names (e.g., "Thu") and times in a 12-hour format with AM/PM, matching the demo's "Thu 4-6 PM" style input.
- The meeting time "midpoint" of a window means the clock-time midpoint (e.g., 4-5 PM produces 4:30 PM), not a time-zone-aware instant.
- Slash commands are scoped to one guild and are guild-local, not globally registered.
- The Swap_Room and Demo_Console channels (#swap-room and #demo-console) are created manually in the demo guild before running the bot.
- "Search again" after a decline re-runs the Loop_Finder over all non-pending items and may re-propose the same loop if it remains the best option, or a different one.
- All four seed students are on the Tempe campus; the campus conflict path is exercised only if non-seeded users on other campuses are added. For the locked demo loop, the meeting spot is Memorial Union.
- "Total Value_Gap" used as the loop-finder tiebreaker means the sum of absolute per-participant Value_Gaps in a loop. This tiebreaker does not affect the seed acceptance test, which has exactly one loop.
- The Value_Gap threshold "50%" is measured against the value given (e.g., Rohan gives $60; 50% is $30; the $45 gap exceeds both $25 and $30).
- The 4-way loop direction "Shreyas → Shravani → Bhavisha → Rohan → Shreyas" follows the graph rule (edge X → Y means X gives to Y); the final plan states who gives what to whom accordingly.
