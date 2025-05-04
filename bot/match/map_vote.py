# -*- coding: utf-8 -*-
import random
import bot
from nextcord.errors import DiscordException
import time

from core.utils import join_and
from core.console import log


class MapVote:

	INT_EMOJIS = [
		"<:Chama_icon_1:1368097341390983280>", "<:Chama_icon_2:1368097320415268894>", "<:Chama_icon_3:1368097292124426301>", 
		"<:Chama_icon_4:1368097269802336256>", "<:Chama_icon_5:1368097249006981181>", "<:Chama_icon_6:1368097226152214559>", 
		"<:Chama_icon_7:1368097203221954621>", "<:Chama_icon_8:1368097172494618684>", "<:Chama_icon_9:1368097150159814819>", 
		"<:Chama_icon_10:1368097114382536705>", "<:Chama_icon_11:1368097092656173076>", "<:Chama_icon_12:1368096763637923850>", 
		"<:Chama_icon_13:1368096741789798430>", "<:Chama_icon_14:1368096718150828042>", "<:Chama_icon_15:1368096694679502901>", 
		"<:Chama_icon_16:1368096590744522752>", "<:Chama_icon_17:1368096572004634705>", "<:Chama_icon_18:1368096550395576340>"
	]

	def __init__(self, match):
		self.m = match
		self.message = None
		self.maps = []
		self.map_votes = []
		self.timeout = self.m.cfg.get('map_vote_timeout', 90)  # Default to 90 seconds if not set
		self.start_time = 0

		if len(self.m.cfg['maps']) > 1 and self.m.cfg['vote_maps']:
			self.maps = self.m.random_maps(self.m.cfg['maps'], self.m.cfg['vote_maps'], self.m.queue.last_maps)
			self.map_votes = [set() for i in self.maps]
			self.m.states.append(self.m.MAP_VOTE)

	async def think(self, frame_time):
		current_time = int(time.time())
		time_elapsed = current_time - self.start_time
		
		if time_elapsed >= self.timeout:
			ctx = bot.SystemContext(self.m.qc)
			await self.finish(ctx)

	async def start(self, ctx):
		self.start_time = int(time.time())
		if not self.maps:
			await self.m.next_state(ctx)
			return

		text = f"!spawn message {self.m.id}"
		self.message = await ctx.channel.send(text)

		emojis = [self.INT_EMOJIS[n] for n in range(len(self.maps))]
		try:
			for emoji in emojis:
				await self.message.add_reaction(emoji)
		except DiscordException:
			pass
		bot.waiting_reactions[self.message.id] = self.process_reaction
		await self.refresh(ctx)

	async def refresh(self, ctx):
		try:
			await self.message.edit(content=None, embed=self.m.embeds.map_vote(self.maps, self.map_votes))
		except DiscordException:
			pass

	async def process_reaction(self, reaction, user, remove=False):
		if self.m.state != self.m.MAP_VOTE or user not in self.m.players:
			return

		if str(reaction) in self.INT_EMOJIS:
			idx = self.INT_EMOJIS.index(str(reaction))
			if idx < len(self.maps):
				if remove:
					self.map_votes[idx].discard(user.id)
				else:
					self.map_votes[idx].add(user.id)
				await self.refresh(bot.SystemContext(self.m.queue.qc))

	async def finish(self, ctx):
		# Count votes and select the map with most votes
		vote_counts = [len(votes) for votes in self.map_votes]
		max_votes = max(vote_counts)
		winning_maps = [self.maps[i] for i, count in enumerate(vote_counts) if count == max_votes]
		
		# If there's a tie, randomly select one of the winning maps
		self.m.maps = [random.choice(winning_maps)]
		
		# Clean up the message
		if self.message:
			try:
				await self.message.delete()
			except DiscordException:
				pass
		
		await self.m.next_state(ctx) 