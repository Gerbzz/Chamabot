# -*- coding: utf-8 -*-
import sys
import os
import datetime
from threading import Thread
from multiprocessing import Queue
import rlcompleter  # this does python autocomplete by tab
try:
	import readline
except ModuleNotFoundError:  # windows support
	import pyreadline as readline

from core.config import cfg

LogLevelToInt = {
	'CHAT': 0,
	'DEBUG': 1,
	'COMMANDS': 2,
	'INFO': 3,
	'ERRORS': 4,
	'NOTHING': 5
}


class Log:

	def __init__(self):
		# Create log dir if needed
		if not os.path.exists(os.path.abspath("logs")):
			os.makedirs('logs')

		self.file = open(datetime.datetime.now().strftime("logs/log_%Y-%m-%d-%H:%M"), 'w', encoding='utf-8')
		self.loglevel = LogLevelToInt[cfg.LOG_LEVEL]

	@staticmethod
	def display(string):
		# Have to do this encoding/decoding bullshit because python fails to encode some symbols by default
		string = string.encode(sys.stdout.encoding, 'ignore').decode(sys.stdout.encoding)

		# Save user input line, print string and then user input line
		line_buffer = readline.get_line_buffer()
		sys.stdout.write("\r\n\033[F\033[K" + string + '\r\n>' + line_buffer)

	def log(self, data, log_level):
		string = str(data)
		string = "{}|{}> {}".format(
			datetime.datetime.now().strftime("%d.%m.%Y (%H:%M:%S)"),
			log_level,
			string)
		self.display(string)
		self.file.write(string + '\r\n')

	def close(self):
		self.file.close()

	def chat(self, data):
		if self.loglevel <= 0:
			self.log(data, 'CHAT')

	def debug(self, data):
		if self.loglevel == 1:
			self.log(data, 'DEBUG')

	def command(self, data):
		if self.loglevel <= 2:
			self.log(data, 'COMMANDS')

	def info(self, data):
		if self.loglevel <= 3:
			self.log(data, 'INFO')

	def error(self, data):
		if self.loglevel <= 4:
			self.log(data, 'ERROR')
		

def user_input():
	"""Listen for user input in a separate thread.

	In production the bot often runs under a service manager without an interactive
	TTY attached. In that case, calling ``input`` raises ``EOFError`` immediately
	and crashes the thread, taking the whole application down. We catch that
	exception (and ``KeyboardInterrupt``) and exit the thread gracefully instead
	of letting it propagate.
	"""
	try:
		readline.parse_and_bind("tab: complete")
		while True:
			try:
				input_cmd = input('>')
			except EOFError:
				# Non-interactive shell – stop listening without killing the bot.
				log.info("Console input closed (EOF). Exiting input thread.")
				break
			except KeyboardInterrupt:
				log.info("Console input interrupted with Ctrl+C. Exiting input thread.")
				break

			# Put the command in the queue only if we actually received something.
			if input_cmd:
				user_input_queue.put(input_cmd)
	except Exception as e:
		log.error(f"Error in console input thread: {e}")


def terminate():
	global alive
	alive = False


alive = True
log = Log()
user_input_queue = Queue()

# Init user console
thread = Thread(target=user_input, name="user_input")
thread.daemon = True
thread.start()
