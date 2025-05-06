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
