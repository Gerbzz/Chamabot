import traceback
from nextcord import ChannelType, Activity, ActivityType, Button, ButtonStyle
from nextcord.ui import View
import asyncio

from core.client import dc
from core.console import log
from core.config import cfg
import bot
from bot.commands.queues import join_callback, leave_callback, keep_embed_at_bottom


@dc.event
async def on_init():
	await bot.stats.check_match_id_counter()


@dc.event
async def on_think(frame_time):
	for match in list(bot.active_matches):  # Iterate over a copy for safe removal
		try:
			await match.think(frame_time)
		except Exception as e:
			log.error("\n".join([
				f"Error during Match.think() for match_id: {match.id}.",
				f"Error: {str(e)}. Traceback:\n{traceback.format_exc()}=========="
			]))
			try:
				log.info(f"Attempting to cancel match {match.id} due to error in on_think's call to match.think().")
				if hasattr(match, 'qc') and match.qc:
					ctx = bot.SystemContext(match.qc)
					await match.cancel(ctx)
				else:
					log.error(f"Cannot cancel match {match.id}: 'qc' attribute not found or is None. Removing directly.")
					if match in bot.active_matches:
						bot.active_matches.remove(match)
			except Exception as cancel_e:
				log.error(f"Error during attempt to cancel match {match.id} after think error: {str(cancel_e)}\n{traceback.format_exc()}==========")
				# If cancellation itself fails, as a last resort, remove it directly.
				if match in bot.active_matches:
					bot.active_matches.remove(match)
			break  # Maintain original behavior of stopping on first error in loop
	await bot.expire.think(frame_time)
	await bot.noadds.think(frame_time)
	await bot.stats.jobs.think(frame_time)
	await bot.expire_auto_ready(frame_time)


@dc.event
async def on_message(message):
	if message.channel.type == ChannelType.private and message.author.id != dc.user.id:
		await message.channel.send(cfg.HELP)

	if message.channel.type != ChannelType.text:
		return

	if message.content == '!enable_pubobot':
		await bot.enable_channel(message)
	elif message.content == '!disable_pubobot':
		await bot.disable_channel(message)


@dc.event
async def on_reaction_add(reaction, user):
	if user.id != dc.user.id and reaction.message.id in bot.waiting_reactions.keys():
		await bot.waiting_reactions[reaction.message.id](reaction, user)


@dc.event
async def on_reaction_remove(reaction, user):  # FIXME: this event does not get triggered for some reason
	if user.id != dc.user.id and reaction.message.channel.id in bot.waiting_reactions.keys():
		await bot.waiting_reactions[reaction.message.id](reaction, user, remove=True)


@dc.event
async def on_ready():
	if not bot.bot_was_ready:
		log.info("Connecting to discord...")
		bot.bot_was_ready = True
	else:
		log.info("Reconnecting to discord...")

	log.info(f"Logged in discord as '{dc.user}'.")
	log.info("Loading queue channels...")
	for qc in bot.queue_channels.values():
		if (channel := dc.get_channel(qc.id)) is not None:
			log.info(f"    Init channel {channel.guild.name}>#{channel.name} successful.")
			await qc.update_info(channel)
		else:
			log.error(f"    Init channel {qc.cfg.cfg_info.get('guild_name')}>#{qc.cfg.cfg_info.get('channel_name')} failed.")

	log.info("Loading state...")
	await bot.load_state()
	log.info("Done.")

	# Don't automatically register queue embed views on startup
	# Users need to manually create queue embeds using the /queue-embed command
	bot.bot_ready = True
	
	# Register global queue embed views
	log.info("Registering global queue embed views...")
	try:
		for key, message_id in bot.commands.queues.global_queue_embeds.items():
			try:
				# Get channel and queue info from the key
				# Format could be either:
				# - global_queue-name_channel-id (legacy)
				# - global_queue-name_channel-id_queue-channel-id (new)
				parts = key.split('_')
				if len(parts) < 3:
					log.error(f"Invalid key format: {key}")
					continue
					
				queue_name = parts[1]
				channel_id = int(parts[2])
				
				# Get the queue channel ID (if available)
				queue_channel_id = None
				if len(parts) >= 4:
					queue_channel_id = int(parts[3])
				
				# Get the channel
				channel = dc.get_channel(channel_id)
				if channel:
					# Create the view with join/leave buttons
					view = View(timeout=None)
					
					# Join button
					join_button = Button(
						style=ButtonStyle.green.value,
						label="Join Queue",
						custom_id=f"global_join_{queue_name}_{queue_channel_id if queue_channel_id else channel_id}"
					)
					join_button.callback = bot.commands.queues.global_join_callback
					view.add_item(join_button)
					
					# Leave button
					leave_button = Button(
						style=ButtonStyle.red.value,
						label="Leave Queue",
						custom_id=f"global_leave_{queue_name}_{queue_channel_id if queue_channel_id else channel_id}"
					)
					leave_button.callback = bot.commands.queues.global_leave_callback
					view.add_item(leave_button)
					
					# Register the view with the bot
					dc.add_view(view, message_id=message_id)
					log.info(f"Registered global view for queue {queue_name} in channel {channel.name}")
				else:
					log.error(f"Could not find channel {channel_id} for global queue embed")
			except Exception as e:
				log.error(f"Failed to register global view for key {key}: {str(e)}")
	except Exception as e:
		log.error(f"Error registering global queue embed views: {str(e)}")
	
	log.info("Global queue embed view registration complete.")


@dc.event
async def on_disconnect():
	log.info("Connection to discord is lost.")
	bot.bot_ready = False


@dc.event
async def on_resumed():
	log.info("Connection to discord is resumed.")
	if bot.bot_was_ready:
		bot.bot_ready = True


@dc.event
async def on_presence_update(before, after):
	if after.raw_status not in ['idle', 'offline']:
		return
	if after.id in bot.allow_offline:
		return

	for qc in filter(lambda i: i.guild_id == after.guild.id, bot.queue_channels.values()):
		if after.raw_status == "offline" and qc.cfg.remove_offline:
			await qc.remove_members(after, reason="offline")

		if after.raw_status == "idle" and qc.cfg.remove_afk and bot.expire.get(qc, after) is None:
			await qc.remove_members(after, reason="afk", highlight=True)


@dc.event
async def on_member_remove(member):
	for qc in filter(lambda i: i.id == member.guild.id, bot.queue_channels.values()):
		await qc.remove_members(member, reason="left guild")
