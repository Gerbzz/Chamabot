__all__ = [
	'add', 'remove', 'who', 'add_player', 'remove_player', 'promote', 'start', 'split',
	'reset', 'subscribe', 'server', 'maps', 'queue_embed', 'recreate_queue_embeds'
]

import time
from random import choice
from nextcord import Member, Embed, Button, ButtonStyle, ActionRow
from nextcord.ui import View, Button
from core.utils import error_embed, join_and, find, seconds_to_str
from core.client import dc
from core.console import log
import bot
import asyncio
import json
import logging

# Global dictionaries for queue management
queue_tasks = {}  # Store active tasks
queue_channels = {}  # Store queue channels
queue_views = {}  # Store queue views
queue_embeds = {}  # Store queue embeds

async def update_queue_embed(ctx, queue_name):
	"""Update the queue embed with current players"""
	try:
		# Get the queue channel
		qc = ctx.qc
		if not qc:
			log.error("No queue channel found")
			return

		# Get the queue
		q = find(lambda i: i.name.lower() == queue_name.lower(), qc.queues)
		if not q:
			log.error(f"Could not find queue {queue_name}")
			return

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

		# Create the view
		view = View(timeout=None)
		join_button = Button(label="Join", style=ButtonStyle.green, custom_id=f"join_{queue_name}")
		leave_button = Button(label="Leave", style=ButtonStyle.red, custom_id=f"leave_{queue_name}")
		join_button.callback = join_callback
		leave_button.callback = leave_callback
		view.add_item(join_button)
		view.add_item(leave_button)
		qc.queue_views[queue_name] = view

		# Get the current message ID
		channel_key = f"{queue_name}_{ctx.channel.id}"
		message_id = qc.queue_embeds.get(channel_key)

		if message_id:
			try:
				# Try to update existing message
				message = await ctx.channel.fetch_message(message_id)
				if message:
					await message.edit(embed=embed, view=view)
					return
			except Exception as e:
				log.error(f"Failed to update message {message_id}: {str(e)}")

		# If message doesn't exist or update failed, send a new one
		new_message = await ctx.channel.send(embed=embed, view=view)
		qc.queue_embeds[channel_key] = new_message.id

		# Start background task to keep embed at bottom
		task_key = f"{ctx.channel.id}_{queue_name}"
		if task_key in bot.queue_tasks:
			bot.queue_tasks[task_key].cancel()
		bot.queue_tasks[task_key] = asyncio.create_task(
			keep_embed_at_bottom(ctx.channel, queue_name, new_message.id)
		)

	except Exception as e:
		log.error(f"Error updating queue embed: {str(e)}")

async def move_embed_to_bottom(channel, queue_name: str, message_id: int):
	"""Move the queue embed to the bottom of the channel"""
	try:
		# Try to delete the old embed if it exists
		try:
			old_message = await channel.fetch_message(message_id)
			await old_message.delete()
			print(f"🗑️ Deleted old embed message {message_id}")
		except Exception as e:
			print(f"ℹ️ Old message {message_id} not found or already deleted")
		
		# Get the queue channel and queue
		qc = bot.queue_channels.get(channel.id)
		if not qc:
			print(f"❌ No queue channel found for channel {channel.id}")
			return
			
		q = find(lambda i: i.name.lower() == queue_name.lower(), qc.queues)
		if not q:
			print(f"❌ Queue {queue_name} not found")
			return
			
		# Create new view if it doesn't exist
		if queue_name not in qc.queue_views:
			print(f"📝 Creating new view for queue {queue_name}")
			view = View(timeout=None)
			join_button = Button(label="Join", style=ButtonStyle.green, custom_id=f"join_{queue_name}")
			leave_button = Button(label="Leave", style=ButtonStyle.red, custom_id=f"leave_{queue_name}")
			join_button.callback = join_callback
			leave_button.callback = leave_callback
			view.add_item(join_button)
			view.add_item(leave_button)
			qc.queue_views[queue_name] = view
		else:
			view = qc.queue_views[queue_name]
		
		# Create new embed
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
		
		# Send new embed at bottom
		new_message = await channel.send(embed=embed, view=view)
		
		# Update the stored message ID with channel-specific key
		channel_key = f"{queue_name}_{channel.id}"
		qc.queue_embeds[channel_key] = new_message.id
		print(f"✅ Moved queue embed to bottom (new ID: {new_message.id})")
		
		# Start or update the background task
		task_key = f"{channel.id}_{queue_name}"
		if task_key in bot.queue_tasks:
			bot.queue_tasks[task_key].cancel()
		bot.queue_tasks[task_key] = asyncio.create_task(keep_embed_at_bottom(channel, queue_name, new_message.id))
		
		return new_message.id
	except Exception as e:
		print(f"❌ Error moving embed to bottom: {str(e)}")
		print(f"Type: {type(e)}")
		import traceback
		print("Traceback:")
		print(traceback.format_exc())
		return None

