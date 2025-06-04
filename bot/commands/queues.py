__all__ = [
	'add', 'remove', 'who', 'add_player', 'remove_player', 'promote', 'start', 'split',
	'reset', 'subscribe', 'server', 'maps', 'queue_embed', 'recreate_queue_embeds', 'remove_queue_embed',
	'global_queue_embed', 'remove_global_queue_embed'
]

import time
from random import choice
from nextcord import Member, Embed, Button, ButtonStyle, ActionRow, TextChannel, NotFound, Forbidden
from nextcord.ui import View, Button
from core.utils import error_embed, join_and, find, seconds_to_str
from core.client import dc
from core.console import log
import bot
import asyncio
import json
import logging
from datetime import datetime, timedelta

# Global dictionaries for queue management
queue_tasks = {}  # Store active tasks
queue_channels = {}  # Store queue channels
queue_views = {}  # Store queue views
queue_embeds = {}  # Store queue embeds
global_queue_embeds = {}  # Store global queue embeds
last_global_updates = {}  # Store timestamps of last updates for rate limiting

# Rate limiting constants
MIN_UPDATE_INTERVAL = 5  # Minimum seconds between updates for the same embed

async def update_queue_embed(ctx, queue_name: str, create_if_missing=False):
	"""Update an existing queue embed (only creates new one if create_if_missing=True)"""
	print("\n==================================================")
	print("🔄 UPDATE QUEUE EMBED")
	print("==================================================")
	print(f"🎯 Queue: {queue_name}")
	print(f"👤 Context type: {type(ctx)}")
	print(f"🆕 Create if missing: {create_if_missing}")
	
	try:
		# Get the current channel's queue channel
		current_qc = bot.queue_channels.get(ctx.channel.id)
		if not current_qc:
			print("❌ Current channel is not a queue channel")
			return
			
		# Find the queue in the current channel
		q = find(lambda i: i.name.lower() == queue_name.lower(), current_qc.queues)
		if not q:
			print("❌ Queue not found in this channel")
			return
		
		# Create channel-specific key for tracking
		channel_key = f"{queue_name}_{ctx.channel.id}"
		
		# Check if we already have a message for this queue in this channel
		if channel_key in current_qc.queue_embeds:
			print(f"📝 Updating existing embed for queue: {queue_name}")
			try:
				# Create the updated embed
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
				
				# Create the view with join/leave buttons
				view = View(timeout=None)
				
				# Join button
				join_button = Button(
					style=ButtonStyle.green.value,
					label="Join Queue",
					custom_id=f"join_{queue_name}"
				)
				join_button.callback = join_callback
				view.add_item(join_button)
				
				# Leave button
				leave_button = Button(
					style=ButtonStyle.red.value,
					label="Leave Queue",
					custom_id=f"leave_{queue_name}"
				)
				leave_button.callback = leave_callback
				view.add_item(leave_button)
				
				# Try to update the existing message
				message = await ctx.channel.fetch_message(current_qc.queue_embeds[channel_key])
				await message.edit(embed=embed, view=view)
				print(f"✅ Updated existing embed")
				
				# Register the view with the bot for persistence
				dc.add_view(view, message_id=message.id)
				print(f"✅ Re-registered view for message {message.id}")
				
			except Exception as e:
				print(f"ℹ️ Could not update existing message: {str(e)}")
				if create_if_missing:
					print("🆕 Creating new embed since create_if_missing=True")
					await queue_embed(ctx, queue_name)
				else:
					print("🚫 Not creating new embed since create_if_missing=False")
					# Remove the invalid message ID from tracking
					del current_qc.queue_embeds[channel_key]
					save_queue_data()
		else:
			print(f"ℹ️ No existing embed found for queue: {queue_name}")
			if create_if_missing:
				print("🆕 Creating new embed since create_if_missing=True")
				await queue_embed(ctx, queue_name)
			else:
				print("🚫 Not creating new embed since create_if_missing=False")
		
	except Exception as e:
		print(f"❌ Error in update_queue_embed: {str(e)}")
		print(f"Type: {type(e)}")
		import traceback
		print("Traceback:")
		print(traceback.format_exc())

