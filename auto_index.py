from elupdate import sheet
import discord
from discord.ext import commands
import os

from bot_config import require_env

AUTHORLIST_KEY_ENV = "AUTHORLIST_KEY"
BIWEEKLY_AUTHORLIST_KEY_ENV = "BIWEEKLY_AUTHORLIST_KEY"
AUTHOR_INDEX_CONTACT_USER_ID = os.getenv("AUTHOR_INDEX_CONTACT_USER_ID", "")
authorlistsheet = 'Authorlist'


def authorlist_key():
    return (
        os.getenv(AUTHORLIST_KEY_ENV)
        or os.getenv(BIWEEKLY_AUTHORLIST_KEY_ENV)
        or require_env(AUTHORLIST_KEY_ENV)
    )


def generate_index():
    cells,target = sheet(authorlist_key(),authorlistsheet)
    fandom = cells[0].index('Fandom')
    penname = cells[0].index('Pen Names')
    profile_link = cells[0].index('Links')
    story_link = cells[0].index('Main Story Link')
    story_title = cells[0].index('Main Story Name')
    index_dict = {}
    for row in cells[1:]:
        if row[story_title] == '':
            continue
        else:
            author_entry = [row[penname],row[profile_link],row[story_title],row[story_link]]
            if row[fandom] in index_dict:

                index_dict[row[fandom]] = index_dict[row[fandom]] + [author_entry]
            else:
                index_dict[row[fandom]] = [author_entry]
    return index_dict

def format_index(index_dict):
    contact = f"<@{AUTHOR_INDEX_CONTACT_USER_ID}>" if AUTHOR_INDEX_CONTACT_USER_ID else "server staff"
    info_embed = discord.Embed(description=f'If you are unsatisfied and wish to change the category you\'ve been put under, the name you\'ve been put under as or the story that has been entered here, please message {contact}.',color=0xed0909)
    index_list = []
    index_list.append(info_embed)
    for fandom in index_dict:
        fandom_list = []
        fandom_title = f'-+-{fandom}-+-'
        for author_entry in index_dict[fandom]:
            entry_text = f'[{author_entry[0]}]({author_entry[1]}) - [{author_entry[2]}]({author_entry[3]})\n'
            if len(fandom_list) >= 30:
                fandom_embed = discord.Embed(title=fandom_title,description=''.join(fandom_list),color=0x00ff00)
                fandom_title = ''
                index_list.append(fandom_embed)
                fandom_list = []
            else:
                fandom_list.append(entry_text)
        fandom_embed = discord.Embed(title=fandom_title,description=''.join(fandom_list),color=0x00ff00)
        index_list.append(fandom_embed)

    return index_list

def run_index():
    index_dict = generate_index()
    index_list = format_index(index_dict)
    return index_list
