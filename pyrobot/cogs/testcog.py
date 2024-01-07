#  Copyright (c) 2019-2023 ThatRedKite and contributors

import random
import os
import json
import time

import discord
from discord.ext import commands
from discord.ext.commands import has_permissions, MissingPermissions
from redis import asyncio as aioredis

import pyrobot

Q_POOL = []

class PyroTestQuestionButton(discord.ui.Button):
    def __init__(self, ctx: discord.ApplicationContext, answer: str, correct: bool, session):
        super().__init__(label=answer, style=discord.ButtonStyle.blurple)
        self.correct = correct
        self.ctx = ctx
        self.session = session

    async def callback(self, interaction: discord.Interaction):
        if self.correct:
            await interaction.response.send_message("Correct!", ephemeral=True)
            self.session.failed = False
        else:
            await interaction.response.send_message(f"Incorrect! You have {self.session.max_tries-1-self.session.num_tries} attempt(s) remaining.", ephemeral=True)
            self.session.failed = True
        
        self.session.complete = True
        await interaction.message.delete()
        self.view.stop()

class PyroTestQuestionView(discord.ui.View):
    def __init__(self, timeout: int, ctx: discord.ApplicationContext, session, question: dict):
        super().__init__(timeout=timeout)
        self.start_time = time.time()
        self.ctx = ctx
        self.session = session
        self.question = question
        
        for i, answer in enumerate(question["answers"]):
            self.add_item(PyroTestQuestionButton(ctx, answer, i == question["correct"], session))

class PyroTestSession:
    def __init__(self, ctx: discord.ApplicationContext, bot, num_tries, max_tries):
        global Q_POOL
        self.ctx = ctx
        self.did_accept = None
        self.failed = True
        self.bot = bot
        self.complete = False
        self.num_tries = num_tries
        self.max_tries = max_tries
        
        if len(Q_POOL) == 0:
            q_pool_path = os.path.join(self.bot.data_dir, "questions.json")
            if not os.path.exists(q_pool_path):
                json.dump([], open(q_pool_path, "w"))
                raise Exception("No questions.json file found. Please add questions to the file and restart the bot.")
            
            Q_POOL = json.load(open(q_pool_path, "r"))
    
    async def start(self):
        self.failed = False
        self.start_time = time.time()
        
        question = random.choice(Q_POOL)
        embed = discord.Embed(
            title="Pyro Test",
            description=question["question"],
            color=discord.Color.blurple()
        )
        view = PyroTestQuestionView(timeout=30, ctx=self.ctx, session=self, question=question)
        await self.ctx.author.send(embed=embed, view=view)

        timed_out_ = await view.wait()
        if timed_out_:
            await self.ctx.author.send("You ran out of time. Please try again later.")
            self.failed = True
            return
        
        # The user has completed the test
        if not self.failed:
            await self.bot.redis.sadd(f"pyro_test_completed:{self.ctx.guild.id}", self.ctx.author.id)
            await self.bot.redis.delete(f"pyro_test:{self.ctx.guild.id}:{self.ctx.author.id}")
            role_id = await self.bot.redis.get(f"pyro_test_role:{self.ctx.guild.id}")
            if role_id is not None:
                role = self.ctx.guild.get_role(int(role_id))
                await self.ctx.author.add_roles(role)
                await self.ctx.author.send(f"Congratulations! You have passed the test and have been given the {role.mention} role.")
            else:
                await self.ctx.author.send("Congratulations! You have passed the test, However the admins are idiots so please contact them!")
            

