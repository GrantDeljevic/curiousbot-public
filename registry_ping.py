import re
from difflib import get_close_matches
import discord
import asyncio
import traceback
import ffwebscrape
import auto_register
from bot_config import env_int

async def check_for_member(message,type):
    parsed_tag = message.embeds[0].fields[0].value

    if type == "error reporter":
        for i in message.embeds[0].fields:
            if i.name == "Display Name":
                parsed_tag = i.value
    elif type == "author":
        authordict = {'mainstory':''}
        for i in message.embeds[0].fields:
            if i.name == "Do you write original works, or fanfiction?":
                authordict['fforiginal'] = i.value
            elif i.name == "Which site do you use the most?":
                authordict['mainsite'] = i.value
            elif i.name == "Please submit a link to your fanfiction.net or AO3 account here, if you have one.":
                authordict['link'] = i.value
            elif i.name == "If you have any accounts not input above, please link them here!":
                authordict['secondlink'] = i.value
            elif i.name == "If you write fanfiction, what would you consider your main fandom? (Please only list one. If you write original works, leave this blank or write \'original\'.)":
                authordict['fandom'] = i.value
            elif i.name == "Which of your stories would you like to have linked in Author\'s Index? (You may only choose one)":
                authordict['mainstory'] = i.value
            elif i.name == "What is your pen name?":
                authordict['penname'] = i.value
        try:
            if authordict['link'] != None:
                if "fanfiction.net/" in authordict['link']:
                    platform = 0
                elif "archiveofourown.org/users/" in authordict['link']:
                    platform = 1
                elif 'tapas.io' in authordict['link']:
                    platform = 2
                if 'platform' in locals():
                    authordict['follownum'] = ffwebscrape.followcount(authordict['link'],platform)
                    if authordict['follownum'] == False:
                        authordict['follownum'] = 0
                    await message.channel.send(f"This author has {authordict['follownum']} follows")
                else:
                    authordict['follownum'] = 0
            else:
                authordict['follownum'] = 0
                authordict['link'] = ""
        except:
            authordict['follownum'] = 0
            authordict['link'] = ""
            print("handled: ", traceback.format_exc())
    #make name lowercase
    name = parsed_tag.lower().strip('@')
    guild = message.guild
    guild_members = guild.members
    owner_user_id = env_int("OWNER_USER_ID")
    beats = discord.utils.get(guild_members, id=owner_user_id) if owner_user_id else None
    try:
        found_user = discord.utils.get(guild_members, name=name)
        if type == "author":
            authordict['tag'] = found_user.name
            try:
                await auto_register.autoRole(found_user,authordict['follownum'],guild)
                try:
                    found_story_info = auto_register.register(authordict)
                    if found_story_info:
                        reply_message = f"{found_user.mention} has been added to the authorlist with their fandom and story information, and been auto-assigned an author role."
                    else:
                        reply_message = f"{found_user.mention} has been added to the authorlist and been auto-assigned an author role. Please manually add their fandom and story information."
                    await message.reply(reply_message)
                except:
                    await message.reply(f"{found_user.mention} has been added to their author role, but needs to be added to the authorlist.")
                    print("handled: ", traceback.format_exc())
                    if beats is not None:
                        await beats.send(f"Error with auto registry, dummy. Error Message: \n\n{traceback.format_exc()}")
            except:
                await message.reply(f"{found_user.mention} needs to be added to their author role and the authorlist.")
                print("handled: ", traceback.format_exc())
                if beats is not None:
                    await beats.send(f"Failed autorole. Error Message: \n\n{traceback.format_exc()}")
        elif found_user is not None:
            await message.reply(f"{found_user.mention}")

        elif found_user is None:
            raise AttributeError
    except AttributeError:
        doesNotExist = f"We cannot find this {type}'s tag in the archives. If it is not in the archives, it does not exist."
        close_tags = []
        for i in guild_members:
            if get_close_matches(name,[i.name]) != []:
                close_tags.append(i.name)
                if len(close_tags) > 3:
                    break

        if len(close_tags) == 0:
            await message.reply(doesNotExist)
            return False
        
        elif len(close_tags) <= 3:
            pinged = False
            for close_tag in close_tags:
                found_user = discord.utils.get(guild_members, name=close_tag)
                if found_user is not None:
                    await message.reply(f"This may be your {type}. {found_user.mention}")
                    pinged = True

                #add thumbs up reaction to confirmation message
                    # await confirmation.add_reaction("👍")
            if not pinged:
                await message.reply(doesNotExist)
        else:
            await message.reply("There are too many close matches for this tag.")
