"""Slash commands. Each one maps to a single engine call."""

import logging
from collections.abc import Callable

import discord
from discord import app_commands

from swaploop.demo import demo_key, reset_demo, seed_demo
from swaploop.engine import SwapEngine
from swaploop.models import Student
from swaploop.timeutil import DAYS, format_slot, parse_time_range

log = logging.getLogger(__name__)

MAX_VALUE_USD = 100_000


async def _reply_for_student(
    interaction: discord.Interaction, action: Callable[[SwapEngine, Student], str]
) -> None:
    engine: SwapEngine = interaction.client.engine
    student = engine.student_for_discord(str(interaction.user.id), interaction.user.display_name)
    try:
        text = action(engine, student)
    except ValueError as error:
        text = str(error)
    await interaction.response.send_message(text, ephemeral=True)


def register_commands(tree: app_commands.CommandTree) -> None:
    @tree.command(name="have", description="Offer an item you want to trade away")
    @app_commands.describe(item="What you are offering", condition="For example good or fair",
                           value="Approximate value in USD")
    @app_commands.guild_only()
    async def have(interaction: discord.Interaction, item: str, condition: str,
                   value: app_commands.Range[int, 0, MAX_VALUE_USD]):
        def action(engine: SwapEngine, student: Student) -> str:
            stored = engine.add_have(student.id, item, condition, value)
            return (f"Saved: {stored.name} ({stored.condition}, ${stored.value_usd}). "
                    "It is posted anonymously in the swap room.")
        await _reply_for_student(interaction, action)

    @tree.command(name="need", description="Say which item you are looking for")
    @app_commands.describe(item="What you want to receive")
    @app_commands.guild_only()
    async def need(interaction: discord.Interaction, item: str):
        def action(engine: SwapEngine, student: Student) -> str:
            return f"Saved: you need {engine.add_need(student.id, item).name}."
        await _reply_for_student(interaction, action)

    @tree.command(name="free", description="Add a time you are free to meet (Phoenix time)")
    @app_commands.describe(day="Day of the week", times="For example 4-6 PM")
    @app_commands.choices(day=[app_commands.Choice(name=d, value=d) for d in DAYS])
    @app_commands.guild_only()
    async def free(interaction: discord.Interaction, day: app_commands.Choice[str], times: str):
        def action(engine: SwapEngine, student: Student) -> str:
            start, end = parse_time_range(times)
            window = engine.add_free_window(student.id, day.value, start, end)
            return f"Saved: free {format_slot(window.day, window.start_min, window.end_min)}."
        await _reply_for_student(interaction, action)

    @tree.command(name="campus", description="Set the campus you are on")
    @app_commands.describe(name="For example Tempe")
    @app_commands.guild_only()
    async def campus(interaction: discord.Interaction, name: str):
        def action(engine: SwapEngine, student: Student) -> str:
            engine.set_campus(student.id, name)
            return f"Saved: campus {name.strip()}."
        await _reply_for_student(interaction, action)

    @tree.command(name="status", description="See what your agent has on file for you")
    @app_commands.guild_only()
    async def status(interaction: discord.Interaction):
        await _reply_for_student(interaction, lambda engine, student: engine.status_text(student.id))

    demo = app_commands.Group(
        name="demo", description="Run the scripted demo",
        guild_only=True, default_permissions=discord.Permissions(manage_guild=True),
    )

    @demo.command(name="seed", description="Reset everything and load the four demo students")
    async def demo_seed(interaction: discord.Interaction):
        bot = interaction.client
        await interaction.response.defer(ephemeral=True)
        bot.messenger.post_demo_console("**Demo key**\n" + demo_key())
        seed_demo(bot.engine)
        await interaction.followup.send("Demo seeded. Answer the prompts in the demo console.", ephemeral=True)

    @demo.command(name="reset", description="Clear all students, items and loops")
    async def demo_reset(interaction: discord.Interaction):
        bot = interaction.client
        reset_demo(bot.engine)
        bot.messenger.post_swap_room("Demo reset. Everything has been cleared.")
        await interaction.response.send_message("Everything has been cleared.", ephemeral=True)

    tree.add_command(demo)
