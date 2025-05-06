# -*- coding: utf-8 -*-
import traceback
import json
from nextcord import Interaction, Embed, ButtonStyle
from nextcord.ui import View, Button
import logging
import nextcord.ext.commands
import asyncio

from core.console import log
from core.database import db
from core.config import cfg
from core.utils import error_embed, ok_embed, get, find
from core.client import dc

import bot

# Configure Nextcord logging
logging.getLogger('nextcord').setLevel(logging.WARNING)
logging.getLogger('nextcord.client').setLevel(logging.WARNING)
logging.getLogger('nextcord.gateway').setLevel(logging.WARNING)


async def enable_channel(message):
	if not (message.author.id == cfg.DC_OWNER_ID or message.channel.permissions_for(message.author).administrator):
		await message.channel.send(embed=error_embed(
			"One must posses the guild administrator permissions in order to use this command."
		))
		return
	if message.channel.id not in bot.queue_channels.keys():
		bot.queue_channels[message.channel.id] = await bot.QueueChannel.create(message.channel)
		await message.channel.send(embed=ok_embed("The bot has been enabled."))
	else:
		await message.channel.send(
			embed=error_embed("The bot is already enabled on this channel.")
		)


async def disable_channel(message):
	if not (message.author.id == cfg.DC_OWNER_ID or message.channel.permissions_for(message.author).administrator):
		await message.channel.send(embed=error_embed(
			"One must posses the guild administrator permissions in order to use this command."
		))
		return
	qc = bot.queue_channels.get(message.channel.id)
	if qc:
		for queue in qc.queues:
			await queue.cfg.delete()
		await qc.cfg.delete()
		bot.queue_channels.pop(message.channel.id)
		await message.channel.send(embed=ok_embed("The bot has been disabled."))
	else:
		await message.channel.send(embed=error_embed("The bot is not enabled on this channel."))


def update_qc_lang(qc_cfg):
	bot.queue_channels[qc_cfg.p_key].update_lang()


def update_rating_system(qc_cfg):
	bot.queue_channels[qc_cfg.p_key].update_rating_system()


def save_state():
	log.info("Saving state...")
	queues = []
	queue_embeds_data = {}
	
	for qc in bot.queue_channels.values():
		for q in qc.queues:
			if q.length > 0:
				queues.append(q.serialize())
			# Save queue embed data
			channel_key = f"{q.name}_{qc.id}"
			if channel_key in qc.queue_embeds:
				if qc.id not in queue_embeds_data:
					queue_embeds_data[qc.id] = {}
				queue_embeds_data[qc.id][q.name] = qc.queue_embeds[channel_key]

	matches = []
	for match in bot.active_matches:
		matches.append(match.serialize())

	state_data = {
		'queues': queues,
		'matches': matches,
		'allow_offline': bot.allow_offline,
		'expire': bot.expire.serialize(),
		'queue_embeds': queue_embeds_data,
		'global_queue_embeds': bot.commands.queues.global_queue_embeds
	}

	try:
		with open("saved_state.json", 'w') as f:
			json.dump(state_data, f, indent=2)
		log.info("State saved successfully")
	except Exception as e:
		log.error(f"Failed to save state: {str(e)}")