async def keep_embed_at_bottom(channel, queue_name, message_id):
	"""Background task to keep queue embed at the bottom of the channel"""
	while True:
		try:
			# Get the message
			message = await channel.fetch_message(message_id)
			if not message:
				log.error(f"Could not find message {message_id} in channel {channel.name}")
				break

			# Get the queue channel
			qc = bot.queue_channels.get(channel.id)
			if not qc:
				log.error(f"Could not find queue channel for {channel.id}")
				break

			# Get the queue
			q = find(lambda i: i.name.lower() == queue_name.lower(), qc.queues)
			if not q:
				log.error(f"Could not find queue {queue_name}")
				break

			# Update the embed
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

			# Create the view
			view = View(timeout=None)
			join_button = Button(label="Join", style=ButtonStyle.green, custom_id=f"join_{queue_name}")
			leave_button = Button(label="Leave", style=ButtonStyle.red, custom_id=f"leave_{queue_name}")
			join_button.callback = join_callback
			leave_button.callback = leave_callback
			view.add_item(join_button)
			view.add_item(leave_button)
			qc.queue_views[queue_name] = view

			# Try to update the message
			try:
				await message.edit(embed=embed, view=view)
			except Exception as e:
				log.error(f"Failed to update message {message_id}: {str(e)}")
				# If update fails, try to send a new message
				try:
					new_message = await channel.send(embed=embed, view=view)
					# Update the stored message ID
					channel_key = f"{queue_name}_{channel.id}"
					qc.queue_embeds[channel_key] = new_message.id
					# Delete the old message
					try:
						await message.delete()
					except Exception as e:
						log.error(f"Failed to delete old message {message_id}: {str(e)}")
				except Exception as e:
					log.error(f"Failed to send new message: {str(e)}")

			# Wait before next update
			await asyncio.sleep(30)
		except Exception as e:
			log.error(f"Error in keep_embed_at_bottom: {str(e)}")
			await asyncio.sleep(30)  # Wait before retrying

async def add(ctx, queues: str = None):
	""" add author to channel queues """
	phrase = await ctx.qc.check_allowed_to_add(ctx, ctx.author)

	targets = queues.lower().split(" ") if queues else []
	# select the only one queue on the channel
	if not len(targets) and len(ctx.qc.queues) == 1:
		t_queues = ctx.qc.queues

	# select queues requested by user
	elif len(targets):
		t_queues = [q for q in ctx.qc.queues if any(
			(t == q.name.lower() or t in (a["alias"].lower() for a in q.cfg.aliases) for t in targets)
		)]

	# select active queues or default queues if no active queues
	else:
		t_queues = [q for q in ctx.qc.queues if len(q.queue) and q.cfg.is_default]
		if not len(t_queues):
			t_queues = [q for q in ctx.qc.queues if q.cfg.is_default]

	qr = dict()  # get queue responses
	for q in t_queues:
		qr[q] = await q.add_member(ctx, ctx.author)
		if qr[q] == bot.Qr.QueueStarted:
			await ctx.notice(ctx.qc.topic)
			# Update the queue embed
			await update_queue_embed(ctx, q.name)
			return

	if len(not_allowed := [q for q in qr.keys() if qr[q] == bot.Qr.NotAllowed]):
		await ctx.error(ctx.qc.gt("You are not allowed to add to {queues} queues.".format(
			queues=join_and([f"**{q.name}**" for q in not_allowed])
		)))

	if bot.Qr.Success in qr.values():
		await ctx.qc.update_expire(ctx.author)
		if phrase:
			await ctx.reply(phrase)
		await ctx.notice(ctx.qc.topic)
		# Update embeds for all affected queues
		for q in t_queues:
			await update_queue_embed(ctx, q.name)
	else:  # have to give some response for slash commands
		await ctx.ignore(content=ctx.qc.topic, embed=error_embed(ctx.qc.gt("Action had no effect."), title=None))


