# SwapLoop

**Personal agents that find multi-party swap loops between students, negotiate time and value conflicts, and lock a trade only when everyone says yes. No money.**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2?logo=discord&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)
![Tests](https://img.shields.io/badge/tests-138%20passing-brightgreen)

Built by **Brew & Build** for the Cubbie Hackathon, Track 2 (Agent-to-Agent Coordination).

**Demo video:** https://drive.google.com/drive/folders/1MRXci4bLnTz7aVHB0ia66TyiiKegA4YQ?usp=drive_link

SwapLoop is a Discord bot where each student gets a personal agent that finds multi-person item swaps on campus. Your agent talks to other students' agents, works out who can trade with whom, sorts out clashes in time, value and place, and only locks a swap once every person has said yes. No money changes hands.

## Built with

| Area | What we used |
| --- | --- |
| Language | Python 3.11+ |
| Chat layer | discord.py 2.x: slash commands, buttons, channels |
| Storage | SQLite |
| Core logic | Graph cycle search for 2-4 way swaps, deterministic conflict checks |
| Testing | pytest: 138 tests, including an end-to-end demo run |

## What we built

- A loop finder that turns "A needs what B has" into complete swap cycles
- Three conflict checks: time, value gap and meeting place
- Accept/Decline confirmation, with release and re-search on a decline
- A one-person demo mode with four simulated students
- A terminal version, `python -m swaploop.simulate`, as a backup

## The problem

Students have things they no longer need and things they need right now: a calculus textbook, a mini-fridge, a bike lock, a desk lamp. Swapping one-for-one rarely works, because the person who wants your textbook almost never has the thing you want. Group chats and marketplace posts turn into a pile of "anyone have...?" messages that nobody keeps track of.

The trade often exists, though, as a loop. Shreyas has a textbook that Shravani needs, Shravani has a lamp that Bhavisha needs, Bhavisha has a bike lock that Rohan needs, and Rohan has the mini-fridge that Shreyas needs. Nobody can see that loop from where they stand. Even when someone does, the four of them still have to agree on a day, a place and whether the deal feels fair. That is the work the agents do.

## How it works

- Each student registers what they have (`/have`), what they need (`/need`), when they are free (`/free`) and their campus (`/campus`). Their agent keeps it in SQLite.
- Listings are posted to `#swap-room` anonymously (Agent A, Agent B, and so on). Names stay hidden until a swap is locked.
- Item names are normalized, so "calc textbook" and "Calculus Textbooks" count as the same thing.
- The loop finder builds a graph where an arrow from X to Y means X has an item Y needs. It looks for cycles of 2, 3 or 4 people. Shorter loops win, and among equal ones the loop with the smallest total value gap wins. There is no AI in this step, so the same data always gives the same answer.
- When a loop is found, the agents check three things:
  - **Time.** If everyone shares at least 30 minutes, they meet at the middle of that window. If not, they propose the window most people share and ask the others to accept it.
  - **Value.** If someone gives away much more than they get back (more than $25 or half of what they give), their agent asks them to accept the gap or add an item.
  - **Place.** If people are on different campuses, the agents pick a meeting spot from a fixed list.
- Every involved student gets an Accept or Decline prompt that spells out what they give, what they get, and anything they are being asked to accept. The loop locks only when everyone accepts. If anyone declines, the items are released and the search runs again without re-asking the same loop.
- When a loop locks, the final plan (who gives what to whom, when and where) goes to `#swap-room` and to each person.

The matching and negotiation logic lives in plain Python modules with no Discord code in them, so it can be tested and run from the command line.

## Setup

You need Python 3.11 or newer and a Discord server you can add a bot to.

### 1. Install

```
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Create the Discord bot

1. In the Discord developer portal, create an application and add a bot to it.
2. Copy the bot token. Keep it private.
3. Invite the bot to your server with the `bot` and `applications.commands` scopes. Give it View Channels and Send Messages. It does not need any privileged intents.
4. In your server, create two text channels named `swap-room` and `demo-console`.
5. Turn on Developer Mode in Discord (User Settings, Advanced), then right-click your server and copy its ID.

### 3. Configure

Copy the example file and fill it in:

```
cp .env.example .env
```

```
DISCORD_TOKEN=<your bot token>
GUILD_ID=<your server id>
```

The remaining lines are optional: `SWAPLOOP_DB` (database file, default `swaploop.db`), `SWAP_ROOM_CHANNEL` and `DEMO_CONSOLE_CHANNEL` (channel names, defaults `swap-room` and `demo-console`). `.env` is git-ignored. Never commit it, and never paste the token into an issue or a chat. If either required value is missing the bot refuses to start and tells you which one.

## Run the bot

```
python -m swaploop.discord_app
```

You should see a line saying six slash commands were registered to your server. They are registered to that one server only, so they show up straight away.

| Command | What it does |
| --- | --- |
| `/have` | Offer an item: name, condition, approximate value in USD |
| `/need` | Say which item you want |
| `/free` | Add a free window, for example Thu and `4-6 PM` (Phoenix time) |
| `/campus` | Set your campus |
| `/status` | Show what your agent has on file |
| `/demo seed` | Reset everything and load the four demo students |
| `/demo reset` | Clear all data |

`/demo` needs the Manage Server permission.

Discord shows who ran a slash command, so if you want to keep listings anonymous, run the student commands in a private channel. The agents' posts in `#swap-room` never include names until a swap locks.

## Run the demo

The demo loads four simulated students whose items form one 4-way loop, and one person answers for all of them.

1. Start the bot as above.
2. Run `/demo seed` in any channel. It wipes any existing data first, so the agents always start at Agent A.
3. Look at `#demo-console`. It shows a key (Agent A is Shreyas, Agent B is Rohan, Agent C is Bhavisha, Agent D is Shravani) and one prompt per student, each with buttons labeled with that student's name.
4. Look at `#swap-room`. It shows four anonymous listings, then the loop the agents found: Agent A to Agent D to Agent C to Agent B and back to Agent A. Below it are the agents' notes:
   - Rohan is only free Tuesday afternoon, so his agent proposes Thursday 4 to 5 PM, the window the other three share, with the meeting at 4:30 PM.
   - Rohan would give a $60 mini-fridge for a $15 bike lock, a $45 gap, so his agent asks him to accept it.
   - Everyone is on Tempe, so the meeting spot is Memorial Union.
5. In `#demo-console`, press Accept for Shreyas, Shravani and Bhavisha. Rohan's prompt lists the time change and the value gap separately. Press Accept for Rohan.
6. The loop locks. The final plan appears in `#swap-room`:
   - Shreyas gives the calculus textbook to Shravani
   - Shravani gives the desk lamp to Bhavisha
   - Bhavisha gives the bike lock to Rohan
   - Rohan gives the mini-fridge to Shreyas
   - Thursday 4:30 PM at Memorial Union

To show a decline, run `/demo seed` again and press Decline for Rohan. The loop is released, the others are told, and the items go back into the pool. Use `/demo reset` to clear everything when you are done.

## Backup: run it without Discord

If Discord is down or the network is bad, the same demo runs in the terminal:

```
python -m swaploop.simulate
```

It seeds the four students, prints every message the agents send, answers the prompts in a fixed order, and ends with the locked plan. It uses the same code as the bot and gives the same result every time. The exit code is 0 when the loop locks.

## Tests

```
pytest
```

The tests cover item matching, the loop finder and ranking, the time, value and campus checks, the database, the negotiation flow (including decline and double clicks), the Discord formatting, and the full demo scenario end to end.

## Project layout

```
swaploop/
  matcher.py       item name cleanup and aliases
  loop_finder.py   swap graph and 2-4 way cycle search
  conflicts.py     time, value and campus checks
  engine.py        registration, negotiation and confirmation
  db.py            SQLite storage
  demo.py          the four-student seed
  simulate.py      terminal version of the demo
  discord_app/     slash commands, channels and buttons
tests/             unit and end-to-end tests
docs/design.md     how the pieces fit together
```

## Limits

- The agents are rule-based and deterministic, with no language model. Natural-language input is a possible next step.
- One server, one campus list (Tempe), loops of up to 4 people.
- Item matching is by name and a small built-in alias list, not by meaning.
- Times are weekday and clock time in Phoenix time.
- `/demo seed` and `/demo reset` clear all data, including real students.

## Team

**Brew & Build**, Arizona State University

Shreyas Revankar, Rohan Waghode, Bhavisha Sondagar and Shravani Kulkarni.

