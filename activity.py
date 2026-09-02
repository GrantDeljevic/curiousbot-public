import discord
import asyncio
import pandas as pd
import pygsheets
import numpy as np
from datetime import date
from io import BytesIO

from bot_config import google_client


async def read_channel_data(channel_data):
    payload = await channel_data.read()
    return pd.read_csv(
        BytesIO(payload),
        sep=',',
        usecols=['channel_name', 'readers', 'chatters', 'messages'],
    )


async def run_activity(interaction, channel_data):
    try:
        channels_csv = await read_channel_data(channel_data)
    except:
        await interaction.response.send_message("Please make sure you are attaching the channel list CSV."
        "(This is in testing. If you are having issues attaching a CSV to the command please reach out to Beats)",ephemeral=True)
        return False
    authorchannels = []
    for i in channels_csv['channel_name']:
        if '【' in str(i) and '🏛' not in str(i):
            authorchannels.append(i)
    authors_df = channels_csv.loc[channels_csv['channel_name'].isin(authorchannels)]
    scores = []
    for i in authors_df.iloc:
        try:
            score = 0.5 * np.log(int(i['readers']))
            score += np.log(int(i['chatters']))
            score += 0.5 * np.log(int(i['messages']))
            score += 0.5*np.log(int(i['messages'])/int(i['chatters']))
        except ZeroDivisionError:
            score += 0
        if score > 0:
            scores.append(score)
        else:
            scores.append(0)
    authors_df['score'] = scores

    chatter_avg = authors_df['chatters'].mean()
    message_avg = authors_df['messages'].mean()
    reader_avg = authors_df['readers'].mean()
    score_avg = authors_df['score'].mean()
    score_med = authors_df['score'].median()

    avg_list = [[chatter_avg],[message_avg],[reader_avg],[score_avg],[score_med]]
    label_list = [['Chatter Average:'],['Message Average:'],['Reader Average:'],['Aminta Score Average:'],['Aminta Score Median:']]
    sorted_authors = authors_df.sort_values(by='score',ascending=False)

    timestamp = date.today()
    timestamp = timestamp.strftime("%m/%d/%y")
    gc = google_client()
    res = gc.create(f"{timestamp} Dorm Activity")
    target = gc.open_by_key(res.id)
    target.share('',role='writer',type='anyone')
    wks = target.sheet1
    wks.set_dataframe(sorted_authors,(1,1))
    wks.update_values('G1:G5',label_list)
    wks.update_values('H1:H5',avg_list)

    url = target.url
    await interaction.response.send_message(url,ephemeral=False)