async def remove(ctx, queues: str = None):
	""" add author from channel queues """
	targets = queues.lower().split(" ") if queues else []

	if not len(targets):
		t_queues = [q for q in ctx.qc.queues if q.is_added(ctx.author)]
	else:
		t_queues = [
			q for q in ctx.qc.queues if
			any((t == q.name.lower() or t in (a["alias"].lower() for a in q.cfg.aliases) for t in targets)) and
			q.is_added(ctx.author)
		]

	if len(t_queues):
		for q in t_queues:
			q.pop_members(ctx.author)
			# Update the queue embed after removing player
			await update_queue_embed(ctx, q.name)

		if not any((q.is_added(ctx.author) for q in ctx.qc.queues)):
			bot.expire.cancel(ctx.qc, ctx.author)

		await ctx.notice(ctx.qc.topic)
	else:
		await ctx.ignore(content=ctx.qc.topic, embed=error_embed(ctx.qc.gt("Action had no effect."), title=None))


async def who(ctx, queues: str = None):
	""" List added players """
	targets = queues.lower().split(" ") if queues else []

	if len(targets):
		t_queues = [
			q for q in ctx.qc.queues if
			any((t == q.name.lower() or t in (a["alias"].lower() for a in q.cfg.aliases) for t in targets))
		]
	else:
		t_queues = [q for q in ctx.qc.queues if len(q.queue)]

	if not len(t_queues):
		await ctx.reply(f"> {ctx.qc.gt('no players')}")
	else:
		await ctx.reply("\n".join([f"> **{q.name}** ({q.status}) | {q.who}" for q in t_queues]))


async def add_player(ctx, player: Member, queue: str):
	""" Add a player to a queue """
	ctx.check_perms(ctx.Perms.MODERATOR)
	if (p := await ctx.get_member(player)) is None:
		raise bot.Exc.SyntaxError(ctx.qc.gt("Specified user not found."))
	if (q := find(lambda i: i.name.lower() == queue.lower(), ctx.qc.queues)) is None:
		raise bot.Exc.SyntaxError(f"Queue '{queue}' not found on the channel.")

	resp = await q.add_member(ctx, p)
	if resp == bot.Qr.Success:
		await ctx.qc.update_expire(p)
		await ctx.reply(ctx.qc.topic)
	elif resp == bot.Qr.QueueStarted:
		await ctx.reply(ctx.qc.topic)
	else:
		await ctx.error(f"Got bad queue response: {resp.__name__}.")


async def remove_player(ctx, player: Member, queues: str = None):
	""" Remove a player from queues """
	ctx.check_perms(ctx.Perms.MODERATOR)

	if (p := await ctx.get_member(player)) is None:
		raise bot.Exc.SyntaxError(ctx.qc.gt("Specified user not found."))
	ctx.author = p
	await remove(ctx, queues=queues)


async def promote(ctx, queue: str = None):
	""" Promote a queue """
	if not queue:
		if (q := next(iter(sorted(
			(i for i in ctx.qc.queues if i.length),
			key=lambda i: i.length, reverse=True
		)), None)) is None:
			raise bot.Exc.NotFoundError(ctx.qc.gt("Nothing to promote."))
	else:
		if (q := find(lambda i: i.name.lower() == queue.lower(), ctx.qc.queues)) is None:
			raise bot.Exc.NotFoundError(ctx.qc.gt("Specified queue not found."))

	now = int(time.time())
	if ctx.qc.cfg.promotion_delay and ctx.qc.cfg.promotion_delay+ctx.qc.last_promote > now:
		raise bot.Exc.PermissionError(ctx.qc.gt("You're promoting too often, please wait `{delay}` until next promote.".format(
			delay=seconds_to_str((ctx.qc.cfg.promotion_delay+ctx.qc.last_promote)-now)
		)))

	await q.promote(ctx)
	ctx.qc.last_promote = now


