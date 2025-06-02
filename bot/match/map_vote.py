# -*- coding: utf-8 -*-
import random
import bot
from nextcord.errors import DiscordException
import time

from core.utils import join_and
from core.console import log


class MapVote:

	INT_EMOJIS = [
		"1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "0️⃣",  # Discord's built-in keycap emojis for 1-10
		"<:keycap_eleven:1379164982570254347>", "<:keycap_twelve:1379165019803226334>", 
		"<:keycap_thirteen:1379165123402530967>", "<:keycap_fourteen:1379165199872823457>", 
		"<:keycap_fifteen:1379165448154906835>", "<:keycap_sixteen:1379165525569175649>", 
		"<:keycap_seventeen:1379165571895001130>", "<:keycap_eighteen:1379165693735342100>", 
		"<:keycap_nineteen:1379165770378117270>"  # Your custom emojis for 11-19
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