async def load_state():
	# First try to load the state file
	try:
		with open("saved_state.json", "r") as f:
			data = json.loads(f.read())
	except IOError:
		log.info("No saved state found")
		return
	except json.JSONDecodeError as e:
		log.error(f"Failed to parse saved state: {str(e)}")
		return
	except Exception as e:
		log.error(f"Unexpected error loading state file: {str(e)}")
		return

	log.info("Loading state...")

	try:
		bot.allow_offline = list(data.get('allow_offline', []))

		# First, recreate all queue channels
		if 'queue_embeds' in data:
			for channel_id, queues in data['queue_embeds'].items():
				channel_id = int(channel_id)
				channel = dc.get_channel(channel_id)
				if channel and channel_id not in bot.queue_channels:
					try:
						bot.queue_channels[channel_id] = await bot.QueueChannel.create(channel)
						log.info(f"Recreated queue channel for {channel.guild.name}>#{channel.name}")
					except Exception as e:
						log.error(f"Failed to recreate queue channel {channel_id}: {str(e)}")

		# Then load queue states
		for qd in data.get('queues', []):
			if qd.get('queue_type') in ['PickupQueue', None]:
				try:
					await bot.PickupQueue.from_json(qd)
				except bot.Exc.ValueError as e:
					log.error(f"Failed to load queue state ({qd.get('queue_id')}): {str(e)}")
			else:
				log.error(f"Got unknown queue type '{qd.get('queue_type')}'.")

		for md in data.get('matches', []):
			try:
				await bot.Match.from_json(md)
			except bot.Exc.ValueError as e:
				log.error(f"Failed to load match {md['match_id']}: {str(e)}")

		if 'expire' in data:
			await bot.expire.load_json(data['expire'])

		# Store and recreate queue embeds
		if 'queue_embeds' in data:
			for channel_id, queues in data['queue_embeds'].items():
				channel_id = int(channel_id)
				if channel_id in bot.queue_channels:
					qc = bot.queue_channels[channel_id]
					channel = dc.get_channel(channel_id)
					if channel:
						for queue_name, message_id in queues.items():
							try:
								# Store the message ID
								channel_key = f"{queue_name}_{channel_id}"
								qc.queue_embeds[channel_key] = message_id
								
								# Get the queue
								q = find(lambda i: i.name.lower() == queue_name.lower(), qc.queues)
								if not q:
									continue
									
								# Create the view
								view = View(timeout=None)
								join_button = Button(label="Join", style=ButtonStyle.green, custom_id=f"join_{queue_name}")
								leave_button = Button(label="Leave", style=ButtonStyle.red, custom_id=f"leave_{queue_name}")
								join_button.callback = bot.commands.queues.join_callback
								leave_button.callback = bot.commands.queues.leave_callback
								view.add_item(join_button)
								view.add_item(leave_button)
								qc.queue_views[queue_name] = view
								
								# Create the embed
								embed = Embed(
									title=f"{q.name} Queue",
									description="Current queued players:",
									color=0x7289DA
								)
								if len(q.queue):
									embed.add_field(
										name="Players",
										value="\n".join([f"• {player.display_name}" for player in q.queue]),
										inline=False
									)
								else:
									embed.add_field(
										name="Players",
										value="No players in queue",
										inline=False
									)
								
								# Send new embed
								new_message = await channel.send(embed=embed, view=view)
								qc.queue_embeds[channel_key] = new_message.id
								
								# Register the view with the bot
								dc.add_view(view, message_id=new_message.id)
								
								# Start background task to keep embed at bottom
								task_key = f"{channel_id}_{queue_name}"
								if task_key in bot.queue_tasks:
									bot.queue_tasks[task_key].cancel()
								bot.queue_tasks[task_key] = asyncio.create_task(
									bot.commands.queues.keep_embed_at_bottom(channel, queue_name, new_message.id)
								)
								
								# Try to delete the old message
								try:
									old_message = await channel.fetch_message(message_id)
									await old_message.delete()
									log.info(f"Deleted old queue embed for {queue_name}")
								except Exception as e:
									log.error(f"Could not delete old queue embed: {str(e)}")
								
								log.info(f"Recreated queue embed for {queue_name} in {channel.name}")
							except Exception as e:
								log.error(f"Failed to recreate queue embed for {queue_name}: {str(e)}")
		
		# Load global queue embeds data
		if 'global_queue_embeds' in data:
			try:
				bot.commands.queues.load_global_queue_data_from_state(data)
				log.info("Loaded global queue embeds data")
			except Exception as e:
				log.error(f"Failed to load global queue embeds data: {str(e)}")

		log.info("State loaded successfully")
	except Exception as e:
		log.error(f"Failed to load state: {str(e)}")
		return


async def remove_players(*users, reason=None):
	for qc in set((q.qc for q in bot.active_queues)):
		await qc.remove_members(*users, reason=reason)


async def expire_auto_ready(frame_time):
	for user_id, at in list(bot.auto_ready.items()):
		if at < frame_time:
			bot.auto_ready.pop(user_id)
