import os
import logging
import json
import sys
from abc import ABC
from datetime import datetime
from pathlib import Path

import aiohttp
import discord
from redis import asyncio as aioredis
from discord.ext import bridge

from .extensions import ENABLED_EXTENSIONS

__name__ = "PyroBot"
__version__ = "0.0.1"
__author__ = "John Woo"

data_dir = "/app/data"
dir_name = "/app/pyrobot"

intents = discord.Intents.all()

# check if the init_settings.json file exists and if not, create it
if not Path(os.path.join(data_dir, "init_settings.json")).exists():
    print("No init_settings.json file found. Creating one now.")
    settings_dict_empty = {
        "discord token": "",
    }
    # write the dict as json to the init_settings.json file with the json library
    with open(os.path.join(data_dir, "init_settings.json"), "w") as f:
        # dump the dict as json to the file with an indent of 4 and support for utf-8
        json.dump(settings_dict_empty, f, indent=4, ensure_ascii=False)
    # make the user 1000 the owner of the file, so they can edit it
    os.chown(os.path.join(data_dir, "init_settings.json"), 1000, 1000)

    # exit the program
    exit(1)

# load the init_settings.json file with the json library
with open(os.path.join(data_dir, "init_settings.json"), "r") as f:
    try:
        settings_dict = json.load(f)
        # get the discord token, the tenor api key, and the prefix from the dict
        discord_token = settings_dict["discord token"]

    except json.decoder.JSONDecodeError:
        print("init_settings.json is not valid json. Please fix it.")
        exit(1)


# define the bot class
class PyroBot(bridge.Bot, ABC):
    def __init__(self, dir_name, help_command=None, description=None, **options):
        super().__init__(help_command=help_command, description=description, **options)
        # paths
        self.dir_name = dir_name
        self.data_dir = "/app/data/"
        self.temp_dir = "/tmp/"

        # info
        self.version = __version__
        self.start_time = datetime.now()
        self.pid = os.getpid()

        try:
            self.redis = aioredis.Redis(host="redis", db=1, decode_responses=True)
        except aioredis.ConnectionError:
            exit(1)
    async def aiohttp_start(self):
        self.aiohttp_session = aiohttp.ClientSession()


# create the bot instance

bot = PyroBot(dir_name, intents=intents)

# load the cogs aka extensions
bot.load_extensions(*ENABLED_EXTENSIONS, store=False)

extensions = [extension.split(".")[-1] for extension in ENABLED_EXTENSIONS]

# try to start the bot with the token from the init_settings.json file catch any login errors
try:
    bot.run(discord_token)
except discord.LoginFailure:
    exit(1)