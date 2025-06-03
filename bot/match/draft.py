# -*- coding: utf-8 -*-
import bot
from core.utils import find
from nextcord import DiscordException
import time
import traceback
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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
		# Get draft timeout from match config, default to 30 seconds if not set
		self.timeout = self.m.cfg.get('draft_timeout', 30)
		self.last_pick_time = 0
		self.auto_pick_warning_sent = False
		self.warning_time = 10  # Seconds before auto-pick to show warning

		if self.m.cfg['pick_teams'] == "draft":
			# Add DRAFT state after MAP_VOTE state if it exists
			if self.m.MAP_VOTE in self.m.states:
				map_vote_index = self.m.states.index(self.m.MAP_VOTE)
				self.m.states.insert(map_vote_index + 1, self.m.DRAFT)
			else:
				self.m.states.append(self.m.DRAFT)

	async def start(self, ctx):
		self.last_pick_time = int(time.time())
		self.auto_pick_warning_sent = False
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
			logger.debug(f"Match {self.m.id} not in draft state, skipping draft think")
			return

		if len(self.m.teams[2]) == 0:
			logger.debug(f"Match {self.m.id} no players left to pick, ending draft")
			await self.m.next_state(bot.SystemContext(self.m.qc))
			return

		pick_step = len(self.m.teams[0]) + len(self.m.teams[1]) - 2
		if pick_step >= len(self.pick_order):
			logger.debug(f"Match {self.m.id} all picks completed, ending draft")
			await self.m.next_state(bot.SystemContext(self.m.qc))
			return

		picker_team = self.m.teams[self.pick_order[pick_step]]
		if not picker_team or not picker_team[0]:
			logger.debug(f"Match {self.m.id} no valid picker team or captain")
			return

		current_time = int(time.time())
		time_elapsed = current_time - self.last_pick_time
		time_remaining = self.timeout - time_elapsed
		
		logger.debug(f"Match {self.m.id} draft state: pick_step={pick_step}, time_elapsed={time_elapsed}, time_remaining={time_remaining}")
		
		# Send warning 10 seconds before auto-pick
		if not self.auto_pick_warning_sent and time_remaining <= self.warning_time and time_remaining > 0:
			try:
				logger.debug(f"Match {self.m.id} sending auto-pick warning to {picker_team[0].name}")
				await bot.SystemContext(self.m.qc).notice(
					self.m.gt("{captain} you have {time} seconds to pick a player, or the highest rated player will be auto-picked.").format(
						captain=picker_team[0].mention,
						time=time_remaining
					)
				)
				self.auto_pick_warning_sent = True
			except Exception as e:
				logger.error(f"Match {self.m.id} error sending auto-pick warning: {str(e)}")

		# Check if it's time to auto-pick
		if time_elapsed >= self.timeout:
			try:
				logger.debug(f"Match {self.m.id} auto-pick triggered for {picker_team[0].name}")
				# Sort unpicked players by rating
				unpicked_players = sorted(
					self.m.teams[2],
					key=lambda p: self.m.ratings[p.id],
					reverse=True
				)
				
				if unpicked_players:
					logger.debug(f"Match {self.m.id} auto-picking {unpicked_players[0].name} for {picker_team.name}")
					# Auto-pick the highest rated player
					await self.pick(bot.SystemContext(self.m.qc), picker_team[0], unpicked_players[0])
					
					# Reset timers
					self.last_pick_time = current_time
					self.auto_pick_warning_sent = False
					
					# Notify about auto-pick
					await bot.SystemContext(self.m.qc).notice(
						self.m.gt("{player} was auto-picked for {team} due to timeout.").format(
							player=unpicked_players[0].mention,
							team=picker_team.name
						)
					)
					
					# Refresh the draft state
					await self.refresh(bot.SystemContext(self.m.qc))
				else:
					logger.debug(f"Match {self.m.id} no players available for auto-pick")
					# No players left to pick, move to next state
					await self.m.next_state(bot.SystemContext(self.m.qc))
					
			except Exception as e:
				logger.error(f"Match {self.m.id} error during auto-pick: {str(e)}\n{traceback.format_exc()}")
				# If auto-pick fails, try to continue the draft
				self.last_pick_time = current_time
				self.auto_pick_warning_sent = False

	async def pick(self, ctx, captain, players):
		""" Pick a player for the captain's team """

		# Handle single player or list of players
		if isinstance(players, list):
			if not players:  # Empty list
				raise bot.Exc.ValueError(self.m.gt("No player specified"))
			player = players[0]  # Take first player from list
		else:
			player = players

		# Log pick attempt details
		logger.info("===== PICK ATTEMPT DEBUG =====")
		logger.info(f"Captain {captain.name} attempting to pick {player.name}")
		logger.info(f"Match state: {self.m.state}")
		logger.info(f"Team 0 ({self.m.teams[0].name}): {[p.name for p in self.m.teams[0]]}")
		logger.info(f"Team 1 ({self.m.teams[1].name}): {[p.name for p in self.m.teams[1]]}")
		logger.info(f"Available players: {[p.name for p in self.m.teams[2]]}")
		logger.info(f"All players in match: {[p.name for p in self.m.players]}")

		# Check match state
		if self.m.state != self.m.DRAFT:
			logger.error(f"Invalid match state: {self.m.state}")
			raise bot.Exc.MatchStateError(self.m.gt("The match must be on the draft stage."))

		# Calculate and validate pick step
		pick_step = len(self.m.teams[0]) + len(self.m.teams[1]) - 2
		logger.info(f"Current pick step: {pick_step}, Pick order length: {len(self.pick_order)}")
		if pick_step >= len(self.pick_order):
			logger.error(f"Pick step {pick_step} exceeds pick order length {len(self.pick_order)}")
			raise bot.Exc.MatchStateError(self.m.gt("All picks are done."))

		# Validate picker team and captain
		picker_team = self.m.teams[self.pick_order[pick_step]]
		logger.info(f"Picker team: {picker_team.name}")
		logger.info(f"Expected captain: {picker_team[0].name if picker_team and picker_team[0] else 'None'}")
		logger.info(f"Actual captain: {captain.name}")

		# Check captain permissions
		if not picker_team or captain != picker_team[0]:
			logger.error(f"Captain mismatch - Expected: {picker_team[0].name if picker_team and picker_team[0] else 'None'}, Got: {captain.name}")
			raise bot.Exc.PermissionError(self.m.gt("It's not your turn to pick. Only the captain can pick."))

		# Validate player availability
		logger.info(f"Checking if {player.name} is in teams[2] (available players)")
		# Debug: Print the actual contents of teams[2]
		logger.info(f"teams[2] contents: {[str(p) for p in self.m.teams[2]]}")
		logger.info(f"Player object to find: {str(player)}")
		
		# Check if player objects are actually the same
		for available_player in self.m.teams[2]:
			logger.info(f"Comparing with available player: {str(available_player)}")
			logger.info(f"IDs match? {available_player.id == player.id}")
		
		if player not in self.m.teams[2]:
			logger.error(f"Player {player.name} (ID: {player.id}) not available for picking")
			# Check if player is in match at all
			if player not in self.m.players:
				logger.error(f"Player {player.name} (ID: {player.id}) not in match players list")
				logger.error(f"Match players: {[(p.name, p.id) for p in self.m.players]}")
				raise bot.Exc.ValueError(self.m.gt("Player {player} is not part of this match.").format(player=player.name))
			
			# Check if player is already on a team
			for i, team in enumerate(self.m.teams[:2]):
				if player in team:
					logger.error(f"Player {player.name} already on team {team.name}")
					raise bot.Exc.ValueError(self.m.gt("Player {player} is already on team {team}.").format(
						player=player.name,
						team=team.name
					))
			
			# Check if player objects might be different instances
			for available_player in self.m.teams[2]:
				if available_player.id == player.id:
					logger.error(f"Found player with matching ID but different object instance")
					# Use the instance from teams[2]
					player = available_player
					break
			
			# If we still haven't found the player
			logger.error(f"Player {player.name} in unexpected state - in match but not in any team or available pool")
			logger.error(f"Current teams state:")
			for i, team in enumerate(self.m.teams):
				logger.error(f"Team {i}: {[(p.name, p.id) for p in team]}")
			raise bot.Exc.ValueError(self.m.gt("Player is in an invalid state. Please report this to an admin."))

		# Add player to the team
		logger.info(f"Adding {player.name} to {picker_team.name}")
		picker_team.append(player)
		
		# Make sure teams[2] is still a Team object
		if not isinstance(self.m.teams[2], self.m.Team):
			logger.warning(f"teams[2] is not a Team object, recreating it")
			unpicked = list(self.m.teams[2])  # Save current players
			self.m.teams[2] = self.m.Team(name="unpicked", emoji="📋", idx=-1)  # Recreate Team object
			self.m.teams[2].extend(unpicked)  # Restore players
		
		# Remove player from unpicked pool
		logger.info(f"Removing {player.name} from unpicked pool")
		self.m.teams[2].remove(player)
		
		# Reset timers
		self.last_pick_time = int(time.time())
		self.auto_pick_warning_sent = False
		
		# Log final team states
		logger.info(f"Final team states after pick:")
		for i, team in enumerate(self.m.teams):
			logger.info(f"Team {i} ({team.name}): {[p.name for p in team]}")
		
		# Update the display
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
