
import asyncio
import os
import sys
import time
import traceback
import typing
import warnings
from discord import app_commands, Interaction, Embed, User
import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ext import commands
from dotenv import load_dotenv
import re

from bot_config import env_int, env_ints, env_strings, google_client, require_env

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot_kwargs = {}
application_id = env_int("CURIOUSBOT_APPLICATION_ID")
if application_id is not None:
    bot_kwargs["application_id"] = application_id
bot = commands.Bot("`",intents=intents,help_command=None,**bot_kwargs)
run_weekly = False
scheduler = AsyncIOScheduler()
warnings.filterwarnings('ignore','.*PytzU*.')
warnings.filterwarnings('ignore','.*apscheduler*.')

AUTHORLIST_KEY_ENV = "AUTHORLIST_KEY"
BIWEEKLY_AUTHORLIST_KEY_ENV = "BIWEEKLY_AUTHORLIST_KEY"
OWNER_USER_ID = env_int("OWNER_USER_ID")
BOT_USER_ID = env_int("CURIOUSBOT_USER_ID", application_id)
EL_GUILD_ID = env_int("EL_GUILD_ID")
TESTING_GUILD_ID = env_int("TESTING_GUILD_ID")
SENATE_GUILD_ID = env_int("SENATE_GUILD_ID")
SENATE_ROSTER_KEY = os.getenv("SENATE_ROSTER_KEY", "")
SENATE_ROSTER_SHEET = os.getenv("SENATE_ROSTER_SHEET", "Senate Roster")
WEEKLY_SHEET = os.getenv("WEEKLY_SHEET", "Weekly Update")
OPERATIONS_CHANNEL_ID = env_int("OPERATIONS_CHANNEL_ID")
BOTS_AND_UPDATES_CHANNEL_ID = env_int("BOTS_AND_UPDATES_CHANNEL_ID")
JUNKYARD_CHANNEL_ID = env_int("JUNKYARD_CHANNEL_ID")
AUTHOR_INDEX_CHANNEL_ID = env_int("AUTHOR_INDEX_CHANNEL_ID")
AUTHOR_NAME_CHANGE_CHANNEL_ID = env_int("AUTHOR_NAME_CHANGE_CHANNEL_ID")
MD_CHANNEL_ID = env_int("MD_CHANNEL_ID")
MD_GUILD_ID = env_int("MD_GUILD_ID")
MD_ROLE_ID = env_int("MD_ROLE_ID")
COUNCIL_ADMIN_ROLE_ID = env_int("COUNCIL_ADMIN_ROLE_ID")
MANAGEMENT_ROLE_ID = env_int("MANAGEMENT_ROLE_ID")
CHAIRMAN_ROLE_ID = env_int("CHAIRMAN_ROLE_ID")
CONFIRMATION_CHANNEL_IDS = set(env_ints("CONFIRMATION_CHANNEL_IDS"))
FIC_PROMO_SOURCE_AUTHOR_ID = env_int("FIC_PROMO_SOURCE_AUTHOR_ID")
FIC_PROMO_SOURCE_CHANNEL_ID = env_int("FIC_PROMO_SOURCE_CHANNEL_ID")
FIC_PROMO_TARGET_CHANNEL_ID = env_int("FIC_PROMO_TARGET_CHANNEL_ID")
FIC_PROMO_REQUIRED_DOMAINS = ("fanfiction.net", "archiveofourown.org", "patreon.com")
FIC_PROMO_ROLE_IDS = env_ints("FIC_PROMO_ROLE_IDS")
BIWEEKLY_AUTHORIZED_USERS = set(env_ints("BIWEEKLY_AUTHORIZED_USER_IDS", [OWNER_USER_ID] if OWNER_USER_ID else []))
BIWEEKLY_ALLOWED_CHANNELS = set(env_ints("BIWEEKLY_ALLOWED_CHANNEL_IDS"))
BIWEEKLY_ALLOWED_ROLE_IDS = set(env_ints("BIWEEKLY_ALLOWED_ROLE_IDS"))
INDEX_ALLOWED_CHANNELS = set(env_ints(
    "INDEX_ALLOWED_CHANNEL_IDS",
    [channel_id for channel_id in (OPERATIONS_CHANNEL_ID, BOTS_AND_UPDATES_CHANNEL_ID) if channel_id],
))
FOLLOWS_ALLOWED_CHANNELS = set(env_ints(
    "FOLLOWS_ALLOWED_CHANNEL_IDS",
    [channel_id for channel_id in (OPERATIONS_CHANNEL_ID, JUNKYARD_CHANNEL_ID, BOTS_AND_UPDATES_CHANNEL_ID) if channel_id],
))
REMOVE_ALLOWED_CHANNELS = set(env_ints(
    "REMOVE_ALLOWED_CHANNEL_IDS",
    [channel_id for channel_id in (OPERATIONS_CHANNEL_ID, BOTS_AND_UPDATES_CHANNEL_ID) if channel_id],
))
RANKUPDATE_ALLOWED_CHANNELS = set(env_ints(
    "RANKUPDATE_ALLOWED_CHANNEL_IDS",
    [OPERATIONS_CHANNEL_ID] if OPERATIONS_CHANNEL_ID else [],
))
AUTOINDEX_AUTHORIZED_USERS = set(env_ints("AUTOINDEX_AUTHORIZED_USER_IDS", [OWNER_USER_ID] if OWNER_USER_ID else []))
LEGACYPARKE_AUTHORIZED_USERS = set(env_ints("LEGACYPARKE_AUTHORIZED_USER_IDS", [OWNER_USER_ID] if OWNER_USER_ID else []))
AUTHOR_WEBHOOK_IDS = set(env_ints("AUTHOR_WEBHOOK_IDS"))
REACT_X_WEBHOOK_IDS = set(env_ints("REACT_X_WEBHOOK_IDS"))
EDITOR_WEBHOOK_IDS = set(env_ints("EDITOR_WEBHOOK_IDS"))
APPLICANT_WEBHOOK_IDS = set(env_ints("APPLICANT_WEBHOOK_IDS"))
PLAYTESTER_WEBHOOK_IDS = set(env_ints("PLAYTESTER_WEBHOOK_IDS"))
ERROR_REPORTER_WEBHOOK_IDS = set(env_ints("ERROR_REPORTER_WEBHOOK_IDS"))
SUGGESTER_WEBHOOK_IDS = set(env_ints("SUGGESTER_WEBHOOK_IDS"))
BIWEEKLY_RUNNING_MESSAGE = "Running biweekly. Estimated runtime is over 2 hours."


