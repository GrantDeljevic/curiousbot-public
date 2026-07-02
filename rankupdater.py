import discord
import asyncio

from bot_config import require_env

async def start(ctx,bot,cells):

    found = False
    guild_id = int(require_env("EL_GUILD_ID"))
    authorranklist = ['Author','Bronze Author {0+}','Gold Author {1500+}','Topaz Author {2500+}','Ruby Author {6500+}','Onyx Author {500+}','Copper Author {200+}','Silver Author {800+}','Diamond Author {10000+}','Garnet Author {4000+}','Peridot Author {20000+}','Emerald Author {35000+}','Sapphire Author {15000+}']

    cells = [c for c in cells if c != []]

    #set variable to the last column in cells that is non 0
    rankcol = cells[0].index('Author rank')
    tagcol = cells[0].index('Discord Tags')
    author_dict = {}
    for i in cells[1:]:
        try:
            if i[rankcol] in authorranklist and i[tagcol] != '':
                author_dict[i[tagcol]] = i[rankcol]
        except IndexError:
            continue
    guild = bot.get_guild(guild_id)
    messagelist = []
    for tag in author_dict:
        member = guild.get_member_named(tag)
        if member is not None:
            newrolename = author_dict[tag]
            newrole = discord.utils.get(guild.roles, name=newrolename)
            if newrole in member.roles:
                continue
            for role in member.roles:
                if role.name in authorranklist:
                    found = True
                    oldrole = role
                    break
            await member.add_roles(newrole)
            if found == True:
                found = False
                await member.remove_roles(oldrole)
                messagelist.append(f'Updated {member.mention} from {oldrole.name} to {newrolename}\n')
            else:
                messagelist.append(f'Added {member.mention} to {newrolename}\n')
    try:
        await ctx.send(''.join(messagelist))
    except discord.errors.HTTPException:
        await ctx.send(''.join(messagelist[:30]))
        if len(messagelist) > 30:
            await ctx.send(''.join(messagelist[30:60]))
        if len(messagelist) > 60:
            await ctx.send(''.join(messagelist[60:]))
