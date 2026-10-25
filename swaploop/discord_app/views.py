"""Accept/Decline buttons. They carry loop and student ids in the custom id, so they
keep working after a restart."""

import discord

from swaploop.discord_app.formatting import MAX_MESSAGE_LENGTH, button_label, outcome_note, truncate
from swaploop.models import Student


def can_answer_for(student: Student, discord_user_id: int) -> bool:
    """Real students answer for themselves; simulated ones are answered by the operator."""
    return student.discord_id is None or student.discord_id == str(discord_user_id)


class AnswerButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"swaploop:(?P<loop>\d+):(?P<student>\d+):(?P<answer>accept|decline)",
):
    def __init__(self, loop_id: int, student_id: int, accepted: bool, student_name: str | None = None):
        self.loop_id = loop_id
        self.student_id = student_id
        self.accepted = accepted
        super().__init__(
            discord.ui.Button(
                label=button_label(accepted, student_name),
                style=discord.ButtonStyle.success if accepted else discord.ButtonStyle.danger,
                custom_id=f"swaploop:{loop_id}:{student_id}:{'accept' if accepted else 'decline'}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["loop"]), int(match["student"]), match["answer"] == "accept")

    async def callback(self, interaction: discord.Interaction) -> None:
        engine = interaction.client.engine
        try:
            student = engine.db.get_student(self.student_id)
        except KeyError:
            await interaction.response.send_message("This prompt is no longer active.", ephemeral=True)
            return
        if not can_answer_for(student, interaction.user.id):
            await interaction.response.send_message("This prompt is for someone else.", ephemeral=True)
            return

        outcome = engine.answer(self.loop_id, self.student_id, self.accepted)
        original = truncate(interaction.message.content, MAX_MESSAGE_LENGTH - 120)
        await interaction.response.edit_message(
            content=f"{original}\n\n**{student.name}:** {outcome_note(outcome)}", view=None
        )


def build_answer_view(loop_id: int, student_id: int, student_name: str | None = None) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(AnswerButton(loop_id, student_id, True, student_name))
    view.add_item(AnswerButton(loop_id, student_id, False, student_name))
    return view
