__all__ = [
	'add', 'remove', 'who', 'add_player', 'remove_player', 'promote', 'start', 'split',
	'reset', 'subscribe', 'server', 'maps', 'queue_embed'
]

import time
from random import choice
from nextcord import Member, Embed, Button, ButtonStyle, ActionRow
from nextcord.ui import View, Button
from core.utils import error_embed, join_and, find, seconds_to_str
import bot


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
	"""Create or update a queue embed with join/leave buttons"""
	try:
		print("\n" + "="*50)
		print("🎮 QUEUE EMBED UPDATE")
		print("="*50)
		print(f"🎯 Queue: {queue_name}")
		print(f"👤 Context type: {type(ctx)}")

		# Find the queue
		q = find(lambda i: i.name.lower() == queue_name.lower(), ctx.qc.queues)
		if not q:
			print("❌ Queue not found")
			raise bot.Exc.SyntaxError(f"Queue '{queue_name}' not found on the channel.")
		print("✅ Found queue")

		# Create the embed
		embed = Embed(
			title=f"{q.name} Queue",
			description="Current queued players:",
			color=0x7289DA
		)

		# Add players to embed
		if len(q.queue):
			print(f"👥 Queue has {len(q.queue)} players")
			embed.add_field(
				name="Players",
				value="\n".join([f"• {player.display_name}" for player in q.queue]),
				inline=False
			)
		else:
			print("👥 Queue is empty")
			embed.add_field(
				name="Players",
				value="No players in queue",
				inline=False
			)

		# Initialize queue_embeds if needed
		if not hasattr(ctx.qc, 'queue_embeds'):
			print("📝 Initializing queue_embeds dictionary")
			ctx.qc.queue_embeds = {}

		# Create or get existing view
		if not hasattr(ctx.qc, 'queue_views'):
			print("📝 Initializing queue_views dictionary")
			ctx.qc.queue_views = {}

		# Get or create view for this queue
		if q.name not in ctx.qc.queue_views:
			print(f"🔄 Creating new view for queue: {q.name}")
			view = View(timeout=None)
			
			# Create buttons
			join_button = Button(
				style=ButtonStyle.green,
				custom_id=f"join_{q.name}",
				emoji="✅",
				label="Join"
			)
			leave_button = Button(
				style=ButtonStyle.red,
				custom_id=f"leave_{q.name}",
				emoji="❌",
				label="Leave"
			)

			# Set up callbacks
			async def join_callback(interaction):
				print("\n" + "="*50)
				print("🎮 JOIN BUTTON CLICKED")
				print("="*50)
				print(f"👤 User: {interaction.user.display_name} (ID: {interaction.user.id})")
				print(f"🎯 Queue: {q.name}")
				print(f"📊 Queue state: {len(q.queue)}/{q.cfg.max_size if hasattr(q.cfg, 'max_size') else 'N/A'} players")
				
				try:
					print("\n🔄 Attempting to add member...")
					resp = await q.add_member(ctx, interaction.user)
					print(f"📝 Response: {resp}")
					
					if resp == bot.Qr.Success:
						print("✅ Successfully added to queue")
						await ctx.qc.update_expire(interaction.user)
						await interaction.response.send_message("You have joined the queue!", ephemeral=True)
					elif resp == bot.Qr.QueueStarted:
						print("🎮 Queue has started")
						await interaction.response.send_message("Queue has started!", ephemeral=True)
					else:
						print(f"❌ Failed to join: {resp}")
						await interaction.response.send_message("Could not join the queue!", ephemeral=True)
					
					print("\n🔄 Updating queue embed...")
					await queue_embed(ctx, q.name)
					print("✅ Queue embed updated")
				except Exception as e:
					print("\n❌ ERROR IN JOIN CALLBACK")
					print(f"Error: {str(e)}")
					print(f"Type: {type(e)}")
					import traceback
					print("Traceback:")
					print(traceback.format_exc())
					try:
						await interaction.response.send_message("An error occurred while joining the queue!", ephemeral=True)
					except Exception as e2:
						print(f"Failed to send error message: {str(e2)}")

			async def leave_callback(interaction):
				print("\n" + "="*50)
				print("🚪 LEAVE BUTTON CLICKED")
				print("="*50)
				print(f"👤 User: {interaction.user.display_name} (ID: {interaction.user.id})")
				print(f"🎯 Queue: {q.name}")
				print(f"📊 Queue state: {len(q.queue)}/{q.cfg.max_size if hasattr(q.cfg, 'max_size') else 'N/A'} players")
				
				try:
					print("\n🔍 Checking if user is in queue...")
					is_added = q.is_added(interaction.user)
					print(f"📝 User in queue: {is_added}")
					
					if is_added:
						print("\n🔄 Removing user from queue...")
						print(f"Before: {[p.display_name for p in q.queue]}")
						q.pop_members(interaction.user)
						print(f"After: {[p.display_name for p in q.queue]}")
						
						print("\n🔍 Checking other queues...")
						in_other_queues = any((q.is_added(interaction.user) for q in ctx.qc.queues))
						print(f"User in other queues: {in_other_queues}")
						
						if not in_other_queues:
							print("⏱️ Canceling expire timer")
							bot.expire.cancel(ctx.qc, interaction.user)
						
						await interaction.response.send_message("You have left the queue!", ephemeral=True)
						print("✅ Successfully left queue")
					else:
						print("❌ User not in queue")
						await interaction.response.send_message("You are not in this queue!", ephemeral=True)
					
					print("\n🔄 Updating queue embed...")
					await queue_embed(ctx, q.name)
					print("✅ Queue embed updated")
				except Exception as e:
					print("\n❌ ERROR IN LEAVE CALLBACK")
					print(f"Error: {str(e)}")
					print(f"Type: {type(e)}")
					import traceback
					print("Traceback:")
					print(traceback.format_exc())
					try:
						await interaction.response.send_message("An error occurred while leaving the queue!", ephemeral=True)
					except Exception as e2:
						print(f"Failed to send error message: {str(e2)}")

			# Add callbacks to buttons
			join_button.callback = join_callback
			leave_button.callback = leave_callback
			
			# Add buttons to view
			view.add_item(join_button)
			view.add_item(leave_button)
			
			# Store the view
			ctx.qc.queue_views[q.name] = view
			print("✅ Created and stored new view")
		else:
			print(f"📝 Using existing view for queue: {q.name}")
			view = ctx.qc.queue_views[q.name]

		# Handle existing embed
		if q.name in ctx.qc.queue_embeds:
			try:
				print(f"📝 Updating existing embed for queue: {q.name}")
				message = await ctx.channel.fetch_message(ctx.qc.queue_embeds[q.name])
				await message.edit(embed=embed, view=view)
				print("✅ Successfully updated existing embed")
				return
			except Exception as e:
				print(f"❌ Failed to update existing embed: {str(e)}")
				print("🔄 Creating new embed instead")

		# Create new embed
		print(f"📝 Creating new embed for queue: {q.name}")
		message = await ctx.channel.send(embed=embed, view=view)
		ctx.qc.queue_embeds[q.name] = message.id
		print(f"✅ Created new embed with message ID: {message.id}")

		# Register the view with the bot
		print("🔄 Registering view with bot")
		try:
			ctx.interaction.client.add_view(view)
			print("✅ Successfully registered view with bot")
		except Exception as e:
			print(f"❌ Failed to register view: {str(e)}")
			print(f"Error type: {type(e)}")

	except Exception as e:
		print("\n❌ ERROR IN QUEUE_EMBED")
		print(f"Error: {str(e)}")
		print(f"Type: {type(e)}")
		import traceback
		print("Traceback:")
		print(traceback.format_exc())
		await ctx.error(f"An error occurred while creating the queue embed: {str(e)}")