class TestAcceptDenyView(discord.ui.View):
    def __init__(self, timeout: int, ctx: discord.ApplicationContext, session: PyroTestSession):
        super().__init__(timeout=timeout)
        self.start_time = time.time()
        self.ctx = ctx
        self.session = session

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.session.did_accept is not None:
            return
        self.session.did_accept = True
        await self.session.bot.redis.incr(f"pyro_test:{self.ctx.guild.id}:{self.ctx.author.id}")
        await self.session.start()

    @discord.ui.button(label="Nevermind", style=discord.ButtonStyle.red)
    async def deny(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.session.did_accept is not None:
            return
        await interaction.response.send_message("You may try again later.")
        await interaction.message.delete()
        self.session.did_accept = False

class TestCog(commands.Cog, name="Pyro Test Cog"):
    def __init__(self, bot):
        self.bot: pyrobot.PyroBot = bot
        self.redis: aioredis.Redis = bot.redis

    pyrotest = discord.SlashCommandGroup(
        "pyrotest",
        "Pyro test commands",
        checks=[]
    )

    async def start_test(self, ctx: discord.ApplicationContext, num_tries, max_tries):
        embed = discord.Embed(
            title="Pyro Test",
            description="You will be asked a random question regarding pyrotechnics. When you are ready to begin, press the Accept button, and you will have 30 seconds to answer the question.",
            color=discord.Color.blurple()
        )
        session = PyroTestSession(ctx, self.bot, num_tries, max_tries)
        await ctx.author.send(embed=embed, view=TestAcceptDenyView(timeout=30, ctx=ctx, session=session))

    @pyrotest.command(
        name="attempt",
        description="Attempt the pyrotechnics test",
        checks=[]
    )
    async def _attempt(self, ctx: discord.ApplicationContext):
        key = f"pyro_test:{ctx.guild.id}:{ctx.author.id}"
        key2 = f"pyro_test_completed:{ctx.guild.id}"

        if await self.redis.sismember(key2, ctx.author.id):
            return await ctx.respond("You have already completed the test.")

        max_tries = await self.redis.get(f"pyro_test_max_tries:{ctx.guild.id}")
        num_tries = await self.redis.get(key)
        if num_tries is None:
            num_tries = 0
        else:
            num_tries = int(num_tries)
        
        if max_tries is None:
            max_tries = 3
            await self.redis.set(f"pyro_test_max_tries:{ctx.guild.id}", max_tries)
        else:
            max_tries = int(max_tries)
        
        if num_tries >= max_tries:
            return await ctx.respond(f"You have already attempted the test {max_tries} times. Please contact an administrator if you would like to try it again.")
        
        await ctx.respond(f"Please check your DMs for instructions on how to complete the test.")

        await self.start_test(ctx, num_tries, max_tries)
    
    @pyrotest.command(
        name="setrole",
        description="Set the role that users will receive upon completing the test",
    )
    @has_permissions(administrator=True)
    async def _setrole(self, ctx: discord.ApplicationContext, role: discord.Role):
        await self.redis.set(f"pyro_test_role:{ctx.guild.id}", role.id)
        await ctx.respond(f"Successfully set the role to {role.mention}.")

    @pyrotest.command(
        name="maxtries",
        description="Set the maximum number of tries a user can attempt the test",
    )
    @has_permissions(administrator=True)
    async def _maxtries(self, ctx: discord.ApplicationContext, num_tries: int):
        await ctx.respond(f"Successfully set the maximum number of tries to {num_tries}.")
        await self.redis.set(f"pyro_test_max_tries:{ctx.guild.id}", num_tries)

    @pyrotest.command(
        name="reset",
        description="Reset a user's test attempts",
    )
    @has_permissions(administrator=True)
    async def _reset(self, ctx: discord.ApplicationContext, member: discord.Member):
        await self.redis.delete(f"pyro_test:{ctx.guild.id}:{member.id}")
        await self.redis.srem(f"pyro_test_completed:{ctx.guild.id}", member.id)
        await ctx.respond(f"Successfully reset {member.mention}'s test attempts.")
    
    @_reset.error
    @_maxtries.error
    @_setrole.error
    async def pyrotest_error(self, ctx: discord.ApplicationContext, error):
        if isinstance(error, MissingPermissions):
            await ctx.respond("You do not have permission to use this command.")

def setup(bot):
    bot.add_cog(TestCog(bot))