async def start(ctx, queue: str = None):
	""" Manually start a queue """
	ctx.check_perms(ctx.Perms.MODERATOR)
	if (q := find(lambda i: i.name.lower() == queue.lower(), ctx.qc.queues)) is None:
		raise bot.Exc.SyntaxError(f"Queue '{queue}' not found on the channel.")
	await q.start(ctx)
	await ctx.reply(ctx.qc.topic)


async def split(ctx, queue: str, group_size: int = None, sort_by_rating: bool = False):
	""" Split queue players into X separate matches """
	ctx.check_perms(ctx.Perms.MODERATOR)
	if (q := find(lambda i: i.name.lower() == queue.lower(), ctx.qc.queues)) is None:
		raise bot.Exc.SyntaxError(f"Queue '{queue}' not found on the channel.")
	await q.split(ctx, group_size=group_size, sort_by_rating=sort_by_rating)
	await ctx.reply(ctx.qc.topic)


async def reset(ctx, queue: str = None):
	""" Reset all or specified queue """
	ctx.check_perms(ctx.Perms.MODERATOR)
	if queue:
		if (q := find(lambda i: i.name.lower() == queue.lower(), ctx.qc.queues)) is None:
			raise bot.Exc.SyntaxError(f"Queue '{queue}' not found on the channel.")
		await q.reset()
	else:
		for q in ctx.qc.queues:
			await q.reset()
	await ctx.reply(ctx.qc.topic)


async def subscribe(ctx, queues: str = None, unsub: bool = False):
	if not queues:
		roles = [ctx.qc.cfg.promotion_role] if ctx.qc.cfg.promotion_role else []
	else:
		queues = queues.split(" ")
		roles = (q.cfg.promotion_role for q in ctx.qc.queues if q.cfg.promotion_role and any(
			(t == q.name.lower() or t in (a["alias"].lower() for a in q.cfg.aliases) for t in queues)
		))

	if unsub:
		roles = [r for r in roles if r in ctx.author.roles]
		if not len(roles):
			raise bot.Exc.ValueError(ctx.qc.gt("No changes to apply."))
		await ctx.author.remove_roles(*roles, reason="subscribe command")
		await ctx.success(ctx.qc.gt("Removed `{count}` roles from you.").format(
			count=len(roles)
		))

	else:
		roles = [r for r in roles if r not in ctx.author.roles]
		if not len(roles):
			raise bot.Exc.ValueError(ctx.qc.gt("No changes to apply."))
		await ctx.author.add_roles(*roles, reason="subscribe command")
		await ctx.success(ctx.qc.gt("Added `{count}` roles to you.").format(
			count=len(roles)
		))


async def server(ctx, queue: str):
	if (q := find(lambda i: i.name.lower() == queue.lower(), ctx.qc.queues)) is None:
		raise bot.Exc.SyntaxError(f"Queue '{queue}' not found on the channel.")
	if not q.cfg.server:
		raise bot.Exc.NotFoundError(ctx.qc.gt("Server for **{queue}** is not set.").format(
			queue=q.name
		))
	await ctx.success(q.cfg.server, title=ctx.qc.gt("Server for **{queue}**").format(
		queue=q.name
	))


async def maps(ctx, queue: str, one: bool = False):
	if (q := find(lambda i: i.name.lower() == queue.lower(), ctx.qc.queues)) is None:
		raise bot.Exc.SyntaxError(f"Queue '{queue}' not found on the channel.")
	if not len(q.cfg.maps):
		raise bot.Exc.NotFoundError(ctx.qc.gt("No maps is set for **{queue}**.").format(
			queue=q.name
		))

	if one:
		await ctx.success(f"`{choice(q.cfg.maps)['name']}`")
	else:
		await ctx.success(
			", ".join((f"`{i['name']}`" for i in q.cfg.maps)),
			title=ctx.qc.gt("Maps for **{queue}**").format(queue=q.name)
		)


