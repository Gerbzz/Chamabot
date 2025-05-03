# -*- coding: utf-8 -*-
import random
import bot
from nextcord.errors import DiscordException

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
		self.timeout = self.m.cfg.get('map_vote_timeout', 60*3)  # Default to 3 minutes if not set

		if len(self.m.cfg['maps']) > 1 and self.m.cfg['vote_maps']:
			self.maps = self.m.random_maps(self.m.cfg['maps'], self.m.cfg['vote_maps'], self.m.queue.last_maps)
			self.map_votes = [set() for i in self.maps]
			self.m.states.append(self.m.MAP_VOTE)

	async def think(self, frame_time):
		if frame_time > self.m.start_time + self.timeout:
			ctx = bot.SystemContext(self.m.qc)
			await self.finish(ctx)

	async def start(self, ctx):
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
		if self.message:
			bot.waiting_reactions.pop(self.message.id)
			await self.message.delete()

		if self.maps:
			order = list(range(len(self.maps)))
			random.shuffle(order)
			order.sort(key=lambda n: len(self.map_votes[n]), reverse=True)
			self.m.maps = [self.maps[n] for n in order[:self.m.cfg['map_count']]]

		await self.m.next_state(ctx) 