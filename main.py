import discord
import os
import logging
import sqlite3
from siegeapi import Auth
from siegeapi.constants import seasons
from siegeapi.summaries import Summary
import datetime
from discord.ext import commands

auth:Auth ##R6身份 要使用這個取得任何遊戲資料

##需要允許message_content意圖,不然機器人收不到訊息
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='d.',intents=intents,help_command=None)

##機器人啟動完成
@bot.event
async def on_ready():
    global auth
    auth = Auth(os.getenv("R6_ACCOUNT",None), os.getenv("R6_PASSWORD",None))
    await bot.change_presence(activity=discord.Game("d.help"))
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')
    
##幹員資訊
@bot.command()
async def operator(ctx,user,operatorName):
    try:
        # 讀取角色資料與幹員資料
        player = await auth.get_player(name=user)
        await player.load_operators(True)
        
        # 尋找使用者所輸入的幹員資料
        operatorData = findOperators(player.operators,operatorName)
        
        if(operatorData):
            if(operatorData.rounds_won == 0 and operatorData.rounds_lost == 0):
                await ctx.send("此角色無資料可顯示")
            else:
                embed = discord.Embed(title=operatorData.name+"最近表現",colour=discord.Colour.teal())
                embed.set_author(name=player.name, icon_url=player.profile_pic_url)
                embed.set_thumbnail(url=operatorData.icon_url)
                embed.add_field(name="**勝負**", value=f"{operatorData.rounds_won}/{operatorData.rounds_lost}({round(operatorData.win_loss_ratio/100,2)})")
                embed.add_field(name="**戰損**", value=f"{operatorData.kills}/{operatorData.death}({round(operatorData.kill_death_ratio/100,2)})")
                
                await ctx.send(embed=embed)
        else:
            raise Exception(f"找不到{operatorName}幹員資料")
            
    except Exception as error:
        logging.exception(error)
        if(str(error) == "No results"):
            await ctx.send(f"找不到{user}資料")
        else:
            await ctx.send(error)
        
##幹員比較
@bot.command()
async def vsoperator(ctx,user1,user2,operatorName):
    try:
        playerDict = await auth.get_player_batch(names = [user1,user2])

        playerName = [] # 儲存實際遊戲名子當後面字典物件的key
        playerID = [] # 儲存id 因作者誤把使用name查找的playerDict字典key設定成id 所以這邊要先存起來給後面用
        operatorDict = {}
        for key,player in  playerDict.items():
            await player.load_operators(True)
            operatorDict[player.name] = findOperators(player.operators,operatorName)

            if(operatorDict[player.name] is None):
                raise Exception(f"找不到{operatorName}幹員資料")

            playerName.append(player.name)
            playerID.append(key)

        if(operatorDict[playerName[0]].rounds_won == 0 and operatorDict[playerName[0]].rounds_lost == 0):
            raise Exception(f"用戶1{operatorDict[playerName[0]].name}無資料無法比較")

        if(operatorDict[playerName[1]].rounds_won == 0 and operatorDict[playerName[1]].rounds_lost == 0):
            raise Exception("用戶2{operatorData2.name}無資料無法比較")

        embed = discord.Embed(title=f"{playerDict[playerID[0]].name} vs {playerDict[playerID[1]].name}",description=f"{operatorDict[playerName[0]].name}比較",colour=discord.Colour.green())
        embed.set_thumbnail(url=operatorDict[playerName[0]].icon_url)
        embed.add_field(name="**勝負**", 
            value=f"**{playerDict[playerID[0]].name}**: {operatorDict[playerName[0]].rounds_won}/{operatorDict[playerName[0]].rounds_lost} ({operatorDict[playerName[0]].win_loss_ratio})\r\n"
                f"**{playerDict[playerID[1]].name}**: {operatorDict[playerName[1]].rounds_won}/{operatorDict[playerName[1]].rounds_lost} ({operatorDict[playerName[1]].win_loss_ratio})")
        embed.add_field(name="**戰損**", 
            value=f"**{playerDict[playerID[0]].name}**: {operatorDict[playerName[0]].kills}/{operatorDict[playerName[0]].death} ({operatorDict[playerName[0]].kill_death_ratio})\r\n"
                f"**{playerDict[playerID[1]].name}**: {operatorDict[playerName[1]].kills}/{operatorDict[playerName[1]].death} ({operatorDict[playerName[1]].kill_death_ratio})")
        
        await ctx.send(embed=embed)
    except Exception as error:
        logging.exception(error)
        await ctx.send(repr(error))
        
