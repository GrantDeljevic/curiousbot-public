from selenium import webdriver
from bs4 import BeautifulSoup
import pygsheets
import os
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from datetime import date
import re
import numpy as np

from bot_config import google_client, require_env

HYPIXEL_SHEET_KEY_ENV = "HYPIXEL_SHEET_KEY"


def sheet():
    gc = google_client()
    target = gc.open_by_key(require_env(HYPIXEL_SHEET_KEY_ENV)).worksheet_by_title("data")
    cells = target.get_all_values(include_tailing_empty_rows=False, include_tailing_empty=False, returnas='matrix')
    return cells, target, len(cells)

def getSoup():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")

    options.binary_location = os.environ.get("GOOGLE_CHROME_BIN")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=0,0")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extentions")
    options.add_argument("--proxy-server='direct://'")
    options.add_argument("start-maximized")
    options.add_argument("--proxy-bypass-list=*")
    options.add_argument("--disable-gpu")
    ChromeService = Service(os.environ.get("CHROMEDRIVER_PATH"))
    driver = webdriver.Chrome(service=ChromeService,options=options)
    try:
        driver.get("https://hyminions.herokuapp.com/minions?slots=maxed&fuel=30&sellingMethod=0&tax=1#content")
        return BeautifulSoup(driver.page_source, "lxml")
    finally:
        driver.quit()

def scrape_price():
    print("Scraping prices...")
    soup = getSoup()
    header = soup.select('tbody')
    rows = header[0].get_text().split('#')[1:]
    c = 0
    new_minions = []
    namelist = []
    profitlist = []
    cells,target,rownum = sheet()
    minions = cells[0]
    for row in rows:
        c += 1
        if c < 10:
            temp_row = row.split(')')[0][1:].split('(')
        else:
            temp_row = row.split(')')[0][2:].split('(')
        if temp_row[0] not in minions:
            new_minions.append(temp_row[0])
        namelist.append(temp_row[0])
        profitnum = int(re.sub('k','000',temp_row[1]).split('.')[0])
        profitlist.append(profitnum)
    profitlist = [x for _,x in sorted(zip(namelist,profitlist))]
    profitlist = [str(date.today().strftime("%m/%d/%y"))] + profitlist
    if len(new_minions) > 0:
        oldArr = np.array(cells)
        zeroes = np.zeros((rownum-1,len(new_minions)))

        newMinArr = np.vstack((new_minions,zeroes))
        newArr = np.hstack((oldArr,newMinArr))
        newArr = newArr[:, newArr[0, :].argsort()]
        target.update_values(crange = 'A1', values = newArr.tolist())

    target.append_table(profitlist)

def bazaar_alerts():
    prices = scrape_bazaar()
    #if the buy order for any non-rough gemstone or raw soulflow is less than half the sell order, alert
    #if any gemstone quality is significantly (say 1.2x) more than 80x the lower quality, alert
    #if raw soulflow buy order is significantly (say 0.8x) less than 160th the price of a soulflow sell order, alert
    #if the SELL order (insta-buy) for any gemstone is significantly less than an 80th the next highest quality's BUY order (insta-sell), priority alert(alert and ping)
    #if there is a profit to be made by buying and condensing any raw item, alert.

    #priority alert for all of the above if it passes a certain threshold, based on volume as well.

    
