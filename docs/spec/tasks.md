# SwapLoop Tasks

Each task is 30-60 minutes, built tests-first, and ends with passing tests.
Estimated total: about 11 hours. Requirement numbers refer to `requirements.md`.

## Core logic (no Discord)

1. **Project scaffold and config.** `pyproject.toml` (Python 3.11+, discord.py
   2.x, pytest), `swaploop/` and `tests/` packages, `config.py` reading
   `DISCORD_TOKEN`, `GUILD_ID`, `SWAPLOOP_DB`, channel names from the
   environment, `.env.example` with placeholder names only, `*.db` in
   `.gitignore`. Test: missing variable names the variable. (R1.3, R16)

2. **Models and time utilities.** `models.py` dataclasses and enums;
   `timeutil.py` parsing "Thu", "4-6 PM", "4:30 PM" and formatting minutes.
   Reject start >= end. Tests for parsing and formatting. (R3.3)

3. **Matcher.** Normalize, singularize, alias map, match test. Tests for
   case, whitespace, plurals, both example aliases, and a non-match. (R5, R18)

4. **SQLite repository.** `db.py` schema from the design, create/read helpers
   for students, items, windows, loops, legs, confirmations, message log,
   reservation and release, full reset. Tests on an in-memory database.
   (NFR-3, R14)

5. **Swap graph and cycle enumeration.** Build edges from unreserved items,
   enumerate 2-, 3- and 4-cycles once each, ignore 5+. Tests: each length, no
   rotation duplicates, no self-edges, no cycle when one link is missing.
   (R7.1, R7.2)

6. **Ranking and loop selection.** Value gap per participant, ranking by
   length then total gap then item ids, claim of items across picks, skip of
   released signatures. Tests including a case where a shorter loop beats a
   cheaper longer one and the full seed (exactly one 4-way loop, in the
   expected order). (R7.3, R7.4, R19.1)

7. **Time conflict check.** Sweep per day, shared window, best-coverage
   proposal, infeasible case, midpoint. Tests: all-shared, seed (Thu 4-5 PM,
   4:30 PM, Rohan dissents), no overlap at all, windows under 30 minutes,
   missing windows. (R8, R19.2)

8. **Value and campus checks.** Per-participant gap and flag rule, campus spot
   selection with mixed and unknown campuses. Tests: Rohan flagged, receivers
   of more value not flagged, $25 and 50% boundaries, same campus, mixed
   campus, unknown campus. (R9, R10, R19.3)

## Negotiation and command line

9. **Messenger interface and engine, happy path.** `messaging.py` with
   `Messenger`, `RecordingMessenger`, `ConsoleMessenger`; `engine.py` add
   item/window/campus, listings, `search()`, loop creation, prompts,
   agent notes, label-only text, audit log. Test with a recording messenger
   on the seed. (R2, R3, R6, R17)

10. **Engine confirmation, lock and decline.** `answer()` with first-answer-wins,
    lock when all accept and final plan to Swap_Room and participants,
    release on decline and re-search, closed-loop replies. Tests for lock at
    Thu 4:30 PM at Memorial Union, decline path, double click. (R11, R12, R19.4)

11. **Demo seed and command-line simulation.** `demo.py` seed and reset,
    `python -m swaploop.simulate` printing every message and answering in the
    fixed order. Acceptance test: loop order, Rohan's time and value
    conflicts, final plan, identical output across two runs. (R13, R14, R15,
    NFR-1)

## Discord layer

12. **Bot skeleton and registration commands.** `discord_app/bot.py` with
    startup variable check and guild-scoped sync; `/have`, `/need`, `/free`,
    `/campus`, `/status` calling the engine; error replies for bad input.
    Manual check in the test guild. (R1, R2, R3, R4)

13. **Discord messenger, buttons and channels.** `DiscordMessenger` for
    #swap-room (listings, notes, audit, final plan), DMs for real users,
    persistent Accept/Decline dynamic items wired to `engine.answer()`.
    Manual check with one real user. (R6, R11, R17)

14. **Demo mode in Discord.** `/demo seed` and `/demo reset`, #demo-console
    routing for simulated students with per-student button labels, DM
    fallback to the console, restart-safe buttons. Full manual run of the
    seed ending in the locked plan. (R13, R14)

## Wrap-up

15. **README and demo rehearsal.** README with setup (bot creation, intents,
    channels, environment variables), run steps, demo script, the simulator
    backup, and how to run the tests. Walk through the demo twice from a
    clean reset and fix anything rough. (NFR-4)
