import discord
import asyncio
from difflib import get_close_matches

from bot_config import env_int

async def run(interaction,bot,cells):
    headers = cells[0]
    cells = cells[1:]
    taglist = []
    guild_id = interaction.guild_id
    missing = {}
    cells = [c for c in cells if c != []]
    rolenameList = []
    el_guild_id = env_int("EL_GUILD_ID")
    testing_guild_id = env_int("TESTING_GUILD_ID")
    #EL
    if guild_id in {el_guild_id, testing_guild_id}:
        if guild_id == testing_guild_id:
            guild_id = el_guild_id
        for i in cells:
            if i[headers.index('Discord Tags')] != '':
                taglist.append(i[headers.index('Discord Tags')])
                rolenameList.append(i[headers.index('Author rank')])

    taglist = [t for t in taglist if t != '' and t != 'ignore' and t != 'DISCORD ID' and t != 'Discord ID']
    guild = bot.get_guild(guild_id)
    guild_members = guild.members
    close_tags_msg_list = []
    no_close_tags = []
    for index, author_tag in enumerate(taglist):
        name = author_tag.lower().strip("@")
        try:
            memberObj = discord.utils.get(guild_members,name=name)
            if memberObj is None:
                close_tags = []
                for i in guild_members:
                    if get_close_matches(name,[i.name]) != []:
                        close_tags.append(i)
                if len(close_tags) == 0:
                    no_close_tags.append(author_tag)
                if len(close_tags) > 0:
                    missing[author_tag] = close_tags
        except ValueError:
            no_close_tags.append(author_tag)
    if len(missing) > 0:
        print("adding missing to message list")
        for key in missing:
            if len(missing[key]) == 1:
                close_tags_msg_list.append(f'{key} is not an account in the discord, but {missing[key][0].mention} is probably them.\n')
            elif len(missing[key]) > 1:
                close_tags_msg_list.append(f'{key} is not an account in the discord, but they could be one of the following:\n')
                for j in missing[key]:
                    close_tags_msg_list.append(f'{j.mention}\n')
    elif len(missing) == 0 and len(no_close_tags) == 0:
        await interaction.response.send_message('All members are in the discord!',ephemeral=False)

    if len(close_tags_msg_list) > 15:
        for n,i in enumerate(close_tags_msg_list):
            if n % 15 == 0:
                try:
                    message = ''.join(close_tags_msg_list[n:n+15])
                except IndexError:
                    message = ''.join(close_tags_msg_list[n:])
                await interaction.response.send_message(message,ephemeral=False)
    elif len(close_tags_msg_list) > 0:
        await interaction.response.send_message(''.join(close_tags_msg_list),ephemeral=False)
    msg_to_send = []
    msg_to_send.append("Members not in the discord:\n")
    temp_msg = []
    msg_chars = 0
    for i in no_close_tags:
        if msg_chars + len(i) > 1500:
            temp_msg[-1] = temp_msg[-1] + '\n'
            msg_to_send.append('\n'.join(temp_msg))
            msg_chars = 0
            temp_msg = []

        temp_msg.append(i)
        msg_chars += len(i) + 2 #2 is added to account for newline characters

    if len(temp_msg) > 0:
        msg_to_send.append('\n'.join(temp_msg))
    elif len(msg_to_send) == 1:
        return None

    return msg_to_send
