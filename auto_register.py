import pygsheets
from ffwebscrape import followcount, get_story_info
import discord
import asyncio
from difflib import get_close_matches
import os

from bot_config import google_client, require_env

AUTHORLIST_KEY_ENV = "AUTHORLIST_KEY"
BIWEEKLY_AUTHORLIST_KEY_ENV = "BIWEEKLY_AUTHORLIST_KEY"
tab = 'Authorlist'


def authorlist_key():
    return (
        os.getenv(AUTHORLIST_KEY_ENV)
        or os.getenv(BIWEEKLY_AUTHORLIST_KEY_ENV)
        or require_env(AUTHORLIST_KEY_ENV)
    )

def sheet(dockey,sheet):
    gc = google_client()
    target = gc.open_by_key(dockey).worksheet_by_title(sheet)
    cells = target.get_all_values(include_tailing_empty_rows=False, include_tailing_empty=False, returnas='matrix')
    return cells,target

#returns whether the story was successfully registered
def register(authordict):
    key = authorlist_key()
    cells,target = sheet(key,tab)
    tagcol = cells[0].index('Discord Tags')
    rankcol = cells[0].index('Author rank')
    target_row = None
    for rownum,row in enumerate(cells):
        try:
            if row == []:
                target_row = rownum
                break
            elif row[tagcol] == '':
                target_row = rownum
                break
        except KeyError:
            target_row = rownum
            break
    if target_row is None:
        #add more rows
        target_row = len(cells)
        target.insert_rows(target_row,10)
        
    fandomcells,fandomtarget = sheet(key,'Data')
    fandom = ''
    fandomcol = fandomcells[0].index('Fandom List')
    fandomlist = fandomtarget.get_col(fandomcol+1,include_empty=False)[1:]
    try:
        if authordict['fandom'] in fandomlist:
            fandom = authordict['fandom']
        elif get_close_matches(authordict['fandom'],fandomlist,cutoff=0.8) != []:
            fandom = get_close_matches(authordict['fandom'],fandomlist,cutoff=0.8)[0]
    except KeyError:
        fandom = ''
    if 'fanfiction.net/' in authordict['mainstory']:
        platform = 0
        scrapedFandom, title = get_story_info(authordict['mainstory'],platform)
        if scrapedFandom:
            fandom = scrapedFandom
    else:
        title = ''

    target.update_row(target_row+1,[authordict['penname'],'',authordict['tag'],authordict['link'],fandom,title,authordict['mainstory']])
    try:
        target.update_value((target_row+1,rankcol),authordict['follownum'])
    except:
        target.update_value((target_row+1,rankcol),0)

    try:
        if authordict['secondlink'] != None:
            try:
                if 'archiveofourown.org/users/' in authordict['secondlink']:
                    platform = 1
                elif 'fanfiction.net/' in authordict['secondlink']:
                    platform = 0
                elif 'tapas.io' in authordict['secondlink']:
                    platform = 2

                secondary_follows = followcount(authordict['secondlink'],platform)
                if secondary_follows != False:
                    target.update_row(target_row+2,[authordict['penname'],'',authordict['tag'],authordict['secondlink']])
                    target.update_value((target_row+2,rankcol),secondary_follows)
            except:
                pass
    except:
        pass
    if title != '':
        return True
    else:
        return False

def remove(tag):
    cells,target = sheet(authorlist_key(),tab)
    rankcol = cells[0].index('Author rank')
    blankrow = ['' for _ in range(rankcol)]
    tagcol = cells[0].index('Discord Tags')
    name = tag.split('#')[0]
    for rownum,row in enumerate(cells):
        if row[tagcol] in [name, tag]:
            target.update_row(rownum+1,blankrow)
            return True

    return False

async def autoRole(author,follows,guild):

    # authorrankdict = {"Emerald Author {35000+}": 35000, "Peridot Author {20000+}": 20000, "Sapphire Author {15000+}": 15000,
    #                   "Diamond Author {10000+}": 10000, "Ruby Author {6500+}": 6500, "Garnet Author {4000+}": 4000,
    #                   "Topaz Author {2500+}": 2500, "Gold Author {1500+}": 1500, "Silver Author {800+}": 800,
    #                   "Onyx Author {500+}": 500, "Copper Author {200+}": 200, "Bronze Author {0+}": 1, "Author": 0}
    authorranklist = ['Author','Bronze Author {0+}','Gold Author {1500+}','Topaz Author {2500+}','Ruby Author {6500+}','Onyx Author {500+}','Copper Author {200+}','Silver Author {800+}','Diamond Author {10000+}','Garnet Author {4000+}','Peridot Author {20000+}','Emerald Author {35000+}','Sapphire Author {15000+}']
    authorrankfollowslist = [int(i.split('{')[1].split('+')[0]) for i in authorranklist[1:]]
    authorrankdict = dict(zip(authorranklist,authorrankfollowslist))
    role = None
    for followreq in authorrankdict:
        if follows >= authorrankdict[followreq]:
            #if follows is 0, role is Author. If follows is >0, role is the highest rank that follows is greater than.
            if follows == 0:
                role = discord.utils.get(guild.roles, name='Author')
            else:
                role = discord.utils.get(guild.roles, name=followreq)
    if role is not None:
        await author.add_roles(role)
