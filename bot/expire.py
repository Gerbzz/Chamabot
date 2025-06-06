import time

from core.client import dc

import bot

from core.console import log


class ExpireTimer:

	def __init__(self):
		self.tasks = dict()  # hash: Task()
		self.next = None     # Task()

	def serialize(self):
		return [t.serialize() for t in self.tasks.values()]

	async def load_json(self, data):
		for task_data in data:
			try:
				task = await self.ExpireTask.from_json(task_data)
				self.tasks[task.hash] = task
			except bot.Exc.ValueError as e:
				log.error(f"Failed to load expire task '{data}': {str(e)}")
		self._define_next()

	class ExpireTask:

		def __init__(self, qc, member, at):
			self.qc = qc
			self.member = member
			self.at = at
			self.hash = str(self.qc.id) + "_" + str(self.member.id)

		def serialize(self):
			return {'channel_id': self.qc.id, 'member': self.member.id, 'at': self.at}

		@classmethod
		async def from_json(cls, data):
			if (qc := bot.queue_channels.get(data['channel_id'])) is None:
				raise bot.Exc.ValueError(f"QueueChannel is not found.")
			if (guild := dc.get_guild(qc.guild_id)) is None:
				raise bot.Exc.ValueError(f"Guild is not reachable.")
			if (member := guild.get_member(data['member'])) is None:
				raise bot.Exc.ValueError(f"Member is not found.")
			return cls(qc, member, data['at'])

	def set(self, qc, member, delay):
		new_task = self.ExpireTask(qc, member, int(time.time()+delay))
		self.tasks[new_task.hash] = new_task
		self._define_next()

	def get(self, qc, member):
		return self.tasks.get(str(qc.id) + "_" + str(member.id))

	def _define_next(self):
		if len(self.tasks):
			self.next = sorted(self.tasks.values(), key=lambda task: task.at)[0]
		else:
			self.next = None

	def cancel(self, qc, member):
		key = str(qc.id) + "_" + str(member.id)
		if key in self.tasks.keys():
			task = self.tasks.pop(key)
			if self.next and self.next.hash == key:
				self._define_next()

	async def think(self, frame_time):
		if self.next and frame_time >= self.next.at:
			task = self.tasks.pop(self.next.hash)
			self._define_next()
			if task.qc and task.member:
				await task.qc.remove_members(task.member, reason="expire", highlight=True)


expire = ExpireTimer()