def authorlist_key():
    return (
        os.getenv(AUTHORLIST_KEY_ENV)
        or os.getenv(BIWEEKLY_AUTHORLIST_KEY_ENV)
        or require_env(AUTHORLIST_KEY_ENV)
    )


def configured_guilds(*guild_ids):
    guilds = [discord.Object(id=guild_id) for guild_id in guild_ids if guild_id]
    if guilds:
        return app_commands.guilds(*guilds)

    def decorator(func):
        return func

    return decorator


def guild_command_kwargs(guild_id):
    return {"guild": discord.Object(id=guild_id)} if guild_id else {}


def configured_channel(channel_id):
    return bot.get_channel(channel_id) if channel_id else None


def owner_user():
    return bot.get_user(OWNER_USER_ID) if OWNER_USER_ID else None


beats = owner_user()

async def sigterm_handler(_signo, _stack_frame):
    sys.exit(0)


def scrape_price_job():
    from hypixel import scrape_price

    scrape_price()


async def legacyparke_job(bot_instance):
    from legacyparke_watcher import check_legacyparke_once

    return await check_legacyparke_once(bot_instance)


async def execute_biweekly_update():
    import elupdate
    import ffwebscrape

    start_time = time.monotonic()
    try:
        result = await asyncio.to_thread(elupdate.run_biweekly)
    except ffwebscrape.Ao3BotRestrictedError:
        return (
            "AO3 is restricting bot traffic right now, so biweekly stopped before checking "
            "the remaining AO3 URLs. Please try again in a few hours or days."
        )
    runtime = time.monotonic() - start_time
    mins = int(runtime // 60)
    secs = int(runtime % 60)
    return f"Biweekly has finished in {mins} minutes and {secs} seconds.\n{elupdate.format_biweekly_summary(result)}"


def has_any_role(member, role_ids):
    return any(getattr(role, "id", None) in role_ids for role in getattr(member, "roles", []))


def can_run_biweekly(member, channel_id):
    if member.id in BIWEEKLY_AUTHORIZED_USERS:
        return True
    if channel_id in BIWEEKLY_ALLOWED_CHANNELS:
        return True
    return has_any_role(member, BIWEEKLY_ALLOWED_ROLE_IDS)


def should_repost_fic_promo_message(message):
    if message.author.id != FIC_PROMO_SOURCE_AUTHOR_ID:
        return False
    if message.channel.id != FIC_PROMO_SOURCE_CHANNEL_ID:
        return False

    content = message.content.lower()
    return all(domain in content for domain in FIC_PROMO_REQUIRED_DOMAINS)


def fic_promo_allowed_mentions():
    return discord.AllowedMentions(
        everyone=False,
        users=False,
        roles=[discord.Object(id=role_id) for role_id in FIC_PROMO_ROLE_IDS],
        replied_user=False,
    )


async def repost_fic_promo_message(message):
    target_channel = bot.get_channel(FIC_PROMO_TARGET_CHANNEL_ID)
    if target_channel is None:
        target_channel = await bot.fetch_channel(FIC_PROMO_TARGET_CHANNEL_ID)

    role_mentions = " ".join(f"<@&{role_id}>" for role_id in FIC_PROMO_ROLE_IDS)
    repost_content = f"{role_mentions}\n{message.content}"
    allowed_mentions = fic_promo_allowed_mentions()

    if len(repost_content) <= 2000:
        await target_channel.send(repost_content, allowed_mentions=allowed_mentions)
        return

    first_chunk_size = 2000 - len(role_mentions) - 1
    await target_channel.send(
        f"{role_mentions}\n{message.content[:first_chunk_size]}",
        allowed_mentions=allowed_mentions,
    )

    for start in range(first_chunk_size, len(message.content), 2000):
        await target_channel.send(
            message.content[start:start + 2000],
            allowed_mentions=discord.AllowedMentions.none(),
        )


def sheet(dockey,sheet):
    gc = google_client()
    target = gc.open_by_key(dockey).worksheet_by_title(sheet)
    cells = target.get_all_values(include_tailing_empty_rows=False, include_tailing_empty=False, returnas='matrix')
    return cells,target

@bot.event
async def on_ready():
    print('We have logged in as {0.user}'.format(bot))
    sync_guild_ids = [guild_id for guild_id in (EL_GUILD_ID, TESTING_GUILD_ID) if guild_id]
    if sync_guild_ids:
        for guild_id in sync_guild_ids:
            await bot.tree.sync(guild=discord.Object(id=guild_id))
    else:
        await bot.tree.sync()
    if not scheduler.running:
        scheduler.add_job(runsenact,trigger='cron',hour=12,misfire_grace_time=1000)
        # scheduler.add_job(weeklysenact,trigger='cron',day_of_week='mon',hour=12,misfire_grace_time=1000)
        scheduler.add_job(scrape_price_job,trigger='cron',hour=21,misfire_grace_time=1000)
        legacyparke_minutes = int(os.getenv('LEGACYPARKE_INTERVAL_MINUTES', '15'))
        scheduler.add_job(
            legacyparke_job,
            trigger='interval',
            minutes=legacyparke_minutes,
            args=[bot],
            id='legacyparke_rent_watch',
            replace_existing=True,
            misfire_grace_time=1000,
        )
        scheduler.start()

@bot.tree.command(
        name="index",
        description="Updates the index of authors in the server. Only works in the operations or bots channel.",
        **guild_command_kwargs(EL_GUILD_ID)

)
async def index(interaction: Interaction):
    import indexupdate

    try:
        msg_to_send = None
        if interaction.channel_id in INDEX_ALLOWED_CHANNELS:
            cells,_ = sheet(authorlist_key(), 'Author Follows Sorted')
        else:
            await interaction.response.send_message('Please run this command in the operations or bots channels.',
                                                    ephemeral=True)
            return
        msg_to_send = await indexupdate.run(interaction,bot,cells)

        if msg_to_send:
            interaction.response.send_message(msg_to_send[0],ephemeral=False)
            for msg in msg_to_send[1:]:
                await interaction.channel.send(msg,ephemeral=False)
        else:
            await interaction.response.send_message("No updates were made to the index.",ephemeral=False)
    except:
        print(traceback.format_exc())
        await interaction.response.send_message("Something went wrong while checking the index. Beats has been notified and will be inbound with excuses shortly.",ephemeral=False)
        beats = owner_user()
        #send the traceback
        if beats is not None:
            await beats.send(f"Something went wrong while checking the index. {traceback.format_exc()}")

@bot.tree.command(
        name="activity",
        description="Runs the activity command. Only works in the operations channel or EL council leadership channels.",
        **guild_command_kwargs(EL_GUILD_ID)
)
async def activity(interaction: Interaction):
    import activity as actfile

    if interaction.guild_id == EL_GUILD_ID:
        EL = bot.get_guild(EL_GUILD_ID)
        council_administrator = EL.get_role(COUNCIL_ADMIN_ROLE_ID) if COUNCIL_ADMIN_ROLE_ID else None
        management = EL.get_role(MANAGEMENT_ROLE_ID) if MANAGEMENT_ROLE_ID else None
        chairman = EL.get_role(CHAIRMAN_ROLE_ID) if CHAIRMAN_ROLE_ID else None
        if management in interaction.user.roles or council_administrator in interaction.user.roles or chairman in interaction.user.roles:
            await actfile.run_activity(interaction)
        else:
            await interaction.response.send_message("You cannot use that command. Please contact a member of management or council leadership.",ephemeral=True)
    elif interaction.guild_id == TESTING_GUILD_ID:
        await actfile.run_activity(interaction)
    else:
        await interaction.response.send_message("You cannot use that command in this discord.",ephemeral=True)


@bot.tree.command(
        name="biweekly",
        description="Runs the Emerald Library author score biweekly update.",
)
@configured_guilds(EL_GUILD_ID, TESTING_GUILD_ID)
async def biweekly_slash(interaction: Interaction):
    if not can_run_biweekly(interaction.user, interaction.channel_id):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    await interaction.response.send_message(BIWEEKLY_RUNNING_MESSAGE, ephemeral=False)
    try:
        message = await execute_biweekly_update()
        await interaction.channel.send(message)
    except Exception:
        print(f"handled in biweekly: {traceback.format_exc()}")
        await interaction.channel.send("Biweekly broke. Beats has been notified.")
        beats_user = owner_user()
        if beats_user is not None:
            await beats_user.send(f"Something has gone horribly wrong with the biweekly. Here is the traceback:\n{traceback.format_exc()}")


@bot.tree.command(
        name="followshelp",
        description="Provides help for the follows command.",
        **guild_command_kwargs(EL_GUILD_ID)
)
async def followshelp(interaction: Interaction):
    if interaction.guild_id == EL_GUILD_ID:
        await interaction.response.send_message("The follows command accepts fanfiction.net, tapas.io, and archiveofourown author profile links. Please ensure your link is not to a story."
                "\n\n"
                "``` \nTo submit a fanfiction.net link, please follow the format of:\n\n/follows https://www.fanfiction.net/~curiousbeats \n\n\n "
                "To submit a tapas.io link, please follow the format of: \n\n/follows https://tapas.io/beauvandalen\n\n\n"
                "To submit an AO3 link, please follow the format of: \n\n/follows https://archiveofourown.org/users/Curious_Beats\n\n\n"
                "If you still can't get the bot to work, please head over to the help desk, or ping a member of operations.",ephemeral=True)
    else:
        await interaction.response.send_message("You cannot use that command in this discord.",ephemeral=True)
@bot.tree.command(
        name="urlinfo",
        description="Provides information about a URL.",
        **guild_command_kwargs(TESTING_GUILD_ID)
)
@app_commands.describe(url="The URL to get information about.")
async def test_url_info(interaction: Interaction, url: str):
    import ffwebscrape

    if "fanfiction.net" in url:
        platform = 0
    elif "archiveofourown" in url:
        platform = 1

    try:
        info = await ffwebscrape.get_story_info(url, platform)
    except ffwebscrape.Ao3BotRestrictedError:
        await interaction.response.send_message(ffwebscrape.AO3_BOT_RESTRICTED_MESSAGE, ephemeral=True)
        return

    if info:
        embed = Embed(title="Story Information", color=0x00ff00)
        for key, value in info.items():
            embed.add_field(name=key, value=value, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message("Could not retrieve information for the provided URL.", ephemeral=True)
        
@bot.tree.command(
        name="follows",
        description="Counts the number of followers an author has on fanfiction.net, tapas.io, or archiveofourown.org.",
        **guild_command_kwargs(EL_GUILD_ID)
)
@app_commands.describe(url="The author's profile link.")
async def follows(interaction: Interaction,url: str):
    import ffwebscrape

    if interaction.guild_id == EL_GUILD_ID:
        if "fanfiction.net/" in url:
            if 'm.' in url:
                url = re.sub('m.', 'www.', url)
            if '/s/' in url:
                await interaction.response.send_message("You've submitted a story link. Please submit an author's profile link instead.",
                        ephemeral=True)
                return False
            platform = 0
        elif "archiveofourown.org/" in url:
            platform = 1
            if '/users/' not in url:
                await interaction.response.send_message("Please submit an author's profile in the format /follows [URL].",ephemeral=True)
        elif 'tapas.io' in url:
            platform = 2
        else:
            await interaction.response.send_message("Please submit an author's profile in the format /follows [URL]."
                    " This bot supports ff.net, tapas.io and ao3 links. For help with this command, please use /followshelp.",
                    ephemeral=True)
            return False

        if interaction.channel_id in FOLLOWS_ALLOWED_CHANNELS:
            #this can take more than 3 seconds, so defer
            await interaction.response.defer(thinking=True,ephemeral=False)
            try:
                follownum = await ffwebscrape.followcount(url,platform)
            except ffwebscrape.Ao3BotRestrictedError:
                await interaction.followup.send(ffwebscrape.AO3_BOT_RESTRICTED_MESSAGE,ephemeral=True)
                return
            if follownum == False:
                await interaction.followup.send("There seems to be an error. It's likely that either this profile has no followers, or you submitted an invalid link. For help with this command, please use /followshelp.",ephemeral=True)
            elif follownum == 3:
                await interaction.followup.send("The request timed out multiple times while trying to access the profile via multiple services. This is very likely a problem with fanfiction.net, please try again later.",ephemeral=True)
            else:
                await interaction.followup.send(f"This profile's profile score is {follownum}",ephemeral=False)
        else:
            await interaction.response.send_message("You can\'t use that command in this channel. Please head over to the junkyard to count followers.",ephemeral=True)
    else:
        await interaction.response.send_message("You cannot use that command in this discord.",ephemeral=True)

@bot.event
async def on_raw_reaction_add(payload):
    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    try:
        if BOT_USER_ID is not None and message.author.id == BOT_USER_ID:
            #operations and el in private disc
            if channel.id in CONFIRMATION_CHANNEL_IDS:
                if "Is this your" in message.content:
                    await message.reply(f"User confirmed, thank you {payload.member.display_name}!")
    except AttributeError:
        #send the error to beats
        beats = owner_user()
        if beats is not None:
            await beats.send(f"Error in reaction add:\n{traceback.format_exc()}")
        print("Handled in merits:", traceback.format_exc())

async def runsenact():
    cells,_ = sheet(SENATE_ROSTER_KEY or require_env("SENATE_ROSTER_KEY"),SENATE_ROSTER_SHEET)
    sendict = {}
    cells = [x for x in cells if len(x) >= 18]
    for i in range(2,15):
        try:
            if cells[i][17] == 'Not Completed':
                hours = float(cells[i][13])
                required_hours = 6
                if hours >= 0:
                    hours = round(hours,2)
                    if int(repr(hours)[-1]) == 0:
                        hours = int(hours)
                    remain = round(required_hours-hours,2)
                    if int(repr(remain)[-1]) == 0:
                        remain = int(remain)
                    hours = f"{hours}/{required_hours}"
                    msgstr = f"You have {hours} hours logged on your senator this week! You need to log {remain} more hour(s) before the end of the week."
                elif hours < 0:
                    msgstr = "You have not clocked out for every time you've clocked into the Senate activity log. Please make sure to clock out."
                senatortag = str(cells[i][8])
                senguild = bot.get_guild(SENATE_GUILD_ID) if SENATE_GUILD_ID else None
                senator = senguild.get_member_named(senatortag) if senguild else None
                if senator is not None:
                    sendict[senator] = msgstr
        except IndexError:
            pass
    for senator in sendict:
        await senator.send(sendict[senator])

@bot.tree.command(
        name="remove",
        description="Removes a member from the authorlist. Only works in the operations channels.",
        **guild_command_kwargs(EL_GUILD_ID)
)
@app_commands.describe(arg="The member to remove from the authorlist.")
async def remove(interaction : Interaction, arg : User):
    import auto_register

    guild_id = interaction.guild_id
    # try:
    #     if isinstance(member, str) == False:
    #         arg = await bot.fetch_user(member.id)
    #     else:
    #         arg = member
    # except:
    #     await interaction.response.send_message("There is an error with the DiscordID. Please try again.")
    #     return

    removedMessage = '{remove} has been removed from the roster.'
    #EL
    if guild_id == EL_GUILD_ID:
        if interaction.channel.id in REMOVE_ALLOWED_CHANNELS:
            try:
                removed = auto_register.remove(arg)
                if removed:
                    await interaction.response.send_message(removedMessage.format(remove=arg),ephemeral=False)
                else:
                    await interaction.response.send_message(f'{arg} was not found on the authorlist.',ephemeral=False)
            except:
                print(traceback.format_exc())
                beats = owner_user()
                if beats is not None:
                    await beats.send(f"There was an error using the remove command in EL. Error Message: \n\n{traceback.format_exc()}")
                await interaction.response.send_message("There was an error using the remove command. Beats has been notified and will complain imminently.",ephemeral=False)
        else:
            await interaction.response.send_message('Sorry, but you can\'t do that in this channel. Please head to a configured operations channel.', ephemeral=True)

@bot.command(name = "rankupdate", help = "Updates the ranks of all members in the server. Only works in the operations channel.")
async def rankupdate(ctx):
    import rankupdater

    if ctx.channel.id in RANKUPDATE_ALLOWED_CHANNELS:
        cells,_ = sheet(authorlist_key(),'Author Follows Sorted')
        await ctx.send("Rank update machine is starting. This may take a few minutes.")
        try:
            await rankupdater.start(ctx,bot,cells)
        except:
            print("handled in rankupdate: \n\n", traceback.format_exc())
            await ctx.send("Rank update machine broke. Beats has been notified and will complain imminently.")
            beats = owner_user()
            if beats is not None:
                await beats.send(f"There was an error using the rankupdate command in EL. Error Message: \n\n{traceback.format_exc()}")

@bot.event
async def on_member_remove(member):
    authorranklist = ['Author','Bronze Author {0+}','Gold Author {1500+}','Topaz Author {2500+}','Ruby Author {6500+}','Onyx Author {500+}','Copper Author {200+}','Silver Author {800+}','Diamond Author {10000+}','Garnet Author {4000+}','Peridot Author {20000+}','Emerald Author {35000+}','Sapphire Author {15000+}']
    username = str(member)
    #in order enlisted, nco, warrant officer, officer, senior officer
    for i in member.roles:
        #EL
        if i.name in authorranklist:
            import auto_register

            leaver_channel = configured_channel(OPERATIONS_CHANNEL_ID)

            removed = auto_register.remove(username)
            break
        #MD
        elif MD_ROLE_ID is not None and i.id == MD_ROLE_ID:
            leaver_channel = configured_channel(MD_CHANNEL_ID)
            break
    try:
        if 'leaver_channel' in locals():
            if leaver_channel and leaver_channel.id == OPERATIONS_CHANNEL_ID:
                if removed:
                    await leaver_channel.send(f'{username} left the server and has been removed from the authorlist.')
                else:
                    await leaver_channel.send(f'{username} left the server but was not found in the authorlist.')

            elif member.nick is None:
                await leaver_channel.send(f'{username} has left the server')
            else:
                await leaver_channel.send(f'{username} ({member.nick}) has left the server')

    except UnboundLocalError:
        pass

@bot.event
async def on_user_update(before,after):
    try:
        if str(before) != str(after):
            shared_servers = before.mutual_guilds
            # authorranklist = ["Emerald Author {35000+}", "Prestige Author {15000+}", "Diamond Author {8000+}",
            #                 "Ruby Author {3000+}", "Gold Author {1500+}", "Silver Author {800+}", "Onyx Author {200+}",
            #                 "Bronze Author {0+}", "Author"]
            authorranklist = ['Author','Bronze Author {0+}','Gold Author {1500+}','Topaz Author {2500+}','Ruby Author {6500+}','Onyx Author {500+}','Copper Author {200+}','Silver Author {800+}','Diamond Author {10000+}','Garnet Author {4000+}','Peridot Author {20000+}','Emerald Author {35000+}','Sapphire Author {15000+}']
            target_channels = []
            keylist = []
            tablist = []
            # so we can check md_channel later without grabbing it twice
            md_channel = configured_channel(MD_CHANNEL_ID)
            for j in shared_servers:
                target_member = discord.utils.get(j.members, id=before.id)
                if target_member is None:
                    continue
                for i in target_member.roles:
                    if i.name in authorranklist:
                        #operations
                        target_channels.append(configured_channel(AUTHOR_NAME_CHANGE_CHANNEL_ID))
                        keylist.append(authorlist_key())
                        tablist.append('Authorlist')
                    #MD
                    elif MD_ROLE_ID is not None and i.id == MD_ROLE_ID:
                        target_channels.append(md_channel)

            if len(target_channels) >0:
                before_tag = before.name
                after_tag = after.name
                if md_channel is not None and md_channel in target_channels:
                    await md_channel.send(f"{before_tag} has changed their profile to {after_tag}.")
                else:
                    for i in range(len(target_channels)):
                        key = keylist[i]
                        tab = tablist[i]
                        target_channel = target_channels[i]
                        if target_channel is None:
                            continue
                        cells,target = sheet(key,tab)
                        target.replace(before_tag,after_tag,matchEntireCell=True)
                        await target_channel.send(f"{before_tag} has changed their profile to {after_tag}. Their tag has been updated on your roster.")

    except:
        beats_user = owner_user()
        if beats_user is not None:
            await beats_user.send(f"on user update has broken\n {traceback.format_exc()}")

@bot.event
async def on_message(message):
    try:
        if should_repost_fic_promo_message(message):
            await repost_fic_promo_message(message)
    except Exception:
        print(f"handled in fic promo repost: {traceback.format_exc()}")
        beats = owner_user()
        if beats is not None:
            await beats.send(f"Something has gone wrong with the fic promo repost:\n{traceback.format_exc()}")

    try:
        if message.webhook_id is not None:
            if message.webhook_id in AUTHOR_WEBHOOK_IDS:
                from registry_ping import check_for_member

                try:
                    await check_for_member(message,"author")
                except:
                    print(traceback.format_exc())
                    owner_mention = f"<@{OWNER_USER_ID}>" if OWNER_USER_ID else "the bot owner"
                    await message.channel.send(f"Something has gone horribly wrong 0-0 {owner_mention} please help")
                    beats = owner_user()
                    if beats is not None:
                        await beats.send(f"Something has gone horribly wrong with the author webhook. Here is the traceback:\n{traceback.format_exc()}")

            elif message.webhook_id in REACT_X_WEBHOOK_IDS:
                await message.add_reaction("❌")
            elif message.webhook_id in EDITOR_WEBHOOK_IDS:
                from registry_ping import check_for_member

                await check_for_member(message,"editor")
            elif message.webhook_id in APPLICANT_WEBHOOK_IDS:
                from registry_ping import check_for_member

                await check_for_member(message,"applicant")
            elif message.webhook_id in PLAYTESTER_WEBHOOK_IDS:
                from registry_ping import check_for_member

                await check_for_member(message,"playtester")
            elif message.webhook_id in ERROR_REPORTER_WEBHOOK_IDS:
                from registry_ping import check_for_member

                await check_for_member(message,"error reporter")
            elif message.webhook_id in SUGGESTER_WEBHOOK_IDS:
                from registry_ping import check_for_member

                await check_for_member(message,"suggester")
    except AttributeError:
        pass
    await bot.process_commands(message)

@bot.command(name="autoindex", help="Runs the autoindex")
async def autoindex(ctx):
    from auto_index import run_index

    if ctx.author.id in AUTOINDEX_AUTHORIZED_USERS:
        try:
            index_channel = configured_channel(AUTHOR_INDEX_CHANNEL_ID)
            if index_channel is None:
                await ctx.reply("The author index channel is not configured.")
                return
            await index_channel.purge(limit=500)
            index_embed = run_index()
            for i in index_embed:
                await index_channel.send(embed=i)
            await ctx.reply("Autoindex has finished.")
        except:
            print(f"handled in autoindex: {traceback.format_exc()}")
            await ctx.reply("There's an error with the autoindex. Beats has been notified.")
            beats = owner_user()
            if beats is not None:
                await beats.send(f"Something has gone horribly wrong with the autoindex. Here is the traceback:\n{traceback.format_exc()}")
    else:
        await ctx.send("You do not have permission to use this command.")


@bot.command(name="biweekly", help="Runs the Emerald Library author score biweekly update.")
async def biweekly_prefix(ctx):
    if not can_run_biweekly(ctx.author, ctx.channel.id):
        await ctx.send("You do not have permission to use this command.")
        return

    await ctx.send(BIWEEKLY_RUNNING_MESSAGE)
    try:
        await ctx.send(await execute_biweekly_update())
    except Exception:
        print(f"handled in biweekly: {traceback.format_exc()}")
        await ctx.send("Biweekly broke. Beats has been notified.")
        beats_user = owner_user()
        if beats_user is not None:
            await beats_user.send(f"Something has gone horribly wrong with the biweekly. Here is the traceback:\n{traceback.format_exc()}")


@bot.command(name="legacyparke", help="Runs the Legacy Parke rent watcher once.")
async def legacyparke(ctx):
    from legacyparke_watcher import check_legacyparke_once

    if ctx.author.id not in LEGACYPARKE_AUTHORIZED_USERS:
        await ctx.send("You do not have permission to use this command.")
        return
    await ctx.send("Checking Legacy Parke rents.")
    try:
        message = await check_legacyparke_once(bot, post_unchanged=True)
        legacyparke_channel_id = env_int('LEGACYPARKE_CHANNEL_ID')
        if legacyparke_channel_id is None or ctx.channel.id != legacyparke_channel_id:
            await ctx.send(message)
    except:
        print(f"handled in legacyparke: {traceback.format_exc()}")
        await ctx.send("Legacy Parke rent check failed. Beats has been notified.")
        beats = owner_user()
        if beats is not None:
            await beats.send(f"Legacy Parke rent check failed:\n{traceback.format_exc()}")

load_dotenv()
TOKEN = os.getenv('CURIOUSBOT_TOKEN')
bot.run(TOKEN)
