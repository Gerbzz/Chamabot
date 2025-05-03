# -*- coding: utf-8 -*-
import bot
from core.utils import find
from nextcord import DiscordException
import time


class Draft:

	pick_steps = {
		"a": 0,
		"b": 1
	}

	def __init__(self, match, pick_order, captains_role_id):
		self.m = match
		self.pick_order = [self.pick_steps[i] for i in pick_order] if pick_order else []
		self.captains_role_id = captains_role_id
		self.message = None
		self.sub_queue = []
		self.timeout = self.m.cfg.get('draft_timeout', 30)  # Default to 30 seconds if not set
		self.last_pick_time = 0

		if self.m.cfg['pick_teams'] == "draft":
			self.m.states.append(self.m.DRAFT)

	async def start(self, ctx):
		self.last_pick_time = int(time())
		await self.refresh(ctx)

	async def print(self, ctx):
		try:
			await ctx.notice(embed=self.m.embeds.draft())
		except DiscordException:
			pass

	async def refresh(self, ctx):
		if self.m.state != self.m.DRAFT:
			await self.print(ctx)
		elif len(self.m.teams[2]) and any((len(t) < self.m.cfg['team_size'] for t in self.m.teams)):
			await self.print(ctx)
		else:
			await self.m.next_state(ctx)

	async def cap_me(self, ctx, author):
		if self.m.state != self.m.DRAFT:
			raise bot.Exc.MatchStateError(self.m.gt("The match is not on the draft stage."))

		team = find(lambda t: author in t, self.m.teams)
		if team.idx == 2 or team.index(author) != 0:
			raise bot.Exc.PermissionError(self.m.gt("You are not a captain."))
		if len(team) > 1:
			raise bot.Exc.PermissionError(self.m.gt("Can't do that after you've started picking."))

		team.remove(author)
		self.m.teams[2].add(author)
		await self.print(ctx)

	async def cap_for(self, ctx, author, team_name):
		if self.m.state != self.m.DRAFT:
			raise bot.Exc.MatchStateError(self.m.gt("The match is not on the draft stage."))
		elif self.captains_role_id and self.captains_role_id not in (r.id for r in author.roles):
			raise bot.Exc.PermissionError(self.m.gt("You must possess the captain's role."))
		elif (team := find(lambda t: t.name.lower() == team_name.lower(), self.m.teams[:2])) is None:
			raise bot.Exc.SyntaxError(self.m.gt("Specified team name not found."))
		elif len(team):
			raise bot.Exc.PermissionError(
				self.m.gt(f"Team **{team.name}** already have a captain. The captain must type **/capme** first.")
			)

		find(lambda t: author in t, self.m.teams).remove(author)
		team.insert(0, author)
		await self.print(ctx)

	async def think(self, frame_time):
		if self.m.state != self.m.DRAFT:
			return

		if len(self.m.teams[2]) == 0:
			await self.m.next_state(bot.SystemContext(self.m.qc))
			return

		pick_step = len(self.m.teams[0]) + len(self.m.teams[1]) - 2
		if pick_step >= len(self.pick_order):
			await self.m.next_state(bot.SystemContext(self.m.qc))
			return

		picker_team = self.m.teams[self.pick_order[pick_step]]
		if not picker_team:
			return

		# Check if it's time to auto-pick
		if frame_time > self.last_pick_time + self.timeout:
			# Sort unpicked players by rating
			unpicked_players = sorted(
				self.m.teams[2],
				key=lambda p: self.m.ratings[p.id],
				reverse=True
			)
			if unpicked_players:
				await self.pick(bot.SystemContext(self.m.qc), picker_team[0], unpicked_players[0])
				self.last_pick_time = frame_time  # Update last pick time after auto-pick

	async def pick(self, ctx, captain, player):
		if self.m.state != self.m.DRAFT:
			raise bot.Exc.MatchStateError(self.m.gt("The match must be on the draft stage."))

		pick_step = len(self.m.teams[0]) + len(self.m.teams[1]) - 2
		if pick_step >= len(self.pick_order):
			raise bot.Exc.MatchStateError(self.m.gt("All picks are done."))

		picker_team = self.m.teams[self.pick_order[pick_step]]
		if not picker_team or captain not in picker_team:
			raise bot.Exc.PermissionError(self.m.gt("It's not your turn to pick."))

		if player not in self.m.teams[2]:
			raise bot.Exc.ValueError(self.m.gt("Specified player is not available for picking."))

		# Add player to the team
		picker_team.append(player)
		self.m.teams[2].remove(player)
		self.last_pick_time = int(time())

		await self.print(ctx)

	async def put(self, ctx, player, team_name):
		if (team := find(lambda t: t.name.lower() == team_name.lower(), self.m.teams)) is None:
			raise bot.Exc.SyntaxError(self.m.gt("Specified team name not found."))
		if self.m.state not in [self.m.DRAFT, self.m.WAITING_REPORT]:
			raise bot.Exc.MatchStateError(self.m.gt("The match must be on the draft or waiting report stage."))

		if (old_team := find(lambda t: player in t, self.m.teams)) is not None:
			old_team.remove(player)
		else:
			self.m.players.append(player)
			self.m.ratings = {
				p['user_id']: p['rating'] for p in await self.m.qc.rating.get_players((p.id for p in self.m.players))
			}

		team.append(player)
		await self.m.qc.remove_members(player, ctx=ctx)
		await self.refresh(ctx)

	async def sub_me(self, ctx, author):
		if self.m.state not in [self.m.DRAFT, self.m.WAITING_REPORT]:
			raise bot.Exc.MatchStateError(self.m.gt("The match must be on the draft or waiting report stage."))

		if author in self.sub_queue:
			self.sub_queue.remove(author)
			await ctx.success(self.m.gt("You have stopped looking for a substitute."))
		else:
			self.sub_queue.append(author)
			await ctx.success(self.m.gt("You are now looking for a substitute."))

	async def sub_for(self, ctx, player1, player2, force=False):
		if self.m.state not in [self.m.READY_CHECK, self.m.MAP_VOTE, self.m.DRAFT, self.m.WAITING_REPORT]:
			raise bot.Exc.MatchStateError(self.m.gt("The match must be on the ready check, map vote, draft or waiting report stage."))
		elif not force and player1 not in self.sub_queue:
			raise bot.Exc.PermissionError(self.m.gt("Specified player is not looking for a substitute."))

		team = find(lambda t: player1 in t, self.m.teams)
		team[team.index(player1)] = player2
		self.m.players.remove(player1)
		self.m.players.append(player2)
		if player1 in self.sub_queue:
			self.sub_queue.remove(player1)
		self.m.ratings = {
			p['user_id']: p['rating'] for p in await self.m.qc.rating.get_players((p.id for p in self.m.players))
		}
		await self.m.qc.remove_members(player2, ctx=ctx)
		await bot.remove_players(player2, reason="pickup started")

		if self.m.state == self.m.READY_CHECK:
			await self.m.check_in.refresh()
		elif self.m.state == self.m.MAP_VOTE:
			await self.m.map_vote.refresh()
		elif self.m.state == self.m.WAITING_REPORT:
			await ctx.notice(embed=self.m.embeds.final_message())
		else:
			await self.print(ctx)