async def queue_embed(ctx, queue_name: str):
	"""Create a queue embed with join/leave buttons"""
	print("\n==================================================")
	print("🎮 QUEUE EMBED UPDATE")
	print("==================================================")
	print(f"🎯 Queue: {queue_name}")
	print(f"👤 Context type: {type(ctx)}")
	
	try:
		# Get the current channel's queue channel
		current_qc = bot.queue_channels.get(ctx.channel.id)
		if not current_qc:
			print("❌ Current channel is not a queue channel")
			await ctx.error("This channel is not a queue channel")
			return
			
		# Find the queue in the current channel
		q = find(lambda i: i.name.lower() == queue_name.lower(), current_qc.queues)
		if not q:
			print("❌ Queue not found in this channel")
			await ctx.error(f"Queue {queue_name} not found in this channel")
			return
			
		# Create the view with join/leave buttons
		view = View(timeout=None)
		
		# Join button
		join_button = Button(
			style=ButtonStyle.green,
			label="Join Queue",
			custom_id=f"join_{queue_name}"
		)
		join_button.callback = join_callback
		view.add_item(join_button)
		
		# Leave button
		leave_button = Button(
			style=ButtonStyle.red,
			label="Leave Queue",
			custom_id=f"leave_{queue_name}"
		)
		leave_button.callback = leave_callback
		view.add_item(leave_button)
		
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
		
		# Create channel-specific key for tracking
		channel_key = f"{queue_name}_{ctx.channel.id}"
		
		# Check if we already have a message for this queue in this channel
		if channel_key in current_qc.queue_embeds:
			print(f"📝 Updating existing embed for queue: {queue_name}")
			try:
				# Try to update the existing message
				message = await ctx.channel.fetch_message(current_qc.queue_embeds[channel_key])
				await message.edit(embed=embed, view=view)
				print(f"✅ Updated existing embed")
			except Exception as e:
				print(f"ℹ️ Could not update existing message, creating new one: {str(e)}")
				# If we can't update, create a new message
				message = await ctx.channel.send(embed=embed, view=view)
				current_qc.queue_embeds[channel_key] = message.id
				print(f"✅ Created new embed")
		else:
			# Send new message if we don't have one
			message = await ctx.channel.send(embed=embed, view=view)
			current_qc.queue_embeds[channel_key] = message.id
			print(f"✅ Created new embed")
		
		# Register the view with the bot for persistence
		dc.add_view(view, message_id=message.id)
		print(f"✅ Registered view for message {message.id}")
		
		# Start or update the background task
		task_key = f"{ctx.channel.id}_{queue_name}"
		if task_key in bot.queue_tasks:
			bot.queue_tasks[task_key].cancel()
		bot.queue_tasks[task_key] = asyncio.create_task(keep_embed_at_bottom(ctx.channel, q.name, message.id))
		print(f"✅ Started/updated background task for {q.name}")
		
		# Save queue data
		save_queue_data()
		
		print("✅ Queue embed updated")
		
	except Exception as e:
		print(f"❌ Error in queue_embed: {str(e)}")
		print(f"Type: {type(e)}")
		import traceback
		print("Traceback:")
		print(traceback.format_exc())
		await ctx.error(f"An error occurred while creating the queue embed: {str(e)}")

def save_queue_data():
	"""Save queue embed message IDs to database"""
	try:
		# Get all queue embeds
		queue_data = {}
		for queue_name, message_id in queue_embeds.items():
			channel_id = queue_channels.get(queue_name)
			if channel_id:
				queue_data[queue_name] = {
					'message_id': message_id,
					'channel_id': channel_id
				}
		
		# Save to database
		with open('queue_data.json', 'w') as f:
			json.dump(queue_data, f)
		print("✅ Saved queue data to database")
	except Exception as e:
		print(f"❌ Error saving queue data: {str(e)}")

def load_queue_data():
	"""Load queue embed message IDs from database"""
	try:
		with open('queue_data.json', 'r') as f:
			queue_data = json.load(f)
		
		# Restore queue embeds and channels
		for queue_name, data in queue_data.items():
			queue_embeds[queue_name] = data['message_id']
			if data['channel_id']:
				queue_channels[queue_name] = data['channel_id']
		print("✅ Loaded queue data from database")
	except FileNotFoundError:
		print("ℹ️ No queue data found in database")
	except Exception as e:
		print(f"❌ Error loading queue data: {str(e)}")

