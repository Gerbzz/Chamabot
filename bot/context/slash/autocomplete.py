from typing import List
from nextcord import Interaction

from core.utils import find, get

import bot


async def queues(interaction: Interaction, queue: str) -> List[str]:
	# Get the current command name to determine context
	command_name = interaction.data.get('name', '')
	
	# For global queue embeds, show queues from all channels with channel info
	if command_name in ['global-queue-embed', 'remove-global-queue-embed']:
		all_queues = []
		for qc in bot.queue_channels.values():
			for q in qc.queues:
				if q.name.lower().startswith(queue.lower()):
					# Add channel information in parentheses
					channel = interaction.client.get_channel(qc.id)  # Get the actual TextChannel object
					channel_name = channel.name if channel else "unknown-channel"
					all_queues.append(f"{q.name} (#{channel_name})")
		return all_queues[:25]  # Limit to 25 results
	
	# Standard behavior for commands operating on the current channel only
	if (qc := bot.queue_channels.get(interaction.channel_id)) is not None:
		return [q.name for q in qc.queues if q.name.startswith(queue)]
	else:
		return []


async def qc_variables(interaction: Interaction, variable: str) -> List[str]:
	return sorted([v for v in bot.QueueChannel.cfg_factory.variables.keys() if v.startswith(variable)])[:10]


async def queue_variables(interaction: Interaction, variable: str) -> List[str]:
	if (qc := bot.queue_channels.get(interaction.channel_id)) is None:
		return []
	interaction_queue = find(lambda i: i['name'] == 'queue', interaction.data['options'][0]['options'])
	if interaction_queue and (queue := get(qc.queues, name=interaction_queue['value'])):
		return sorted([v for v in queue.cfg_factory.variables.keys() if v.startswith(variable)])[:10]
	return []


async def match_ids(interaction: Interaction, match_id: str) -> List[int]:
	if (qc := bot.queue_channels.get(interaction.channel_id)) is None:
		return []
	return [m.id for m in bot.active_matches if m.qc == qc]


async def teams_by_author(interaction: Interaction, name: str) -> List[str]:
	if (match := find(lambda m: interaction.user in m.players, bot.active_matches)) is not None:
		return [team.name for team in match.teams[:2] if team.name.startswith(name)]
	return ['active match not found']


async def teams_by_match_id(interaction: Interaction, name: str) -> List[str]:
	interaction_match = find(lambda i: i['name'] == 'match_id', interaction.data['options'][0]['options'])
	if interaction_match and (match := get(bot.active_matches, id=interaction_match['value'])):
		return [team.name for team in match.teams[:2] if team.name.startswith(name)]
	return ['incorrect match_id supplied']
