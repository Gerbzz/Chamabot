from nextcord.ext import commands
from .queues import queue_embed

def setup(bot):
    @bot.slash_command(name="queue_embed", description="Create a queue embed with join/leave buttons")
    async def queue_embed_command(interaction, queue_name: str):
        await queue_embed(interaction, queue_name) 