##玩家資訊
@bot.command()
async def player(ctx,user):
    try:
        player = await auth.get_player(name=user)
        await player.load_playtime()
        summary = await getPlayerSummary(player)

        summaryKd = round(summary.kills/summary.death,2)
        rankKd = round(player.ranked_profile.kills/player.ranked_profile.deaths,2)
        summaryWinRatio = round(summary.matches_won/summary.matches_lost,2)
        rankWinRatio = round(player.ranked_profile.wins/player.ranked_profile.losses,2)
        time = datetime.timedelta(minutes=summary.minutes_played)
        
        embed = discord.Embed(colour=discord.Colour.blue(),description=f"遊玩時數：{time}")
        embed.set_author(name=f"<{player.level}>{player.name}", icon_url=player.profile_pic_url)
        embed.add_field(name="**概覽**",value=f"勝負:{summary.matches_won}/{summary.matches_lost}({summaryWinRatio})\r\n"
            f"戰損:{summary.kills}/{summary.death}({summaryKd})")
        embed.add_field(name=f"**排位 {player.ranked_profile.season_code} {player.ranked_profile.rank} {player.ranked_profile.rank_points}**",
            value=f"勝負:{player.ranked_profile.wins}/{player.ranked_profile.losses}({rankWinRatio})\r\n"
                f"戰損:{player.ranked_profile.kills}/{player.ranked_profile.deaths}({rankKd})")
        
        await ctx.send(embed=embed)
    except Exception as error:
        logging.exception(error)
        await ctx.send(error)


##結算歷史戰績
@bot.command()
async def count(ctx,user):
    con = sqlite3.connect("r6.db")
    cur = con.cursor()
    try:
        """
        先query資料庫這個使用者的最新資料->撈r6使用者資料->兩個互減->(勝負等於零)?不寫入資料庫:insert回資料庫->判斷個人資料超過10筆刪除舊資料
        """
        player = await auth.get_player(name=user)
        summary = await getPlayerSummary(player)

        originData = cur.execute("SELECT WINS,LOSSES,KILLS,DEATHS FROM USER_INFO WHERE USER_ID=? AND TIME = (SELECT TIME FROM USER_INFO WHERE USER_ID=? ORDER BY TIME DESC LIMIT 1)",(player.id,player.id,)).fetchone()

        print(originData)
        if(originData is None):
            winsDiff = summary.matches_won
            lossesDiff = summary.matches_lost
            killsDiff = summary.kills
            deathsDiff = summary.death
        else:
            winsDiff = summary.matches_won - originData[0]
            lossesDiff = summary.matches_lost - originData[1]
            killsDiff = summary.kills - originData[2]
            deathsDiff = summary.death - originData[3]

        if(winsDiff != 0 or lossesDiff != 0):
            cur.execute("INSERT INTO USER_INFO VALUES(?,?,?,?,?,?,?,?,?,?,DATETIME())"
                ,(player.id,player.name,summary.matches_won,summary.matches_lost,summary.kills,summary.death,winsDiff,lossesDiff,killsDiff,deathsDiff))
            con.commit()
        
        contentData = cur.execute("SELECT TIME,WINS_DIFF,LOSSES_DIFF,KILLS_DIFF,DEATHS_DIFF FROM USER_INFO WHERE USER_ID=? ORDER BY TIME DESC",(player.id,)).fetchall()
        content = ""
        for row in contentData:
            content += f"**[{row[0]}]**\r\n勝負:{row[1]}/{row[2]}({round(row[1]/row[2],2)}) | 戰損:{row[3]}/{row[4]}({round(row[3]/row[4],2)})\r\n"

        if(len(contentData)>10):
            cur.execute("DELETE FROM USER_INFO WHERE USER_ID=? AND TIME = (SELECT MIN(TIME) FROM USER_INFO WHERE USER_ID=? GROUP BY TIME)",(player.id,player.id,))
            con.commit()

        embed = discord.Embed(colour=discord.Colour.orange())
        embed.set_author(name=player.name, icon_url=player.profile_pic_url)
        embed.add_field(name="**近日戰績**",value=content)
        await ctx.send(embed=embed)
    except Exception as error:
        logging.exception(error)
        await ctx.send(error)  
    finally:
        con.close()      
        
##自定義說明
@bot.command()
async def help(ctx):
    embed = discord.Embed(title="指令說明",description="[]為必要參數",colour=discord.Colour.gold())
    embed.add_field(name= "**d.operator [user] [operator]**",value= "查詢各幹員資訊",inline=False)
    embed.add_field(name= "**d.vsoperator [user1] [user2] [operator]**",value= "比較各幹員資訊",inline=False)
    embed.add_field(name= "**d.player [user]**",value="查詢玩家資訊",inline=False)
    embed.add_field(name= "**d.count [user]**",value="查詢玩家近況",inline=False)
    
    await ctx.send(embed=embed)

async def getPlayerSummary(player):
    seasonCodeList = [] #所有賽季代號
    for value in seasons.values():
        seasonCodeList.append(value["code"])
    
    await player.load_summaries(gamemodes=["all"],team_roles=["all"],seasons=seasonCodeList)
    await player.load_ranked_v2()

    # 所有賽季資料加總
    summary = None # 個人概要
    for season in player.all_summary.values():
        if(summary is None):
            summary = season["all"]
        else:
            for k,v in season["all"].__dict__.items():
                setattr(summary,k,getattr(summary,k)+v)
    return summary

def findOperators(operators,operatorName):
    operatorList = operators.all.attacker + operators.all.defender
    for operatorItem in operatorList:
        if(operatorItem.name.lower()==operatorName.lower()):
            return operatorItem

bot.run(os.getenv("DISCORD_KEY",None))
