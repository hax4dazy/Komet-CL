import config
import discord
import io
import urllib.parse
from discord.ext.commands import Cog

class Lists(Cog):
    """
    Manages channels that are dedicated to lists.
    """

    def __init__(self, bot):
        self.bot = bot

    # Helpers

    def check_if_target_is_staff(self, target):
        return any(r.id in config.staff_role_ids for r in target.roles)

    def is_edit(self, emoji):
        return str(emoji)[0] == u'✏' or str(emoji)[0] == u'📝'

    def is_delete(self, emoji):
        return str(emoji)[0] == u'❌' or str(emoji)[0] == u'❎'

    def is_recycle(self, emoji):
        return str(emoji)[0] == u'♻'

    def is_insert_above(self, emoji):
        return str(emoji)[0] == u'⤴️' or str(emoji)[0] == u'⬆'

    def is_insert_below(self, emoji):
        return str(emoji)[0] == u'⤵️' or str(emoji)[0] == u'⬇'

    def is_reaction_valid(self, reaction):
        allowed_reactions = [
            u'✏',
            u'📝',
            u'❌',
            u'❎',
            u'♻',
            u'⤴️',
            u'⬆',
            u'⬇',
            u'⤵️',
        ]
        return str(reaction.emoji)[0] in allowed_reactions

    async def find_reactions(self, user_id, channel_id, limit = None):
        reactions = []
        channel = self.bot.get_channel(channel_id)
        async for message in channel.history(limit = limit):
            if len(message.reactions) == 0:
                continue

            for reaction in message.reactions:
                users = await reaction.users().flatten()
                user_ids = map(lambda user: user.id, users)
                if user_id in user_ids:
                    reactions.append(reaction)
        
        return reactions

    def create_log_message(self, emoji, action, user, channel, reason = ''):
        msg = f'{emoji} **{action}** \n'\
            f'from {self.bot.escape_message(user.name)} ({user.id}), in {channel.mention}'

        if reason != '':
            msg += f':\n`{reason}`'
        
        return msg

    # Listeners

    @Cog.listener()
    async def on_raw_reaction_add(self, payload):
        await self.bot.wait_until_ready()

        # We only care about reactions in Rules, and Support FAQ
        if payload.channel_id not in config.list_channels:
            return

        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        member = channel.guild.get_member(payload.user_id)
        user = self.bot.get_user(payload.user_id)
        reaction = next((reaction for reaction in message.reactions if str(reaction.emoji) == str(payload.emoji)), None)
        if reaction is None:
            return

        # Only staff can add reactions in these channels.
        if not self.check_if_target_is_staff(member):
            await reaction.remove(user)
            return

        # Reactions are only allowed on messages from the bot.
        if not message.author.bot:
            await reaction.remove(user)
            return

        # Only certain reactions are allowed.
        if not self.is_reaction_valid(reaction):
            await reaction.remove(user)
            return

        # Remove all other reactions from user in this channel.
        for r in await self.find_reactions(payload.user_id, payload.channel_id):
            if r.message.id != message.id or (r.message.id == message.id  and str(r.emoji) != str(reaction.emoji)):
                await r.remove(user)

        # When editing we want to provide the user a copy of the raw text.
        if self.is_edit(reaction.emoji):
            files_channel = self.bot.get_channel(config.list_files_channel)
            file = discord.File(io.BytesIO(message.content.encode('utf-8')), filename = f'{message.id}.txt')
            file_message = await files_channel.send(file = file)

            embed = discord.Embed(
                title = 'Click here to get the raw text to modify.',
                url = f'{file_message.attachments[0].url}?'
            )
            embed.add_field(name = "Message ID", value = file_message.id, inline = False)
            await message.edit(embed = embed)

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        await self.bot.wait_until_ready()

        # We only care about reactions in Rules, and Support FAQ
        if payload.channel_id not in config.list_channels:
            return

        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)

        # Reaction was removed from a message we don't care about.
        if not message.author.bot:
            return

        # We want to remove the embed we added.
        if self.is_edit(payload.emoji):
            embeds = message.embeds
            if len(embeds) == 0:
                return

            fields = embeds[0].fields
            for field in fields:
                if field.name == 'Message ID':
                    files_channel = self.bot.get_channel(config.list_files_channel)
                    file_message = await files_channel.fetch_message(int(field.value))
                    await file_message.delete()
            
            await message.edit(embed = None)

        
    @Cog.listener()
    async def on_message(self, message):
        await self.bot.wait_until_ready()

        # We only care about messages in Rules, and Support FAQ
        if message.channel.id not in config.list_channels:
            return
            
        # We don't care about messages from bots.
        if message.author.bot:
            return

        # Only staff can modify lists.
        if not self.check_if_target_is_staff(message.author):
            await message.delete()
            return

        log_channel = self.bot.get_channel(config.log_channel)
        channel = message.channel
        content = message.content
        user = message.author
        await message.delete()

        reactions = await self.find_reactions(user.id, channel.id)

        # Add to the end of the list if there is no reactions or somehow more than one.
        if len(reactions) != 1:
            await channel.send(content)
            for reaction in reactions:
                await reaction.remove(user)

            await log_channel.send(self.create_log_message("💬", "List item added:", user, channel))
            return

        targeted_reaction = reactions[0]
        targeted_message = targeted_reaction.message

        if self.is_edit(targeted_reaction):
            await targeted_message.edit(content = content)
            await targeted_reaction.remove(user)

            await log_channel.send(self.create_log_message("📝", "List item edited:", user, channel))

        elif self.is_delete(targeted_reaction):
            await targeted_message.delete()

            await log_channel.send(self.create_log_message("❌", "List item deleted:", user, channel, content))

        elif self.is_recycle(targeted_reaction):
            messages = await channel.history(limit = None, after = targeted_message, oldest_first = True).flatten()
            await channel.purge(limit = len(messages) + 1, bulk = True)

            await channel.send(targeted_message.content)
            for message in messages:
                await channel.send(message.content)

            await log_channel.send(self.create_log_message("♻", "List item recycled:", user, channel, content))

        elif self.is_insert_above(targeted_reaction):
            messages = await channel.history(limit = None, after = targeted_message, oldest_first = True).flatten()
            await channel.purge(limit = len(messages) + 1, bulk = True)

            await channel.send(content)
            await channel.send(targeted_message.content)
            for message in messages:
                self.bot.log.info(message.content)
                await channel.send(message.content)

            await log_channel.send(self.create_log_message("💬", "List item added:", user, channel))

        elif self.is_insert_below(targeted_reaction):
            messages = await channel.history(limit = None, after = targeted_message, oldest_first = True).flatten()
            await channel.purge(limit = len(messages) + 1, bulk = True)

            await channel.send(targeted_message.content)
            await channel.send(content)
            for message in messages:
                self.bot.log.info(message.content)
                await channel.send(message.content)

            await log_channel.send(self.create_log_message("💬", "List item added:", user, channel))

def setup(bot):
    bot.add_cog(Lists(bot))