async def keep_embed_at_bottom(channel, queue_name, message_id):
	"""Background task to keep queue embed at the bottom of the channel"""
	while True:
		try:
			# Get the queue channel
			qc = bot.queue_channels.get(channel.id)
			if not qc:
				print(f"❌ Queue channel {channel.id} not found, stopping background task")
				return

			# Get the queue
			q = find(lambda i: i.name.lower() == queue_name.lower(), qc.queues)
			if not q:
				print(f"❌ Queue {queue_name} not found in channel {channel.id}, stopping background task")
				return

			# Check if this message is still registered
			channel_key = f"{queue_name}_{channel.id}"
			
			# If our message ID doesn't match the current one, stop the task
			if current_qc.queue_embeds.get(channel_key) != message_id:
				print(f"ℹ️ Message {message_id} is no longer the active embed for {queue_name}, stopping background task")
				return

			# Check if we're already at the bottom
			is_at_bottom = False
			try:
				# Get the last message in the channel
				async for last_message in channel.history(limit=1):
					# If our message is already the last one, just update it
					if last_message.id == message_id:
						is_at_bottom = True
						# Update the existing message instead of creating a new one
						try:
							message = await channel.fetch_message(message_id)
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

							# Add queue info
							embed.add_field(
								name="Status",
								value=f"{len(q.queue)}/{q.cfg.size} players",
								inline=True
							)

							# Add footer with timestamp
							embed.set_footer(text=f"Last updated: {time.strftime('%H:%M:%S')}")
							await message.edit(embed=embed)
						except Exception as e:
							print(f"❌ Error updating message: {str(e)}")
						break
			except Exception as e:
				print(f"❌ Error checking if message is at bottom: {str(e)}")
				await asyncio.sleep(30)  # Wait longer on error
				continue

			if not is_at_bottom:
				# Before moving to bottom, verify the message still exists and is still registered
				try:
					old_message = await channel.fetch_message(message_id)
					if old_message and qc.queue_embeds.get(channel_key) == message_id:
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

						# Add queue info
						embed.add_field(
							name="Status",
							value=f"{len(q.queue)}/{q.cfg.size} players",
							inline=True
						)

						# Add footer with timestamp
						embed.set_footer(text=f"Last updated: {time.strftime('%H:%M:%S')}")

						# Create the view
						view = View(timeout=None)
						join_button = Button(
							label="Join Queue",
							style=ButtonStyle.green.value,
							custom_id=f"join_{queue_name}"
						)
						leave_button = Button(
							label="Leave Queue",
							style=ButtonStyle.red.value,
							custom_id=f"leave_{queue_name}"
						)
						join_button.callback = join_callback
						leave_button.callback = leave_callback
						view.add_item(join_button)
						view.add_item(leave_button)
						qc.queue_views[queue_name] = view

						# Delete the old message only after we confirm it exists
						await old_message.delete()
						print(f"🗑️ Deleted old embed message {message_id}")

						# Send new message at the bottom
						new_message = await channel.send(embed=embed, view=view)
						
						# Update tracking only if our task is still the active one
						if qc.queue_embeds.get(channel_key) == message_id:
							qc.queue_embeds[channel_key] = new_message.id
							print(f"✅ Moved queue embed to bottom (new ID: {new_message.id})")

							# Register the view
							dc.add_view(view, message_id=new_message.id)

							# Update the task to track the new message
							message_id = new_message.id

							# Also update any global embeds
							await update_global_queue_embed(channel, queue_name, channel.id)
						else:
							print("❌ Task is no longer active, stopping")
							return
					else:
						print("❌ Message no longer exists or is no longer registered, stopping task")
						return
				except discord.NotFound:
					print("❌ Message no longer exists, stopping task")
					return
				except Exception as e:
					print(f"❌ Error moving embed to bottom: {str(e)}")
					print(f"Type: {type(e)}")
					import traceback
					print("Traceback:")
					print(traceback.format_exc())
					await asyncio.sleep(30)  # Wait longer on error
					continue

			# Wait before checking again
			await asyncio.sleep(15 if is_at_bottom else 5)

		except asyncio.CancelledError:
			print(f"ℹ️ Background task for {queue_name} cancelled")
			return
		except Exception as e:
			print(f"❌ Error in keep_embed_at_bottom task: {str(e)}")
			await asyncio.sleep(30)  # Wait longer on error

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
		# Check if this is a global embed channel
		is_global = bool(ctx.qc.queue_embeds.get(f"{q.name}_{ctx.channel.id}"))
		qr[q] = await q.add_member(ctx, ctx.author, silent=is_global)
		if qr[q] == bot.Qr.QueueStarted:
			if not is_global:
				await ctx.notice(ctx.qc.topic)
			# Update the queue embed
			await update_queue_embed(ctx, q.name)
			# Also update global embeds if they exist
			await update_global_queue_embed(ctx.channel, q.name, ctx.qc.id)
			return

	if len(not_allowed := [q for q in qr.keys() if qr[q] == bot.Qr.NotAllowed]):
		await ctx.error(ctx.qc.gt("You are not allowed to add to {queues} queues.".format(
			queues=join_and([f"**{q.name}**" for q in not_allowed])
		)))

	if bot.Qr.Success in qr.values():
		await ctx.qc.update_expire(ctx.author)
		if phrase and not any(bool(ctx.qc.queue_embeds.get(f"{q.name}_{ctx.channel.id}")) for q in t_queues):
			await ctx.reply(phrase)
		await ctx.notice(ctx.qc.topic)
		# Update embeds for all affected queues
		for q in t_queues:
			await update_queue_embed(ctx, q.name)
			# Also update global embeds if they exist
			await update_global_queue_embed(ctx.channel, q.name, ctx.qc.id)
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
			# Also update global embeds if they exist
			await update_global_queue_embed(ctx.channel, q.name, ctx.qc.id)

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

	# Check if this is a global embed channel
	is_global = bool(ctx.qc.queue_embeds.get(f"{q.name}_{ctx.channel.id}"))
	resp = await q.add_member(ctx, p, silent=is_global)
	if resp == bot.Qr.Success:
		await ctx.qc.update_expire(p)
		if not is_global:
			await ctx.reply(ctx.qc.topic)
	elif resp == bot.Qr.QueueStarted:
		if not is_global:
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
	"""Create a queue embed with join/leave buttons (always creates new or updates existing)"""
	print("\n==================================================")
	print("🎮 QUEUE EMBED CREATE/UPDATE")
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
			style=ButtonStyle.green.value,
			label="Join Queue",
			custom_id=f"join_{queue_name}"
		)
		join_button.callback = join_callback
		view.add_item(join_button)
		
		# Leave button
		leave_button = Button(
			style=ButtonStyle.red.value,
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
				message_created = False
			except Exception as e:
				print(f"ℹ️ Could not update existing message, creating new one: {str(e)}")
				# If we can't update, create a new message
				message = await ctx.channel.send(embed=embed, view=view)
				current_qc.queue_embeds[channel_key] = message.id
				print(f"✅ Created new embed")
				message_created = True
		else:
			# Send new message if we don't have one
			message = await ctx.channel.send(embed=embed, view=view)
			current_qc.queue_embeds[channel_key] = message.id
			print(f"✅ Created new embed")
			message_created = True
		
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
		
		print("✅ Queue embed created/updated")

		# Respond to the interaction with a success message
		if message_created:
			await ctx.success(f"Queue embed for **{queue_name}** has been created.")
		else:
			await ctx.success(f"Queue embed for **{queue_name}** has been updated.")
		
	except Exception as e:
		print(f"❌ Error in queue_embed: {str(e)}")
		print(f"Type: {type(e)}")
		import traceback
		print("Traceback:")
		print(traceback.format_exc())
		await ctx.error(f"An error occurred while creating the queue embed: {str(e)}")

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
		
		# Update both the normal queue embed (don't create if missing) and any global embeds
		await update_queue_embed(ctx, queue_name, create_if_missing=False)
		await update_global_queue_embed(channel, queue_name, qc.id)
			
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
		
		# Find the queue in the channel
		q = find(lambda i: i.name.lower() == queue_name.lower(), qc.queues)
		if not q:
			await interaction.response.send_message(f"Queue {queue_name} not found", ephemeral=True)
			return
			
		# Check if user is in the queue
		if not q.is_added(interaction.user):
			await interaction.response.send_message(f"You are not in the {queue_name} queue", ephemeral=True)
			return
			
		# Remove the user from the queue
		q.pop_members(interaction.user)
		
		# Update both normal and global embeds (don't create if missing)
		await update_queue_embed(ctx, queue_name, create_if_missing=False)
		await update_global_queue_embed(channel, queue_name, qc.id)
		
		# Send a public response
		await interaction.response.send_message(f"{interaction.user.mention} has left the {queue_name} queue")
			
	except Exception as e:
		print(f"Error in leave_callback: {str(e)}")
		try:
			await interaction.response.send_message("An error occurred while leaving the queue.", ephemeral=True)
		except:
			pass

async def remove_queue_embed(ctx, queue_name: str):
	"""Remove a queue embed from the channel"""
	print("\n==================================================")
	print("🎮 REMOVE QUEUE EMBED")
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
		
		# Create channel-specific key for tracking
		channel_key = f"{queue_name}_{ctx.channel.id}"
		
		# Check if we have a message for this queue in this channel
		if channel_key in current_qc.queue_embeds:
			try:
				# Try to delete the existing message
				message_id = current_qc.queue_embeds[channel_key]
				message = await ctx.channel.fetch_message(message_id)
				await message.delete()
				print(f"✅ Deleted queue embed for {queue_name}")
				
				# Remove the message ID from tracking
				del current_qc.queue_embeds[channel_key]
				
				# Cancel the background task if it exists
				task_key = f"{ctx.channel.id}_{queue_name}"
				if task_key in bot.queue_tasks:
					bot.queue_tasks[task_key].cancel()
					del bot.queue_tasks[task_key]
					print(f"✅ Cancelled background task for {queue_name}")
				
				# Save queue data
				save_queue_data()
				
				await ctx.success(f"Queue embed for **{queue_name}** has been removed.")
			except Exception as e:
				print(f"❌ Error deleting message: {str(e)}")
				await ctx.error(f"Failed to delete queue embed: {str(e)}")
		else:
			print("❌ No queue embed found for this queue")
			await ctx.error(f"No queue embed found for {queue_name}")
	
	except Exception as e:
		print(f"❌ Error in remove_queue_embed: {str(e)}")
		print(f"Type: {type(e)}")
		import traceback
		print("Traceback:")
		print(traceback.format_exc())
		await ctx.error(f"An error occurred while removing the queue embed: {str(e)}")

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
				join_button = Button(label="Join", style=ButtonStyle.green.value, custom_id=f"join_{queue_name}")
				leave_button = Button(label="Leave", style=ButtonStyle.red.value, custom_id=f"leave_{queue_name}")
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

async def update_global_queue_embed(channel, queue_name, queue_channel_id=None):
	"""Update a global queue embed without posting to chat"""
	try:
		print("\n==================================================")
		print("🔄 UPDATE GLOBAL QUEUE EMBED")
		print("==================================================")
		print(f"🎯 Queue: {queue_name}")
		print(f"📝 Channel: {channel.name} ({channel.id})")
		print(f"🔗 Queue Channel ID: {queue_channel_id}")
		print(f"🗃️ Current global embeds: {list(global_queue_embeds.keys())}")
		
		# If no queue_channel_id is provided, assume it's the same as the channel
		if queue_channel_id is None:
			queue_channel_id = channel.id
			print(f"ℹ️ Using channel ID as queue channel ID: {queue_channel_id}")
		
		# Get the queue channel
		qc = bot.queue_channels.get(queue_channel_id)
		if not qc:
			print(f"❌ Queue channel {queue_channel_id} not found")
			return

		# Get the queue
		q = find(lambda i: i.name.lower() == queue_name.lower(), qc.queues)
		if not q:
			print(f"❌ Queue {queue_name} not found in channel {queue_channel_id}")
			return

		# Track which embeds were successfully updated
		updated_embeds = set()
		failed_embeds = {}
		skipped_embeds = {}

		current_time = datetime.now()

		# Update all global embeds for this queue
		for key, message_id in list(global_queue_embeds.items()):
			parts = key.split('_')
			print(f"📋 Processing key: {key}")
			print(f"📊 Parts: {parts}")
			
			if len(parts) >= 4 and parts[0] == "global" and parts[1] == queue_name:
				# Check rate limiting
				if key in last_global_updates:
					time_since_last_update = (current_time - last_global_updates[key]).total_seconds()
					if time_since_last_update < MIN_UPDATE_INTERVAL:
						print(f"⏳ Skipping update for {key} due to rate limiting (last update was {time_since_last_update:.2f}s ago)")
						skipped_embeds[key] = f"Rate limited ({time_since_last_update:.2f}s < {MIN_UPDATE_INTERVAL}s)"
						continue

				try:
					embed_channel_id = int(parts[2])
					embed_channel = dc.get_channel(embed_channel_id)
					if not embed_channel:
						print(f"❌ Channel {embed_channel_id} not found for embed {key}")
						failed_embeds[key] = "Channel not found"
						continue

					# Create the embed
					embed = Embed(
						title=f"{q.name} Queue",
						description=f"Queue from channel: <#{queue_channel_id}>",
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
					
					# Add queue info
					embed.add_field(
						name="Status",
						value=f"{len(q.queue)}/{q.cfg.size} players",
						inline=True
					)
					
					# Add footer with timestamp
					embed.set_footer(text=f"Last updated: {time.strftime('%H:%M:%S')} • Silent Mode")
					
					# Update the message
					try:
						message = await embed_channel.fetch_message(message_id)
						await message.edit(embed=embed)
						print(f"✅ Updated global queue embed in channel {embed_channel.name} for {queue_name}")
						updated_embeds.add(key)
						last_global_updates[key] = current_time
					except discord.NotFound:
						print(f"❌ Message {message_id} not found in channel {embed_channel.name}")
						failed_embeds[key] = "Message not found"
					except discord.Forbidden:
						print(f"❌ Bot lacks permissions to edit message {message_id} in channel {embed_channel.name}")
						failed_embeds[key] = "Missing permissions"
					except Exception as e:
						print(f"❌ Error updating message {message_id} in channel {embed_channel.name}: {str(e)}")
						failed_embeds[key] = str(e)
				except Exception as e:
					print(f"❌ Error processing global embed {key}: {str(e)}")
					failed_embeds[key] = str(e)
					continue

		# Clean up failed embeds
		for key, reason in failed_embeds.items():
			print(f"🗑️ Removing invalid global embed {key}: {reason}")
			del global_queue_embeds[key]
			if key in last_global_updates:
				del last_global_updates[key]
		
		# Save changes if any embeds were removed
		if failed_embeds:
			save_global_queue_data()
			print(f"💾 Saved global queue data after removing {len(failed_embeds)} invalid embeds")

		# Log summary
		if updated_embeds:
			print(f"📊 Successfully updated {len(updated_embeds)} global embeds for {queue_name}")
		if skipped_embeds:
			print(f"⏳ Skipped {len(skipped_embeds)} updates due to rate limiting")
		if not updated_embeds and not failed_embeds and not skipped_embeds:
			print(f"ℹ️ No global embeds found for {queue_name}")

	except Exception as e:
		print(f"❌ Error in update_global_queue_embed: {str(e)}")
		import traceback
		print(traceback.format_exc())

async def global_queue_embed(ctx, queue_name: str, queue_channel: TextChannel = None):
	"""Create a global queue embed that works in any channel"""
	try:
		# Extract queue name and channel name from autocomplete result
		if " (#" in queue_name:
			queue_name, channel_name = queue_name.split(" (#", 1)
			channel_name = channel_name.rstrip(")")
		
		# Find the queue across all channels
		target_qc = None
		target_queue = None
		
		# If channel parameter provided, check that first
		if queue_channel:
			qc = bot.queue_channels.get(queue_channel.id)
			if qc:
				target_queue = find(lambda i: i.name.lower() == queue_name.lower(), qc.queues)
				if target_queue:
					target_qc = qc

		# If not found, search all queue channels
		if not target_queue:
			for qc in bot.queue_channels.values():
				q = find(lambda i: i.name.lower() == queue_name.lower(), qc.queues)
				if q:
					target_qc = qc
					target_queue = q
					break

		if not target_queue:
			await ctx.error(f"Queue '{queue_name}' not found in any enabled channels")
			return

		# Rest of the existing embed creation code...
		# Make sure to use target_qc and target_queue instead of local channel
		# Update all references to use the found queue and queue channel
		# Create the view with join/leave buttons
		view = View(timeout=None)
		
		# Join button
		join_button = Button(
			style=ButtonStyle.green.value,
			label="Join Queue",
			custom_id=f"global_join_{queue_name}_{target_qc.id}"
		)
		join_button.callback = global_join_callback
		view.add_item(join_button)
		
		# Leave button
		leave_button = Button(
			style=ButtonStyle.red.value,
			label="Leave Queue",
			custom_id=f"global_leave_{queue_name}_{target_qc.id}"
		)
		leave_button.callback = global_leave_callback
		view.add_item(leave_button)
		
		# Create the embed
		embed = Embed(
			title=f"{target_queue.name} Queue",
			description=f"Queue from channel: <#{target_qc.id}>",
			color=0x7289DA
		)
		
		if len(target_queue.queue):
			embed.add_field(
				name="Players",
				value="\n".join([f"• {player.display_name}" for player in target_queue.queue]),
				inline=False
			)
		else:
			embed.add_field(
				name="Players",
				value="No players in queue",
				inline=False
			)
		
		# Add queue info
		embed.add_field(
			name="Status",
			value=f"{len(target_queue.queue)}/{target_queue.cfg.size} players",
			inline=True
		)
		
		# Add footer with timestamp and silent mode indicator
		embed.set_footer(text=f"Last updated: {time.strftime('%H:%M:%S')} • Silent Mode")
		
		# Create channel-specific key for tracking
		# This includes both the target channel ID and the queue channel ID
		channel_key = f"global_{queue_name}_{ctx.channel.id}_{target_qc.id}"
		
		# Check if we already have a message for this queue in this channel
		if channel_key in global_queue_embeds:
			print(f"📝 Updating existing global embed for queue: {queue_name}")
			try:
				# Try to update the existing message
				message = await ctx.channel.fetch_message(global_queue_embeds[channel_key])
				await message.edit(embed=embed, view=view)
				print(f"✅ Updated existing global embed")
				message_created = False
			except Exception as e:
				print(f"ℹ️ Could not update existing message, creating new one: {str(e)}")
				# If we can't update, create a new message
				message = await ctx.channel.send(embed=embed, view=view)
				global_queue_embeds[channel_key] = message.id
				print(f"✅ Created new global embed with key: {channel_key}, message ID: {message.id}")
				message_created = True
		else:
			# Send new message if we don't have one
			message = await ctx.channel.send(embed=embed, view=view)
			global_queue_embeds[channel_key] = message.id
			print(f"✅ Created new global embed with key: {channel_key}, message ID: {message.id}")
			message_created = True
		
		# Register the view with the bot for persistence
		dc.add_view(view, message_id=message.id)
		print(f"✅ Registered view for message {message.id}")
		
		# Save queue data
		save_global_queue_data()
		
		print("✅ Global queue embed updated")

		# Respond to the interaction with a success message
		if message_created:
			await ctx.success(f"Global queue embed for **{queue_name}** has been created. Updates will be silent.")
		else:
			await ctx.success(f"Global queue embed for **{queue_name}** has been updated. Updates will be silent.")
		
	except Exception as e:
		print(f"❌ Error in global_queue_embed: {str(e)}")
		print(f"Type: {type(e)}")
		import traceback
		print("Traceback:")
		print(traceback.format_exc())
		await ctx.error(f"An error occurred while creating the global queue embed: {str(e)}")

async def remove_global_queue_embed(ctx, queue_name: str, queue_channel_id: int = None):
	"""Remove a global queue embed from the channel"""
	print("\n==================================================")
	print("🎮 REMOVE GLOBAL QUEUE EMBED")
	print("==================================================")
	print(f"🎯 Queue: {queue_name}")
	print(f"👤 Context type: {type(ctx)}")
	
	try:
		# If no queue_channel_id is provided, we need to find embeds in this channel for the specified queue
		if queue_channel_id is None:
			# Look for any global embed for this queue in this channel
			keys_to_remove = []
			for key in global_queue_embeds.keys():
				parts = key.split('_')
				if len(parts) >= 3 and parts[0] == "global" and parts[1] == queue_name and str(ctx.channel.id) == parts[2]:
					keys_to_remove.append(key)
			
			if not keys_to_remove:
				print("❌ No global queue embed found for this queue")
				await ctx.error(f"No global queue embed found for {queue_name}")
				return
			
			# Remove all matching embeds
			for key in keys_to_remove:
				try:
					message_id = global_queue_embeds[key]
					message = await ctx.channel.fetch_message(message_id)
					await message.delete()
					print(f"✅ Deleted global queue embed for {queue_name}")
					
					# Remove the message ID from tracking
					del global_queue_embeds[key]
				except Exception as e:
					print(f"❌ Error deleting message for key {key}: {str(e)}")
					# If we can't find the message, still remove the key
					if key in global_queue_embeds:
						del global_queue_embeds[key]
			
			# Save queue data
			save_global_queue_data()
			
			await ctx.success(f"Global queue embed for **{queue_name}** has been removed.")
		else:
			# If queue_channel_id is provided, look for the specific embed
			channel_key = f"global_{queue_name}_{ctx.channel.id}_{queue_channel_id}"
			
			# Check if we have a message for this queue in this channel
			if channel_key in global_queue_embeds:
				try:
					# Try to delete the existing message
					message_id = global_queue_embeds[channel_key]
					message = await ctx.channel.fetch_message(message_id)
					await message.delete()
					print(f"✅ Deleted global queue embed for {queue_name}")
					
					# Remove the message ID from tracking
					del global_queue_embeds[channel_key]
					
					# Save queue data
					save_global_queue_data()
					
					await ctx.success(f"Global queue embed for **{queue_name}** has been removed.")
				except Exception as e:
					print(f"❌ Error deleting message: {str(e)}")
					# If we can't find the message, still remove the key
					if channel_key in global_queue_embeds:
						del global_queue_embeds[channel_key]
					await ctx.error(f"Failed to delete global queue embed: {str(e)}")
			else:
				# Try with legacy format
				legacy_key = f"global_{queue_name}_{ctx.channel.id}"
				if legacy_key in global_queue_embeds:
					try:
						message_id = global_queue_embeds[legacy_key]
						message = await ctx.channel.fetch_message(message_id)
						await message.delete()
						print(f"✅ Deleted global queue embed for {queue_name}")
						
						# Remove the message ID from tracking
						del global_queue_embeds[legacy_key]
						
						# Save queue data
						save_global_queue_data()
						
						await ctx.success(f"Global queue embed for **{queue_name}** has been removed.")
					except Exception as e:
						print(f"❌ Error deleting message: {str(e)}")
						if legacy_key in global_queue_embeds:
							del global_queue_embeds[legacy_key]
						await ctx.error(f"Failed to delete global queue embed: {str(e)}")
				else:
					print("❌ No global queue embed found for this queue")
					await ctx.error(f"No global queue embed found for {queue_name}")
	
	except Exception as e:
		print(f"❌ Error in remove_global_queue_embed: {str(e)}")
		print(f"Type: {type(e)}")
		import traceback
		print("Traceback:")
		print(traceback.format_exc())
		await ctx.error(f"An error occurred while removing the global queue embed: {str(e)}")

def save_global_queue_data():
	"""Save global queue embed message IDs to database"""
	try:
		print("\n==================================================")
		print("💾 SAVING GLOBAL QUEUE DATA")
		print("==================================================")
		
		# Get all global queue embeds
		queue_data = {}
		for key, message_id in global_queue_embeds.items():
			queue_data[key] = message_id
			print(f"📝 Saving {key}: {message_id}")
		
		print(f"\n📦 Queue Data: {queue_data}")
		
		# Save to database
		with open('global_queue_data.json', 'w') as f:
			json.dump(queue_data, f, indent=2)
		print("✅ Saved global queue data to database")
		
		# Verify the save
		try:
			with open('global_queue_data.json', 'r') as f:
				saved_data = json.load(f)
			print(f"✓ Verified save - Read back {len(saved_data)} entries")
		except Exception as e:
			print(f"⚠️ Could not verify save: {str(e)}")
			
	except Exception as e:
		print(f"❌ Error saving global queue data: {str(e)}")
		print(f"Type: {type(e)}")
		import traceback
		print("Traceback:")
		print(traceback.format_exc())

def load_global_queue_data():
	"""Load global queue embed message IDs from database"""
	try:
		with open('global_queue_data.json', 'r') as f:
			queue_data = json.load(f)
		
		# Restore global queue embeds
		for key, message_id in queue_data.items():
			global_queue_embeds[key] = message_id
		print("✅ Loaded global queue data from database")
	except FileNotFoundError:
		print("ℹ️ No global queue data found in database")
	except Exception as e:
		print(f"❌ Error loading global queue data: {str(e)}")

# Load global queue embeds from saved state on bot restart
def load_global_queue_data_from_state(data):
	if 'global_queue_embeds' in data:
		try:
			print("\n==================================================")
			print("🔄 LOADING GLOBAL QUEUE EMBEDS FROM STATE")
			print("==================================================")
			print(f"📦 Data: {data['global_queue_embeds']}")
			
			for key, message_id in data['global_queue_embeds'].items():
				print(f"\n📝 Processing key: {key}")
				print(f"🔑 Message ID: {message_id}")
				
				global_queue_embeds[key] = message_id
				
				# Register view for this message
				try:
					parts = key.split('_')
					print(f"📋 Parts: {parts}")
					
					if len(parts) >= 4 and parts[0] == "global":
						queue_name = parts[1]
						queue_channel_id = int(parts[3])
						print(f"✨ Queue Name: {queue_name}")
						print(f"📍 Queue Channel ID: {queue_channel_id}")
						
						# Create and register the view
						view = View(timeout=None)
						
						# Join button
						join_button = Button(
							style=ButtonStyle.green.value,
							label="Join Queue",
							custom_id=f"global_join_{queue_name}_{queue_channel_id}"
						)
						join_button.callback = global_join_callback
						view.add_item(join_button)
						
						# Leave button
						leave_button = Button(
							style=ButtonStyle.red.value,
							label="Leave Queue",
							custom_id=f"global_leave_{queue_name}_{queue_channel_id}"
						)
						leave_button.callback = global_leave_callback
						view.add_item(leave_button)
						
						# Register the view
						dc.add_view(view, message_id=message_id)
						print(f"✅ Registered view for message {message_id}")
				except Exception as e:
					print(f"❌ Error registering view for global embed {key}: {str(e)}")
					print(f"Type: {type(e)}")
					import traceback
					print("Traceback:")
					print(traceback.format_exc())
					continue
					
			print("\n✅ Loaded global queue embeds from saved state")
			print(f"📊 Current global embeds: {list(global_queue_embeds.keys())}")
		except Exception as e:
			print(f"❌ Error loading global queue embeds: {str(e)}")
			print(f"Type: {type(e)}")
			import traceback
			print("Traceback:")
			print(traceback.format_exc())

# Modify save_state to also save global queue embeds
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
		'global_queue_embeds': global_queue_embeds
	}

	try:
		with open("saved_state.json", 'w') as f:
			json.dump(state_data, f, indent=2)
		log.info("State saved successfully")
	except Exception as e:
		log.error(f"Failed to save state: {str(e)}")