async def recreate_queue_embeds():
	"""Recreate queue embeds from saved data"""
	try:
		# Load saved data
		load_queue_data()
		
		# Recreate each queue embed
		for queue_name, message_id in queue_embeds.items():
			channel_id = queue_channels.get(queue_name)
			if not channel_id:
				continue
				
			try:
				# Get the channel
				channel = dc.get_channel(channel_id)
				if not channel:
					print(f"❌ Could not find channel {channel_id} for queue {queue_name}")
					continue
				
				# Get the queue channel
				qc = bot.queue_channels.get(channel_id)
				if not qc:
					print(f"❌ Could not find queue channel for {channel_id}")
					continue
				
				# Get the queue
				q = find(lambda i: i.name.lower() == queue_name.lower(), qc.queues)
				if not q:
					print(f"❌ Could not find queue {queue_name}")
					continue
				
				# Create the view
				view = View(timeout=None)
				join_button = Button(label="Join", style=ButtonStyle.green, custom_id=f"join_{queue_name}")
				leave_button = Button(label="Leave", style=ButtonStyle.red, custom_id=f"leave_{queue_name}")
				join_button.callback = join_callback
				leave_button.callback = leave_callback
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
				
				# Update the stored message ID
				channel_key = f"{queue_name}_{channel_id}"
				qc.queue_embeds[channel_key] = new_message.id
				
				# Register the view with the bot
				dc.add_view(view, message_id=new_message.id)
				
				# Start background task
				task_key = f"{channel_id}_{queue_name}"
				if task_key in bot.queue_tasks:
					bot.queue_tasks[task_key].cancel()
				bot.queue_tasks[task_key] = asyncio.create_task(keep_embed_at_bottom(channel, queue_name, new_message.id))
				print(f"✅ Recreated queue embed for {queue_name}")
				
			except Exception as e:
				print(f"❌ Error recreating queue embed for {queue_name}: {str(e)}")
				print(f"Type: {type(e)}")
				import traceback
				print("Traceback:")
				print(traceback.format_exc())
				
		# Save updated data
		save_queue_data()
		
	except Exception as e:
		print(f"❌ Error in recreate_queue_embeds: {str(e)}")
		print(f"Type: {type(e)}")
		import traceback
		print("Traceback:")
		print(traceback.format_exc())

async def join_callback(interaction):
	"""Callback for the join button"""
	try:
		# Get the queue name from the button's custom_id
		queue_name = interaction.data['custom_id'].split('_')[1]
		
		# Get the queue channel and queue
		channel = interaction.channel
		qc = bot.queue_channels.get(channel.id)
		if not qc:
			await interaction.response.send_message("This queue is no longer active.", ephemeral=True)
			return
			
		# Create a SlashContext for the interaction
		ctx = bot.context.slash.context.SlashContext(qc, interaction)
			
		# Add the user to the queue
		await add(ctx, queue_name)
		
		# Update the queue embed
		await update_queue_embed(ctx, queue_name)
			
	except Exception as e:
		print(f"Error in join_callback: {str(e)}")
		await interaction.response.send_message("An error occurred while joining the queue.", ephemeral=True)

async def leave_callback(interaction):
	"""Callback for the leave button"""
	try:
		# Get the queue name from the button's custom_id
		queue_name = interaction.data['custom_id'].split('_')[1]
		
		# Get the queue channel and queue
		channel = interaction.channel
		qc = bot.queue_channels.get(channel.id)
		if not qc:
			await interaction.response.send_message("This queue is no longer active.", ephemeral=True)
			return
			
		# Create a SlashContext for the interaction
		ctx = bot.context.slash.context.SlashContext(qc, interaction)
			
		# Remove the user from the queue
		await remove(ctx, queue_name)
		
		# Update the queue embed
		await update_queue_embed(ctx, queue_name)
			
	except Exception as e:
		print(f"Error in leave_callback: {str(e)}")
		await interaction.response.send_message("An error occurred while leaving the queue.", ephemeral=True)
