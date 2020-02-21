import discord
import config
from discord.ext.commands import Cog

class Lists(Cog):
    """
    Manages lists for Rules and Support FAQ
    """

    def __init__(self, bot):
        self.bot = bot
        self.cache = {}

    def check_if_target_is_staff(self, target):
        return any(r.id in config.staff_role_ids for r in target.roles)

    @Cog.listener()
    async def on_raw_reaction_add(self, payload):
        await self.bot.wait_until_ready()

        # We only care about reactions in Rules, and Support FAQ
        if payload.channel_id not in [config.rules_channel, config.support_faq_channel]:
            return

        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        user = self.bot.get_user(payload.user_id)
        reaction = next((reaction for reaction in message.reactions if str(reaction.emoji) == str(payload.emoji)), None)
        if reaction is None:
            return

        # Only staff can add reactions in these channels.
        if not self.check_if_target_is_staff(message.author):
            await reaction.remove(user)
            return

        # Reactions are only allowed on messages from the bot.
        if not message.author.bot:
            await reaction.remove(user)
            return

        # Only certain reactions are allowed.
        allowed_reactions = [
            3576248693861070078,    # ✏
            -6319061654185249973,   # ❌
            -7122347705770508324,   # ❎
            -2335661887491907069,   # ⬇
            6404897248308065578     # ⬆
        ]
        if hash(reaction.emoji) not in allowed_reactions:
            await reaction.remove(user)
            return

        # Remove already existing 
        if user.id in self.cache:
            cache = self.cache[user.id]
            cached_channel = self.bot.get_channel(cache['channel'])
            cached_message = await cached_channel.fetch_message(cache['message'])
            cached_reaction = next((r for r in cached_message.reactions if hash(r.emoji) == cache['reaction']), None)
            if cached_reaction is not None:
                await cached_reaction.remove(user)

        # Add reaction to our cache.
        self.cache[user.id] = {
            'channel': payload.channel_id,
            'message': payload.message_id,
            'reaction': hash(reaction.emoji)
        }

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        await self.bot.wait_until_ready()

        # We only care about reactions in Rules, and Support FAQ
        if payload.channel_id not in [config.rules_channel, config.support_faq_channel]:
            return

        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)

        # Reaction was removed from a message we don't care about.
        if not message.author.bot:
            return

        # Remove the reaction from our cache.
        if payload.user_id in self.cache:
            del self.cache[payload.user_id]

    @Cog.listener()
    async def on_message(self, message):
        await self.bot.wait_until_ready()

        # We only care about messages in Rules, and Support FAQ
        if message.channel.id not in [config.rules_channel, config.support_faq_channel]:
            return

        # Only staff can modify lists.
        if not self.check_if_target_is_staff(message.author):
            await message.delete()
            return

        # User must not have a reaction set.
        if user.id not in self.cache:
            await message.delete()
            return

def setup(bot):
    bot.add_cog(Lists(bot))
