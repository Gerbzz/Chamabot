import traceback
from nextcord import ChannelType, Activity, ActivityType, Button, ButtonStyle
from nextcord.ui import View

from core.client import dc
from core.console import log
from core.config import cfg
import bot


@dc.event
async def on_init():
	await bot.stats.check_match_id_counter()


@dc.event
async def on_think(frame_time):
	for match in bot.active_matches:
		try:
			await match.think(frame_time)
		except Exception as e:
			log.error("\n".join([
				f"Error at Match.think().",
				f"match_id: {match.id}).",
				f"{str(e)}. Traceback:\n{traceback.format_exc()}=========="
			]))
			bot.active_matches.remove(match)
			break
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
	global bot_was_ready, bot_ready
	if not bot_was_ready:
		log.info("Connecting to discord...")
		bot_was_ready = True
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

	if not bot_ready:
		bot_ready = True
		log.info("Registering existing queue embed views...")
		for qc in bot.queue_channels.values():
			if (channel := dc.get_channel(qc.id)) is not None:
				for queue in qc.queues:
					channel_key = f"{queue.name}_{channel.id}"
					if channel_key in qc.queue_embeds:
						try:
							# Create buttons for the queue
							join_button = Button(
								style=ButtonStyle.green,
								label="Join",
								custom_id=f"join_{queue.name}"
							)
							leave_button = Button(
								style=ButtonStyle.red,
								label="Leave",
								custom_id=f"leave_{queue.name}"
							)

							# Add callbacks to the buttons
							join_button.callback = lambda i: join_queue_callback(i, queue)
							leave_button.callback = lambda i: leave_queue_callback(i, queue)

							# Create the view
							view = View(timeout=None)
							view.add_item(join_button)
							view.add_item(leave_button)

							# Register the view with the bot
							dc.add_view(view, message_id=qc.queue_embeds[channel_key])
							log.info(f"Registered view for queue {queue.name} in channel {channel.name}")
						except Exception as e:
							log.error(f"Failed to register view for queue {queue.name} in channel {channel.name}: {str(e)}")
		log.info("Queue embed view registration complete.")


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
