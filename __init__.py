from json import load, dump, loads
from io import BytesIO
import json
import requests
import base64
import random
from nonebot import get_bot, on_command
from hoshino import priv, R
from hoshino.typing import NoticeSession, MessageSegment, CQHttpError
from .pcrclient import pcrclient, ApiException, bsdkclient
from asyncio import Lock, sleep
from os.path import dirname, join, exists
from copy import deepcopy
from traceback import format_exc
from .safeservice import SafeService
from hoshino.util import pic2b64
from random import randint
import re
import time
import os
from time import gmtime
from hoshino.modules.priconne import chara
from hoshino.modules.priconne._pcr_data import CHARA_NAME
from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageFilter, ImageOps, ImageEnhance
from hoshino import util
import datetime
import sqlite3
from .aiorequests import get
from .yobot import generate_name2qq, report_process
sv_help = '''
[游戏内会战推送] 无描述
'''.strip()
sv = SafeService('会战推送', help_=sv_help, bundle='pcr查询')
curpath = dirname(__file__)
##############################下面这个框填要推送的群
forward_group_list = []
yobot_dir = ''
##############################


current_folder = os.path.dirname(__file__)
img_file = os.path.join(current_folder, 'img')

cache = {}
client = None
lck = Lock()

captcha_lck = Lock()

with open(join(curpath, 'account.json')) as fp:
    acinfo = load(fp)
experimental = acinfo["experimental_options"]
if acinfo["push_group"] != []:
    forward_group_list = acinfo["push_group"]
bot = get_bot()
validate = None
validating = False
acfirst = False

#同步pcrjjc2自动过码
async def captchaVerifierV2(gt, challenge, userid):
    global validating

    validating = True
    captcha_cnt = 0
    while captcha_cnt < 5:
        captcha_cnt += 1
        #try:
        sv.logger.info(f'测试新版自动过码中，当前尝试第{captcha_cnt}次。')

        await sleep(1)

        url = f"https://pcrd.tencentbot.top/geetest_renew?captcha_type=1&challenge={challenge}&gt={gt}&userid={userid}&gs=1"
        header = {"Content-Type": "application/json", "User-Agent": "pcrjjc2/1.0.0"}
        # uuid = loads(await (await get(url="https://pcrd.tencentbot.top/geetest")).content)["uuid"]
        # print(f'uuid={uuid}')

        res = await (await aiorequests.get(url=url, headers=header)).content
        res = loads(res)
        uuid = res["uuid"]
        msg = [f"uuid={uuid}"]
        
        ccnt = 0
        while ccnt < 10:
            ccnt += 1
            res = await (await aiorequests.get(url=f"https://pcrd.tencentbot.top/check/{uuid}", headers=header)).content
            #if str(res.status_code) != "200":
            #    continue
            # print(res)
            res = loads(res)
            if "queue_num" in res:
                nu = res["queue_num"]
                msg.append(f"queue_num={nu}")
                tim = min(int(nu), 3) * 10
                msg.append(f"sleep={tim}")
                #await bot.send_private_msg(user_id=acinfo['admin'], message=f"thread{ordd}: \n" + "\n".join(msg))
                # print(f"pcrjjc2:\n" + "\n".join(msg))
                msg = []
                # print(f'farm: {uuid} in queue, sleep {tim} seconds')
                await sleep(tim)
            else:
                info = res["info"]
                if info in ["fail", "url invalid"]:
                    break
                elif info == "in running":
                    await sleep(5)
                elif 'validate' in info:
                    print(f'info={info}')
                    validating = False
                    return (info["challenge"], info["gt_user_id"], info["validate"])
            if ccnt >= 10:
                raise Exception("Captcha failed")

            # ccnt = 0
            # while ccnt < 3:
            #     ccnt += 1
            #     await sleep(5)
            #     res = await (await get(url=f"https://pcrd.tencentbot.top/check/{uuid}")).content
            #     res = loads(res)
            #     if "queue_num" in res:
            #         nu = res["queue_num"]
            #         print(f"queue_num={nu}")
            #         tim = min(int(nu), 3) * 5
            #         print(f"sleep={tim}")
            #         await sleep(tim)
            #     else:
            #         info = res["info"]
            #         if info in ["fail", "url invalid"]:
            #             break
            #         elif info == "in running":
            #             await sleep(5)
            #         else:
            #             print(f'info={info}')
            #             validating = False
            #             return info["challenge"], info["gt_user_id"], info["validate"]
        # except:
        #     pass

    # await sendToAdmin(
    #     f'自动过码多次尝试失败，可能为服务器错误，自动切换为手动。\n确实服务器无误后，可发送/pcrval重新触发自动过码。')
    validate = await captchaVerifier(gt, challenge, userid)
    validating = False
    return challenge, userid, validate

async def captchaVerifier(gt, challenge, userid):
    global acfirst, validating
    if not acfirst:
        await captcha_lck.acquire()
        acfirst = True
    
    if acinfo['admin'] == 0:
        bot.logger.error('captcha is required while admin qq is not set, so the login can\'t continue')
    else:
        # url = f"链接头：https://cc004.github.io/geetest/geetest.html\n链接：?captcha_type=1&challenge={challenge}&gt={gt}&userid={userid}&gs=1"
        url = f"https://cc004.github.io/geetest/geetest.html?captcha_type=1&challenge={challenge}&gt={gt}&userid={userid}&gs=1"
        if int(acinfo["captcha_group"]) != 0:
            await bot.send_group_msg(group_id = acinfo["captcha_group"],message = f'pcr账号登录需要验证码，请完成以下链接中的验证内容后将第一行validate=后面的内容复制，并用指令/pcrvalclan xxxx将内容发送给机器人完成验证\n为避免tx网页安全验证使验证码过期，请手动拼接链接头和链接：{url}\n※注意：请私聊BOT发送')
        else:
            await bot.send_private_msg(
                user_id = acinfo['admin'],
                message = f'pcr账号登录需要验证码，请完成以下链接中的验证内容后将第一行validate=后面的内容复制，并用指令/pcrvalclan xxxx将内容发送给机器人完成验证\n为避免tx网页安全验证使验证码过期，请手动拼接链接头和链接：{url}'
            )
    validating = True
    await captcha_lck.acquire()
    validating = False
    return validate

async def errlogger(msg):
    await bot.send_private_msg(
        user_id = acinfo['admin'],
        message = f'pcrjjc2登录错误：{msg}'
    )

clients = {}
for account_info in acinfo["account_list"]:
    account = account_info["account"]
    password = account_info["password"]
    bClient = bsdkclient(acinfo, captchaVerifierV2, errlogger, account, password)
    clients[account] = pcrclient(bClient)
define_account = acinfo["account_list"][0]["account"]
client:pcrclient = clients[define_account]

qlck = Lock()

async def verify():     #验证登录状态
    if validating:
        raise ApiException('账号被风控，请联系管理员输入验证码并重新登录', -1)
    async with qlck:
        while client.shouldLogin:
            await client.login()
            time.sleep(3)
    return

@on_command(f'/pcrvalclan')     #原手动验证
async def validate(session):
    global binds, lck, validate
    if session.ctx['user_id'] == acinfo['admin']:
        validate = session.ctx['message'].extract_plain_text().strip()[12:]
        captcha_lck.release()



#本人编程初学者，以下答辩代码警告
boss_icon_list = []
swa = 0 #初始化出刀开关
boss_status = [0,0,0,0,0]
in_game = [0,0,0,0,0]
in_game_old = [0,0,0,0,0]   #实战中
pre_push = [[],[],[],[],[]] #预约组
coin = 0    #会战币
arrow = 0   #出刀ID
tvid = 0    #玩家ID
sw = 0      #会战推送开关
fnum = 0    #实战人数
arrow_rec = 0   #出刀记录
renew_coin = True
side = {    
    1: 'A',
    4: 'B',
    11: 'C',
    31: 'D',
    41: 'E'    
}   #阶段数
phase = {
    1: 1,
    4: 2,
    11: 3,
    31: 4,
    41: 5   
}   #阶段周目
curr_side = '_'
max_chat_list = 20
health_list = [[6000000,8000000,10000000,12000000,15000000],[6000000,8000000,10000000,12000000,15000000],[12000000,14000000,17000000,19000000,22000000],[19000000,20000000,23000000,25000000,27000000],[85000000,90000000,95000000,100000000,110000000]]


@sv.scheduled_job('interval', seconds=60)
async def teafak():
    global coin,arrow_rec,side,curr_side,arrow,sw,pre_push,fnum,forward_group_list,boss_status,in_game,tvid,experimental,renew_coin
    try:
        load_index = 0
        if sw == 0:     #会战推送开关
            return
        if coin == 0 or renew_coin > 0:   #初始化获取硬币数/检测到boss状态发生变化后更新会战币
            item_list = {}
            await verify()
            load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})   #获取会战币api
            if tvid == 0:
                tvid =load_index['user_info']['viewer_id']
            for item in load_index["item_list"]:
                item_list[item["id"]] = item["stock"]
            coin = item_list[90006]
            
        msg = ''
        ref = 0
        res = 0
        
        while(ref == 0):
            try:
                await verify()
                clan_info = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 0})
                clan_id = clan_info['clan']['detail']['clan_id']
                res = await client.callapi('/clan_battle/top', {'clan_id': clan_id, 'is_first': 1, 'current_clan_battle_coin': coin})
                ref = 1
                if renew_coin > 0:
                    renew_coin -= 1
            except Exception as e:
                if ('连接中断' or '发生了错误(E)') in str(e):
                    for forward_group in forward_group_list:
                        await bot.send_group_msg(group_id = forward_group,message = '连接中断，可能顶号，已自动关闭推送，请重新开启会战推送')
                    sw = 0
                    return
                await verify()
                load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})   #击败BOSS时会战币会变动
                item_list = {}
                for item in load_index["item_list"]:
                    item_list[item["id"]] = item["stock"]
                coin = item_list[90006]
                pass


    #判定是否处于会战期间
        if load_index != 0:
            is_interval = load_index['clan_battle']['is_interval']
            if is_interval == 1:
                mode_change_open = load_index['clan_battle']['mode_change_limit_start_time']
                mode_change_open = time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(mode_change_open))
                mode_change_limit = load_index['clan_battle']['mode_change_limit_time']
                mode_change_limit = time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(mode_change_limit))
                msg = f'当前会战未开放，请在会战前一天初始化会战推送\n会战模式可切换时间{mode_change_open}-{mode_change_limit}'
                sw = 0
                for forward_group in forward_group_list:
                    await bot.send_group_msg(group_id = forward_group,message = msg)
                return


    #判定各BOSS圈数并获取预约表推送    
        num = 0
        for boss_info in res['boss_info']:
            lap_num = boss_info['lap_num']
            if lap_num != boss_status[num]:
                boss_status[num] = lap_num
                #msg += f'全新的{lap_num}周目{num+1}王来了！'
                push_list = pre_push[num]
                if push_list != []:     #预约后群内和行会内提醒
                    chat_content = f'{lap_num}周目{num+1}王已被预约，请耐心等候！'
                    try:
                        await verify()
                        await client.callapi('/clan/chat', {'clan_id': clan_id, 'type': 0, 'message': chat_content})
                    except:
                        pass
                    warn = ''
                    for pu in push_list:
                        pu = pu.split('|')
                        uid = int(pu[0])
                        gid = int(pu[1])
                        atmsg = f'提醒：已到{lap_num}周目 {num+1} 王！请注意沟通上一尾刀~\n[CQ:at,qq={uid}]'
                        await bot.send_group_msg(group_id = gid,message = atmsg)
                    pre_push[num] = []
            num += 1

    #获取出刀记录并推送最新的出刀        
        if res != 0:
            history = reversed(res['damage_history'])   #从返回的出刀记录刀的状态
            clan_info = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 0})
            clan_id = clan_info['clan']['detail']['clan_id']
            pre_clan_battle_id = await client.callapi('/clan_battle/top', {'clan_id': clan_id, 'is_first': 1, 'current_clan_battle_coin': coin})
            #print(res)
            if arrow == 0:
                for line in open(current_folder + "/Output.txt",encoding='utf-8'):
                    if line != '':
                        line = line.split(',')
                        if line[0] != 'SL':
                            arrow = int(line[4])
                            # print(arrow)
                #file.close()
            clan_battle_id = pre_clan_battle_id['clan_battle_id']
            in_battle = []
            for hst in history:
                if ((arrow != 0) and (int(hst['history_id']) > int(arrow))) or (arrow == 0):   #记录刀ID防止重复
                    
                    name = hst['name']  #名字
                    vid = hst['viewer_id']  #13位ID
                    kill = hst['kill']  #是否击杀
                    damage = hst['damage']  #伤害
                    lap = hst['lap_num']    #圈数
                    boss = int(hst['order_num'])    #几号boss
                    ctime = hst['create_time']  #出刀时间
                    real_time = time.localtime(ctime)   
                    day = real_time[2]  #垃圾代码
                    hour = real_time[3]
                    minu = real_time[4]
                    seconds = real_time[5]
                    arrow = hst['history_id']   #记录指针
                    enemy_id = hst['enemy_id']  #BOSSID，暂时没找到用处
                    is_auto = hst['is_auto']
                    if is_auto == 1:
                        is_auto_r = '自动刀'
                    else:
                        is_auto_r = '手动刀'
        
                    ifkill = ''     #击杀变成可读
                    if kill == 1:
                        ifkill = '并击破'
                        in_game_old[boss-1] = 0
                        #push = True
                        renew_coin = 2   #第二次获取时顺带刷新会战币数量
                    
                    for st in phase:
                        if lap >= st:
                            phases = st
                    phases = phase[phases]                
                    timeline = await client.callapi('/clan_battle/battle_log_list', {'clan_battle_id': clan_battle_id, 'order_num': boss, 'phases': [phases], 'report_types': [1], 'hide_same_units': 0, 'favorite_ids': [], 'sort_type': 3, 'page': 1})
                    timeline_list = timeline['battle_list']
                    #print(timeline_list)
                    start_time = 0
                    used_time = 0
                    for tl in timeline_list:
                        if tl['battle_end_time'] == ctime:
                            blid1 = tl['battle_log_id']
                            tvid = tl['target_viewer_id']
                            # print(blid1)
                            blid = await client.callapi('/clan_battle/timeline_report', {'target_viewer_id': tvid, 'clan_battle_id': clan_battle_id, 'battle_log_id': int(blid1)})
                            start_time = blid['start_remain_time']
                            used_time = blid['battle_time']
                    if start_time == 90:
                        battle_type = f'初始刀{used_time}s'
                    else:
                        battle_type = f'补偿刀{used_time}s'
                    for st in side:
                        if lap >= st:
                            cur_side = st
                    cur_side = side[cur_side]
                    msg += f'[{cur_side}-{battle_type}]{name} 对 {lap} 周目 {boss} 王造成了 {damage} 伤害{ifkill}({is_auto_r})\n'
                    in_battle.append([boss,kill])
                    output = f'{day},{hour},{minu},{seconds},{arrow},{name},{vid},{lap},{boss},{damage},{kill},{enemy_id},{clan_battle_id},{is_auto},{start_time},{used_time},{ctime},'  #记录出刀，后面要用
                    with open(current_folder+"/Output.txt","a",encoding='utf-8') as file:   
                        file.write(str(output)+'\n')
                        file.close()

                    challenge_item = {}
                    if name in name2qq:
                        challenge_item['qqid'] = name2qq[name]
                    else:
                        msg = f'找不到以下游戏成员对应的QQ号码:\n{name}'
                        await bot.send_group_msg(group_id = forward_group_list[0], message = msg)
                        sw = 0
                        return
                    challenge_item['lap_num'] = lap
                    challenge_item['boss'] = boss - 1
                    challenge_item['damage'] = damage
                    challenge_item['kill'] = kill
                    challenge_item['datetime'] = ctime
                    if start_time == 90:
                        challenge_item['reimburse'] = 0
                    else:
                        challenge_item['reimburse'] = 1
                    ret = await report_process(bot, str(forward_group_list[0]), challenge_item)
                    if ret != 0:
                        sw = 0
                        arrow = 0
                        return

            challenge_item['finish'] = 1
            ret = await report_process(bot, str(forward_group_list[0]), challenge_item)
            if ret != 0:
                sw = 0
                arrow = 0
                return

    #记录实战人数变动并推送
            change = False
            for num in range(0,5):  
                boss_info2 = await client.callapi('/clan_battle/boss_info', {'clan_id': clan_id, 'clan_battle_id': clan_battle_id, 'lap_num': boss_status[num], 'order_num': num+1}) 
                fnum = boss_info2['fighter_num']
                if in_game[num] != fnum:
                    if fnum > in_game[num]:
                        diff = fnum - in_game[num]
                        in_game_old[num] += diff
                        
                    in_game[num] = fnum
                    change = True
                if in_battle != []:
                    change = True
                    for ib in in_battle:
                        if in_game_old[ib[0]-1] > 0:
                            in_game_old[ib[0]-1] -= 1
                        if ib[1] == 1:
                            in_game_old[ib[0]-1] = 0

            if change == True:
                renew_coin = 15
                if acinfo['ingame_calc_mode'] == 1:
                    msg += f'当前实战人数发生变化:\n[{in_game_old[0]}][{in_game_old[1]}][{in_game_old[2]}][{in_game_old[3]}][{in_game_old[4]}]'
                else:
                    msg += f'当前90s内实战人数发生变化:\n[{in_game[0]}][{in_game[1]}][{in_game[2]}][{in_game[3]}][{in_game[4]}]'

            if msg != '':
                if len(msg)>200:
                    msg = '...\n' + msg[-200:] 
                # for forward_group in forward_group_list:
                #     await bot.send_group_msg(group_id = forward_group,message = msg)
        else:
            print('error')
    except Exception as e:
        if ('连接中断' or '发生了错误(E)') in str(e):
            for forward_group in forward_group_list:
                await bot.send_group_msg(group_id = forward_group,message = '连接中断，可能顶号，已自动关闭推送，请重新开启会战推送')
            sw = 0
        elif '发生了错误' in str(e):
            print('发生错误，下次重试')
        return  
            

@sv.on_fullmatch('切换会战推送')    #这个给要出刀的号准备的
async def sw_pus(bot , ev):
    global sw
    u_priv = priv.get_user_priv(ev)
    if u_priv < sv.manage_priv and acinfo["only_admin"] == 1:
        await bot.send(ev,'权限不足，当前指令仅管理员可用!')
        return
    if sw == 0:
        sw = 1
        if boss_icon_list == []:
            try:
                date = datetime.date.today()
                dyear = date.year
                dmonth = date.month
                await get_boss_icon(dyear,dmonth)
            except:
                await bot.send(ev,'获取当期BOSS头像失败')
                pass
        await bot.send(ev,'已开启会战推送')
    else:
        sw = 0
        await bot.send(ev,'已关闭会战推送')


@sv.on_fullmatch('初始化会战推送')  #会战前一天输入这个
async def sw_pus(bot , ev):
    global swa,name2qq,forward_group_list
    ret, name2qq = await generate_name2qq(str(forward_group_list[0]))
    date = datetime.date.today()
    dyear = date.year
    dmonth = date.month
    try:
        await get_boss_icon(dyear,dmonth)
    except:
        await bot.send(ev,'获取当期BOSS头像失败')
        pass
    swa = 1
    await bot.send(ev,'初始化完成')



async def get_boss_icon(dyear,dmonth):
    global boss_icon_list
    '''proxies = {
        'http': 'http://127.0.0.1:4780',
        'https': 'http://127.0.0.1:4780',
        }  '''   
    url = 'https://pcr.satroki.tech/api/Quest/GetClanBattleInfos?s=cn'
    #res = requests.get(url,proxies=proxies).json()
    res = requests.get(url).json()#必须考虑代理问题，可能需要改成设置，暂时搁置
    for cres in res:
        if cres["year"] == dyear and cres["month"] == dmonth:
            battle_title = cres["title"]
            boss_icon_list = []
            boss_phase = cres["phases"][0]["bosses"]
            print(boss_phase)
            for bp in boss_phase:
                boss_icon_list.append(bp["unitId"])
    base = 'https://redive.estertion.win/icon/unit/'
    save_dir = current_folder
    print(boss_icon_list)
    for i in boss_icon_list:     
        #res = requests.get(base+str(i)+'.webp',proxies=proxies)
        res = requests.get(base+str(i)+'.webp')
        with open(current_folder + f'/{i}.png', 'wb') as img:
            img.write(res.content)
            img.close()



@sv.on_prefix('会战预约')   #会战预约5
async def preload(bot , ev):
    global pre_push,sw
    if sw == 0:
        await bot.send(ev,'未开启会战推送')
        return
    num = ev.message.extract_plain_text().strip()
    try:
        if int(num) not in [1,2,3,4,5]:
            await bot.send(ev,'点炒饭是吧，爬！')
            return
        else:
            num = int(num)
            qid = str(ev.user_id) + '|' + str(ev.group_id)
            pus = pre_push[num-1]
            warn = ''
            clan_info = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 0})
            clan_id = clan_info['clan']['detail']['clan_id']
            if pus != []:
                warn = f'注意：多于1人同时预约了{num}王，请注意出刀情况!'
            if qid not in pus:
                pus.append(qid)
                await bot.send(ev,f'预约{num}王成功!\n{warn}',at_sender=True)
                if sw == 1:
                    pp1 = ev.user_id
                    name = ''
                    try:
                        info = await bot.get_group_member_info(group_id=ev.group_id, user_id=pp1)
                        name = info['card'] or pp1
                    except CQHttpError as e:
                        print('error name')
                        pass
                    await verify()
                    chat_content = f'一位行会成员({name})预约了{num}王，请注意出(撞)刀情况。{warn}'
                    await client.callapi('/clan/chat', {'clan_id': clan_id, 'type': 0, 'message': chat_content})
            else:
                pus.remove(qid)
                await bot.send(ev,f'你取消预约了{num}王！',at_sender=True)
                if sw == 1:
                    chat_content = f'一位行会成员取消预约了{num}王!'
                    await client.callapi('/clan/chat', {'clan_id': clan_id, 'type': 0, 'message': chat_content})
                    
    except:
        await bot.send(ev,'点炒饭是吧，爬！')
        pass
    
@sv.on_fullmatch('会战表')  #预约列表
async def sw_plist(bot , ev):
    num = 0
    msg  = ''
    for p in pre_push:
        num += 1
        msg += f'{num}王预约列表\n'
        for pp in p:
            pp = pp.split('|')
            # print(pp)
            pp1 = int(pp[0])
            pp2 = int(pp[1])
            
            try:
                info = await bot.get_group_member_info(group_id=pp2, user_id=pp1)
                name = info['card'] or pp1
            except CQHttpError as e:
                print('error name')
                pass
            msg += f'+{name}\n'
    await bot.send(ev,msg)
    
@sv.on_fullmatch('清空预约表')
async def cle(bot , ev): 
    global pre_push
    u_priv = priv.get_user_priv(ev)
    if u_priv < sv.manage_priv and acinfo["only_admin"] == 1:
        await bot.send(ev,'权限不足，当前指令仅管理员可用!')
        return
    pre_push = pre_push = [[],[],[],[],[]]
    await bot.send(ev,'已全部清空')
    
@sv.on_fullmatch('会战帮助')
async def chelp(bot , ev): 
    # msg = '[查轴[A/B/C/D/E][S/T/TS][1/2/3/4/5][ID]]:查轴，中括号内为选填项，可叠加使用。*S/T/TS分别表示手动/自动/半自动*\n[分刀[A/B/C/D/E][毛分/毛伤][S/T/TS][1/2/3/4/5]]:根据box分刀，中括号内为选填项，可叠加使用。*可选择限定boss，如123代表限定123王*\n[(添加/删除)(角色/作业)黑名单 + 名称或ID]:支持多角色，例如春环环奈，无空格。作业序号：花舞作业的序号，如‘A101’\n[(添加/删除)角色缺失 + 角色名称]:支持多角色，例如春环环奈，无空格\n[查看(作业黑名单/角色缺失/角色黑名单)]\n[清空(作业黑名单/角色缺失/角色黑名单)]\n[切换会战推送]:打开/关闭会战推送\n[会战预约(1/2/3/4/5)]:预约提醒\n[会战表]:查看所有预约\n[编写中...][会战查刀(ID)]:查看出刀详情\n[查档线]:若参数为空，则输出10000名内各档档线；若有多个参数，请使用英文逗号隔开。\n[清空预约表]:(仅SU可用)\n'
    msg = '[查档线]:若参数为空，则输出10000名内各档档线；若有多个参数，请使用英文逗号隔开。新增按照关键词查档线。结算期间数据为空\n[初始化会战推送]:会战前一天输入这个，记得清空Output.txt内的内容，不要删除Output.txt\n[切换会战推送]:打开/关闭会战推送\n[会战预约(1/2/3/4/5)]:预约提醒\n[会战表]:查看所有预约\n[清空预约表]:(仅SU可用)\nsl + 关键ID:为玩家打上SL标记'
    await bot.send(ev,msg)


def rounded_rectangle(size, radius, color):     #ChatGPT帮我写的，我也不会
    width, height = size
    rectangle = Image.new("RGBA", size, color)
    corner = Image.new("RGBA", (radius, radius), (0, 0, 0, 0))
    filled_corner = Image.new("RGBA", (radius, radius), (0, 0, 0, 255))
    mask = Image.new("L", (radius, radius), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, radius * 2, radius * 2), fill=255)

    corner.paste(filled_corner, (0, 0), mask)

    rectangle.paste(corner, (0, 0))
    rectangle.paste(corner.rotate(90), (0, height - radius))
    rectangle.paste(corner.rotate(180), (width - radius, height - radius))
    rectangle.paste(corner.rotate(270), (width - radius, 0))

    return rectangle

def format_number_with_commas(number):      #这个也是他帮我写的
    return '{:,}'.format(number)

#@sv.on_fullmatch('输出会战日志')       #服务器不同
async def cout(bot , ev): 
    cfile = current_folder+ '/Output.txt'
    now = time.strftime("%Y-%m-%d %H:%M:%S",time.localtime())
    name = f'Output - Log {now}'
    await bot.upload_group_file(group_id = ev.group_id, file = cfile, name = name)
    await bot.send(ev, '上传完成')

@sv.on_rex(r'^切换账号(?: |)([\s\S]*)')
async def status(bot, ev):
    match = ev['match']
    if not match : return

    account = match.group(1)
    if account not in clients: return await bot.send(ev, '不存在该账号')
    global client
    client = clients[account]
    await bot.send(ev, '切换成功')

@sv.on_prefix('会战状态')    #这个更是重量级
async def status(bot,ev):
    global sw,health_list,phase,chat_list
    u_priv = priv.get_user_priv(ev)
    if u_priv < sv.manage_priv and acinfo["only_admin"] == 1:
        await bot.send(ev,'权限不足，当前指令仅管理员可用!')
        return
    status = ev.message.extract_plain_text().strip()
    if sw == 0 and status != '1':
        await bot.send(ev,'现在会战推送状态为关闭，请确认是否有人上号，如果仍然需要查看状态，请输入 会战状态1 来确认')
        return
    #try:
    if acinfo["statu_text_mode"] == 1:
        msg = ''
        load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})
        clan_info = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 0})
        clan_id = clan_info['clan']['detail']['clan_id']
        item_list = {}
        for item in load_index["item_list"]:
            item_list[item["id"]] = item["stock"]
        coin = item_list[90006]   
        res = await client.callapi('/clan_battle/top', {'clan_id': clan_id, 'is_first': 1, 'current_clan_battle_coin': coin})
        clan_battle_id = res['clan_battle_id']
        clan_name = res['user_clan']['clan_name']
        rank = res['period_rank']
        lap = res['lap_num']
        msg += f'{clan_name}[{rank}名]--{lap}周目\n※实战人数指90秒内人数\n'
        for boss in res['boss_info']:
            boss_num = boss['order_num']
            boss_id = boss['enemy_id']
            boss_lap_num = boss['lap_num']
            mhp = boss['max_hp']
            hp = boss['current_hp']
            hp_percentage = int((hp / mhp)*100)  # 计算血量百分比
            boss_info2 = await client.callapi('/clan_battle/boss_info', {'clan_id': clan_id, 'clan_battle_id': clan_battle_id, 'lap_num': boss_lap_num, 'order_num': boss_num}) 
            fnum = boss_info2['fighter_num']
            msg += f'{boss_lap_num}周目{boss_num}王 剩余{hp}血({hp_percentage}%)|{fnum}人实战\n'
        await bot.send(ev,msg)
    else:    
        await bot.send(ev,'生成中...')
        ##第一部分:验证
        img = Image.open(img_file+'/hz/bg.png')                          #背景图片
        draw = ImageDraw.Draw(img)
        await verify()
        load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})
        clan_info = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 0})
        '''with open(os.path.join(os.path.dirname(__file__),f"load_index.json"), "w", encoding='utf-8') as f:                                       
             f.write(json.dumps(load_index, indent=4,ensure_ascii=False))''' #保存json，用于测试，轮询太久了
        '''with open(os.path.join(os.path.dirname(__file__),f"load_index.json"), "r", encoding='utf-8') as f:
             load_index=json.load(f)'''                                      #仅用于读取json测试

        try:
            clan_id = clan_info['clan']['detail']['clan_id']               #报错 KeyError: 'clan'
        except:
            return await bot.send(ev, "报错了，请重试")
        item_list = {}
        try:
            for item in load_index["item_list"]:                           #报错 KeyError: 'item_list'
                item_list[item["id"]] = item["stock"]
        except:
            return await bot.send(ev, "报错了，请重试")
        coin = item_list[90006]   
        res = await client.callapi('/clan_battle/top', {'clan_id': clan_id, 'is_first': 1, 'current_clan_battle_coin': coin})
        clan_battle_id = res['clan_battle_id']
        clan_name = res['user_clan']['clan_name']
        setFont = ImageFont.truetype(img_file+'//084.ttf', 45)
        draw.text((5,1582), f'{clan_name}', font=setFont, fill="#367cf7")
        rank = res['period_rank']
        setFont = ImageFont.truetype(img_file+'//084.ttf', 85)
        draw.text((10,1786), f'{rank}', font=setFont, fill="#367cf7")
        ###第一部分：如果当前boss有人出刀，将boss血条变色
        try:
               shape_image = Image.open(img_file+'/hz/h01.png')         #导入遮罩
               original_image = Image.open(img_file+"/hz/1.png")
               result_image = Image.new("RGBA", original_image.size, (0, 0, 0, 0))
               for num in range(0,5):  
                 boss_info2 = await client.callapi('/clan_battle/boss_info', {'clan_id': clan_id, 'clan_battle_id': clan_battle_id, 'lap_num': boss_status[num], 'order_num': num+1}) 
                 fnum = boss_info2['fighter_num']
                 circlelist = [59,365,671,977,1283]
                 if fnum!=0:
                      result_image.paste(shape_image, (324,circlelist[num]), mask=shape_image)
                 result_image.paste(original_image, (0, 0), mask=result_image)
        except:
                pass
        img.paste(result_image, (0, 0), mask=result_image)
        ###第二部分：计算血量百分比，改变boss血量进度条
        lap = res['lap_num']
        img_num = 0 
        for boss in res['boss_info']:
            boss_num = boss['order_num']
            boss_id = boss['enemy_id']
            boss_lap_num = boss['lap_num']
            mhp = boss['max_hp']
            hp = boss['current_hp']
            hp_percentage = hp / mhp  # 计算血量百分比
            img=drawjingdutiao(hp_percentage,img,boss_num)# 根据血量百分比设置血条颜色
            draw = ImageDraw.Draw(img)
            ### 第三部分：输出boss头像
            try:    
                try:
                    img2 = Image.open(current_folder+f'/{boss_icon_list[img_num]}.png')
                except:
                    img2 = R.img(f'priconne/unit/icon_unit_100131.png').open()
                img_num += 1
                fanglist =[49,350,656,962,1268]                           #boss图片的位置
                shape2_image = Image.open(img_file+'/hz/h02.png')         #导入遮罩
                m2 = Image.new('RGBA', shape2_image.size) 
                img3=img2.resize(shape2_image.size,Image.LANCZOS)         #boss图片改大小
                m2.paste(img3, mask=shape2_image)
                img.paste(m2, (17, fanglist[boss_num-1]),mask=m2)   
            except Exception as e:
                print(e)
                pass
            
            ###第四部分输出血量，输出周目，输出abcde阶段
            for st in side:
                if boss_lap_num >= st:
                    cur_stage = st
            cur_stage = side[cur_stage]
            boss_lap_num_list =[84, 390, 696, 1002, 1308]
            bosshplist = [69, 375, 681, 987, 1293]
            setFont = ImageFont.truetype(img_file+'//027.ttf', 68)
            list =[49,350,656,962,1268]
            draw.text((510, bosshplist[boss_num-1]), f'{format_number_with_commas(hp)}/{format_number_with_commas(mhp)}', font=setFont, fill="#4662ec")
            setFont = ImageFont.truetype(img_file+'//MiSans-Demibold.ttf', 125)
            draw.text((319, boss_lap_num_list[boss_num-1]), f'{boss_lap_num}', font=setFont, fill="#229d9c")
            setFont = ImageFont.truetype(img_file+'//MiSans-Demibold.ttf', 40)
            draw.text((290, boss_lap_num_list[boss_num-1]+170), f'{cur_stage}', font=setFont, fill="#ffffff")
            ###第五部分：输出当前预约情况
            pre = pre_push[boss_num-1]
            all_name = ''
            if pre != []:
                
                for pu in pre:
                    pu = pu.split('|')
                    uid = int(pu[0])
                    gid = int(pu[1])
            
            
                    pp1 = uid
                    name = ''
                    try:
                        info = await bot.get_stranger_info(self_id=ev.self_id, user_id=pp1)
                        name = info['nickname'] or pp1
                        name = util.filt_message(name)
                        all_name += f'{name} '
                    except CQHttpError as e:
                        print('error name')
                        pass
            yuyuelist=[139, 455, 761, 1067, 1373]
            setFont = ImageFont.truetype(img_file+'//027.ttf', 50)
            if all_name != '':
                all_name+='已预约'
                all_name=line_break(all_name)
                draw.text((515, yuyuelist[boss_num-1]), f'{all_name}', font=setFont, fill="#030852")
            else:
                draw.text((515, yuyuelist[boss_num-1]), f'无人预约', font=setFont, fill="#030852")
            
        ###第六部分:输出公会头像，出刀情况(这部分没动过)    
        res2 = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 1})
        row = 0
        width = 0
        setFont = ImageFont.truetype(img_file+'//084.ttf', 85)
        last_rank = res2['last_total_ranking']
        draw.text((210, 1786), f'{last_rank}', font=setFont, fill="#367cf7")
        all_battle_count = 0
        for members in res2['clan']['members']:
            vid = members['viewer_id']
            name = members['name']
            favor = members['favorite_unit']
            favorid = str(favor['id'])[:-2]
            stars = 3 if members['favorite_unit']['unit_rarity'] != 6 else 6
            try:
                img2 = R.img(f'priconne/unit/icon_unit_{favorid}{stars}1.png').open()
                img2 = img2.resize((48,48),Image.ANTIALIAS)
        
                img.paste(img2, (435+int(149.5*width), 1630+int(59.8*row)), img2)
            except:
                pass
            kill_sign = 0

            kill_acc = 0
            todayt = time.localtime()
            hourh = todayt[3]
            today = 0
            if hourh < 5:
                today = todayt[2]-1
            else:
                today = todayt[2]
            
            #today = 26
            #实用性存疑，不如改成输出第几天，暂时不管
            setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 15)
            #draw.text((1000,760), f'{today}日', font=setFont, fill="#A020F0")
            img3 = Image.new('RGB', (25, 17), "white")
            img4 = Image.new('RGB', (12, 17), "red")
            #img5 = Image.new('RGB', (25, 17), "green")
            time_sign = 0
            half_sign = 0
            sl_sign = 0
            for line in open(current_folder + "/Output.txt",encoding='utf-8'):
                if line != '':
                    line = line.split(',')
                    # print(line[0])
                    if line[0] == 'SL':
                        mode = 1
                        re_vid = int(line[2])
                        day = int(line[3])
                        hour = int(line[4])
                    else:
                        mode = 2
                        day = int(line[0])
                        hour = int(line[1])
                        re_battle_id = int(line[4])
                        re_name = line[5]
                        re_vid = line[6]
                        re_lap = int(line[7])
                        re_boss = int(line[8])
                        re_dmg = int(line[9])
                        re_kill = int(line[10])
                        re_boss_id = int(line[11])
                        re_clan_battle_id = int(line[12])
                        re_is_auto = int(line[13])
                        re_start_time = int(line[14])
                        re_battle_time = int(line[15])
                    if_today = False
                    if ((day == today and hour >= 5) or (day == today + 1 and hour < 5)) and (re_clan_battle_id == clan_battle_id) and mode == 2:
                        if_today = True
                    if ((day == today and hour >= 5) or (day == today + 1 and hour < 5)) and mode == 1:
                        if_today = True
                    
                    
                    if if_today == True and mode == 1 and int(vid) == int(re_vid):
                        sl_sign = 1
                    
                    if int(vid) == int(re_vid) and if_today == True and mode == 2:
                        full_check = 0
                        if re_start_time == 90 and re_kill == 1:
                            if time_sign >= 1:
                                time_sign -= 1
                                half_sign -= 0.5
                                kill_acc += 0.5
                                continue
                            if re_battle_time <= 20 and re_battle_time != 0:
                                time_sign += 1
                            dmgcheck = 0
                            for check in open(current_folder + "/Output.txt",encoding='utf-8'):
                                if check != '':
                                    check = check.split(',')
                                    if check[0] != 'SL' and (check[7] == re_lap and check[8] == re_boss):
                                        dmgcheck += check[9]
                            for st in phase:
                                if re_lap >= st:
                                    phases = st
                            phases = phase[phases] 
                            if dmgcheck > health_list[phases-1][re_boss-1]:     #总伤害大于BOSS血量，判定为满补
                                full_check += 1


                            kill_acc += 0.5
                            half_sign += 0.5
                        elif re_start_time == 90 and re_kill == 0:
                            if time_sign >= 1:
                                kill_acc += 0.5
                                time_sign -= 1
                                half_sign -= 0.5
                                continue
                            kill_acc += 1
                        else:
                            kill_acc += 0.5
                            half_sign -= 0.5
            # if full_check != 0:        
            #     kill_acc -= 0.5*full_check        
            if kill_acc > 3:    #对满补刀无从下手，先限定三刀补一下
                kill_acc = 3
                half_sogn = 0
            all_battle_count += kill_acc
            
            if kill_acc == 0:
                draw.text((483+149*width, 1630+60*row), f'{name}', font=setFont, fill="#FF0000")
            elif 0< kill_acc < 3:
                draw.text((483+149*width, 1630+60*row), f'{name}', font=setFont, fill="#FF00FF")
            elif kill_acc == 3:
                draw.text((483+149*width, 1630+60*row), f'{name}', font=setFont, fill="#FFFF00")
            width2 = 0
            kill_acc = kill_acc - half_sign
            while kill_acc-1 >=0:
                img.paste(img3, (480+int(149.5*width)+30*width2, 1654+60*row))
                kill_acc -= 1
                width2 += 1
            while half_sign-0.5 >=0:
                img.paste(img4, (480+int(149.5*width)+30*width2, 1654+60*row))
                half_sign -= 0.5
                width2 += 1
            if sl_sign == 1:
                draw.text((433+int(149.5*width), 1654+60*row), f'SL', font=setFont, fill="black")
            width += 1
            if width == 5:
                width = 0
                row += 1    
        ###第七部分:输出今日已出xx刀/90刀
        count_m = len(res2['clan']['members'])*3  
        setFont = ImageFont.truetype(img_file+'//084.ttf', 45)
        draw.text((20,2000), f'{all_battle_count}刀/{count_m}刀', font=setFont, fill="#367cf7")      
        ###第八部分:输出最近出刀战绩(这部分没动过)  
        if res != 0:
            
            info = res['boss_info'] #BOSS
            next_lap_1 = res['lap_num']    #周目
            next_boss = 1
            msg = ''
            history = res['damage_history']
            order = 0
            for hst in history:
                order += 1
                if order < 21:
                    name = hst['name']
                    vid = hst['viewer_id']
                    kill = hst['kill']
                    damage = hst['damage']
                    lap = hst['lap_num']
                    boss = int(hst['order_num'])
                    ctime = hst['create_time']
                    real_time = time.localtime(ctime)
                    day = real_time[2]
                    hour = real_time[3]
                    minu = real_time[4]
                    seconds = real_time[5]
                    arrow = hst['history_id']
                    #real_time = time.strftime('%d - %H:%M:%S', time.localtime(ctime))
                    enemy_id = hst['enemy_id']
                    if boss == 5:
                        next_boss = 1
                        next_lap = lap + 1
                    else:
                        next_boss = boss + 1
                        next_lap = lap
                    ifkill = ''
                    if kill == 1:
                        ifkill = '并击破'
                        #push = True
                    msg = f'[{day}日{hour:02}:{minu:02}]{name} 对 {lap} 周目 {boss} 王造成了 {damage} 伤害{ifkill}'
                    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 20)
                    if kill == 1:
                        draw.text((440, 2170+(order*20)), f'{msg}', font=setFont, fill="black")
                    else:
                        draw.text((440, 2170+(order*20)), f'{msg}', font=setFont, fill="purple")
            ###第九部分：留言（没用过，直接照搬）
            qid = ev.group_id
            if qid not in chat_list:
                draw.text((440,2150), f'本群暂时没有留言！', font=setFont, fill="#A020F0")
            else:
                msg = '留言板：\n'
                for i in range(0,len(chat_list[qid]["uid"])):
                    time_now = int(time.time())
                    time_diff = time_now - chat_list[qid]["time"][i]
                    if time_diff <= 60:
                        time_diff = '刚刚'
                    else:
                        time_diff = int(time_diff/60)
                        time_diff = f'{time_diff}分钟前'
                    nickname = chat_list[qid]["uid"][i]
                    try:
                        nickname = await bot.get_group_member_info(group_id = qid,user_id = (chat_list[qid]["uid"][i]))
                        nickname = nickname['nickname']
                    except:
                        pass
                    chat = chat_list[qid]["text"][i]
                    msg += f'[{time_diff}]{nickname}:{chat}\n'
                draw.text((440,2130), f'{msg}', font=setFont, fill="#A020F0")         
        else:
            print('error')
        ###第十部分：收尾
        width = img.size[0]   # 获取宽度
        height = img.size[1]   # 获取高度
        img = img.resize((int(width*1), int(height*1)), Image.ANTIALIAS)    
        bright_enhancer = ImageEnhance.Brightness(img)
        # 传入调整系数1.1,改变亮度
        img = bright_enhancer.enhance(1.1)
        img = p2ic2b64(img)
        img = MessageSegment.image(img)

        await bot.send(ev, img)
        # except:
        #     await bot.send(ev,'发生不可预料的错误，请重试')
        #     pass

@sv.on_prefix('抓人')
async def get_battle_status(bot,ev):
    u_priv = priv.get_user_priv(ev)
    if u_priv < sv.manage_priv and acinfo["only_admin"] == 1:
        await bot.send(ev,'权限不足，当前指令仅管理员可用!')
        return
    msg = ev.message.extract_plain_text().strip()
    if msg != '':
        today = int(msg)
    else:
        todayt = time.localtime()
        hourh = todayt[3]
        today = 0
        if hourh < 5:
            today = todayt[2]-1
        else:
            today = todayt[2]      
    await verify()
    load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})
    clan_info = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 0})
    clan_id = clan_info['clan']['detail']['clan_id']
    item_list = {}
    for item in load_index["item_list"]:
        item_list[item["id"]] = item["stock"]
    coin = item_list[90006]   
    res = await client.callapi('/clan_battle/top', {'clan_id': clan_id, 'is_first': 1, 'current_clan_battle_coin': coin})
    clan_battle_id = res['clan_battle_id']
    day_sign = 0
    num = 0
    max_page = 0
    battle_history_list = []
    l1h = [[6000000,8000000,10000000,12000000,15000000],[6000000,8000000,10000000,12000000,15000000],[10000000,11000000,16000000,18000000,22000000],[18000000,19000000,22000000,23000000,26000000],[85000000,90000000,95000000,100000000,110000000]]
    while(day_sign == 0):
        num += 1
        timeline = await client.callapi('/clan_battle/battle_log_list', {'clan_battle_id': clan_battle_id, 'order_num': 0, 'phases': [1,2,3,4,5], 'report_types': [1], 'hide_same_units': 0, 'favorite_ids': [], 'sort_type': 3, 'page': num})
        if max_page == 0:
            max_page = timeline['max_page']
        max_page1 = timeline['max_page']
        if max_page1 < max_page:
            day_sign = 1
        for tl in timeline['battle_list']:
            tvid = tl['target_viewer_id']
            log_id = tl['battle_log_id']
            ordern_num = tl['order_num']
            lap_num = tl['lap_num']
            battle_end_time = tl['battle_end_time']
            damage = tl['total_damage']
            #目前暂时无法计算跨日残血boss合刀，对该部分玩家的计算会有偏差，应该可以从这里入手
            usrname = tl['user_name']
            hr = time.localtime(battle_end_time)
            day = hr[2]
            hour = hr[3]
            if (day == today and hour >= 5) or (day == today + 1 and hour < 5):
                battle_history_list.append([tvid,log_id,usrname,ordern_num,lap_num,damage])
            if (day < today):
                day_sign = 1

    
    for log in battle_history_list:
        extra_back = 0
        tvid = log[0]
        log_id = log[1]
        usrname = log[2]
        ordern_num = log[3]
        lap_num = log[4]
        damage = log[5]
        total_dmg = 0
        tvid3 = 0
        for log2 in battle_history_list:
            tvid2 = log2[0]
            ordern_num2 = log2[3]
            lap_num2 = log2[4]
            damage2 = log2[5]
            if ordern_num == ordern_num2 and lap_num == lap_num2:
                if tvid3 == 0:
                    tvid3 = tvid2
                total_dmg += damage2
        for st in phase:
            if lap_num >= st:
                cur_side = st
        cur_side = phase[cur_side]
        if total_dmg > l1h[cur_side-1][ordern_num-1] and (int(tvid3) == int(tvid)):
            extra_back = 1


        blid = await client.callapi('/clan_battle/timeline_report', {'target_viewer_id': tvid, 'clan_battle_id': clan_battle_id, 'battle_log_id': int(log_id)})
        start_time = blid['start_remain_time']
        used_time = blid['battle_time']
        for tl in blid['timeline']:
            if tl['is_battle_finish'] == 1:
                remain_time = tl['remain_time']
                if remain_time != 0:
                    kill = 1
                else:
                    kill = 0
        log.append(start_time)
        log.append(used_time)
        log.append(kill)
        log.append(extra_back)
    res2 = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 1})
    #lack_list = []
    msg = ''
    for members in res2['clan']['members']:
        vid = members['viewer_id']
        name = members['name']
        time_sign = 0
        half_sign = 0
        kill_acc = 0
        for log in battle_history_list:
            if log[0] == vid:
                start_time = log[6]
                used_time = log[7]
                kill = log[8]
                extra_back = log[9]
                if extra_back == 1:
                    kill_acc += 0.5
                    half_sign += 0.5
                    continue
                if start_time == 90 and kill == 1:
                    if time_sign >= 1:
                        time_sign -= 1
                        half_sign -= 0.5
                        kill_acc += 0.5
                        continue
                    if used_time <= 20 and used_time != 0:
                        time_sign += 1
                    kill_acc += 0.5
                    half_sign += 0.5
                elif start_time == 90 and kill == 0:
                    if time_sign >= 1:
                        kill_acc += 0.5
                        time_sign -= 1
                        half_sign -= 0.5
                        continue
                    kill_acc += 1
                else:
                    kill_acc += 0.5
                    half_sign -= 0.5
        if kill_acc < 3:
            msg += f'{name}缺少{3-kill_acc}刀\n目前暂时无法计算跨日残血boss合刀，对该部分玩家的计算会有偏差'
    if msg != '':
        await bot.send(ev,msg)
    
@sv.on_prefix('sl')     
async def sl(bot,ev):
    if sw == 0:
        await bot.send(ev,'未开启会战推送，无法sl')
        return
    usrname = ev.message.extract_plain_text().strip()
    if usrname == '':
        # pp1 = ev.user_id
        # try:
        #     info = await bot.get_group_member_info(group_id=ev.group_id, user_id=pp1)
        #     usrname = info['card'] or pp1
        # except CQHttpError as e:
        #     print('error name')
        #     pass      
        await bot.send(ev,'由于不进行绑定，请输入一个游戏内的ID辨识(关键词搜索)')
        return
    else:
        #try:
        await verify()
        res2 = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 1})
        search_sign = 0
        vid0 = 0
        for members in res2['clan']['members']:
            vid = members['viewer_id']
            name = str(members['name'])
            
            if (usrname == name) or (usrname in name):
                usrname = name
                todayt = time.localtime()
                hourh = todayt[3]
                monm = todayt[1]
                today = 0
                if hourh < 5:
                    today = todayt[2]-1
                else:
                    today = todayt[2]
                for line in open(current_folder + "/Output.txt",encoding='utf-8'):
                    if line != '':
                        line = line.split(',')
                        if line[0] == 'SL':
                            name2 = line[1]
                            vid0 = int(line[2])
                            day = int(line[3])
                            hour = int(line[4])
                            minu = int(line[5])
                            seconds = int(line[6])
                            mon = line[7]
                            if (name2 == name) and (((day == today and hour >= 5) or (day == today + 1 and hour < 5))):
                                await bot.send(ev,f'({name})已于{hour}:{minu}进行过SL操作！')
                                return
                vid0 = vid
                search_sign = 1
                break
        if search_sign == 1:
            real_time = time.localtime()
            mon = real_time[1]
            day = real_time[2]  #垃圾代码
            hour = real_time[3]
            minu = real_time[4]
            seconds = real_time[5]
            output = f'SL,{usrname},{vid0},{day},{hour},{minu},{seconds},{mon},'
            with open(current_folder+"/Output.txt","a",encoding='utf-8') as file:   
                file.write(str(output)+'\n')
                file.close()
            await bot.send(ev,f'{name}({vid0})已上报SL')
        else:
            await bot.send(ev,'没有找到这个ID，请确认')
            return
        # except:
        #     await bot.send(ev,'发生连接错误，请重试')
        #     pass

def p2ic2b64(img, quality=90):
    # 如果图像模式为RGBA，则将其转换为RGB模式
    if img.mode == 'RGBA':
        img_rgb = Image.new('RGB', img.size, (255, 255, 255))
        img_rgb.paste(img, mask=img.split()[3])  # 使用alpha通道作为mask
        img = img_rgb

    buf = BytesIO()
    img.save(buf, format='JPEG', quality=quality)
    base64_str = base64.b64encode(buf.getvalue()).decode('utf-8')
    return 'base64://' + base64_str
    
@sv.scheduled_job('cron', hour='5') #推送5点时的名次
async def rank_and_status():
    global sw,swa,forward_group_list
    if sw == 1:
        await verify()
        try:
            load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})
        except:
            load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})
        item_list = {}
        for item in load_index["item_list"]:
            item_list[item["id"]] = item["stock"]
        coin = item_list[90006]
        clan_info = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 0})
        clan_id = clan_info['clan']['detail']['clan_id']
        res = await client.callapi('/clan_battle/top', {'clan_id': clan_id, 'is_first': 1, 'current_clan_battle_coin': coin})
        #print(res)
        rank = res['period_rank']
        msg = f'当前的排名为{rank}位'
        for forward_group in forward_group_list:
            await bot.send_group_msg(group_id = forward_group,message = msg)
            
        
    if swa == 1:
        # sw = 1
        swa = 0





#查档线等待修改和上传图片
RANK_LST = [1,4,11,21,51,201,601,1201,2801,5001,10001,15001,25001,40001,60001]



@sv.on_prefix('查档线')     #从游戏内获取数据，无数据时返回空
async def query_line(bot,ev):
    u_priv = priv.get_user_priv(ev)
    if u_priv < sv.manage_priv and acinfo["only_admin"] == 1:
        await bot.send(ev,'权限不足，当前指令仅管理员可用!')
        return
    goal = ev.message.extract_plain_text().strip()
    await verify()
    try:
        load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})
    except:
        load_index = await client.callapi('/load/index', {'carrier': 'OPPO'})
    try:
        goal_list = []
        if re.match("^[0-9,]+$", goal):
            # print('mode1')
            rank_mode = 1
            if ',' in goal:
                goal_list = goal.split(',')
            else:
                goal_list.append(goal)
        elif goal == '':
            goal_list = [1,4,11,21,51,201,601,1201,2801,5001]
            await bot.send(ev,'获取数据时间较长，请稍候')
        else:
            rank_mode = 2
            goal_list = []
            await bot.send(ev,f'正在搜索行会关键词{goal}')
            clan_name_search =  await client.callapi('/clan/search_clan', {'clan_name': goal, 'join_condition': 1, 'member_condition_range': 0, 'activity': 0, 'clan_battle_mode': 0})
            clan_list = ''
            for clan in clan_name_search['list']:
                clan_name = clan['clan_name']
                clan_list += f'[{clan_name}]'
            clan_num = len(clan_name_search['list'])
            await bot.send(ev,f'找到{clan_num}个与关键词相关行会,超过5个的将不会查询，请精确化关键词\n{clan_list}')
            clan_num = 0
            for clan in clan_name_search['list']:
                
                if clan_num <= 4:
                    clan_id = clan['clan_id']
                    # print(clan_id)
                    if clan_id == 0:
                        break
                    clan_most_info = await client.callapi('/clan/others_info', {'clan_id': clan_id})
                    clan_most_info = clan_most_info['clan']['detail']['current_period_ranking']
                    if clan_most_info == 0:
                        continue
                    goal_list.append(clan_most_info)
                    clan_num += 1

                else:
                    break
                    #goal_list.append(clan_most_info)
                    #print(goal_list)
        if goal_list == []:
            await bot.send(ev,'无法获取排名，可能是官方正在结算，请等待结算后使用本功能')
            return
        width2 = 500*len(goal_list)
        img4 = Image.new('RGB', (1000, width2), (255, 255, 255))    
        all_num = 0
        # print(len(goal_list))
        for goal in goal_list:
            goal = int(goal)
            item_list = {}
            for item in load_index["item_list"]:
                item_list[item["id"]] = item["stock"]
            coin = item_list[90006]   
            load_index2 = await client.callapi('/clan/info', {'clan_id': 0, 'get_user_equip': 1})
            clan_name = load_index2
            clan_id = clan_name['clan']['detail']['clan_id']
            res = await client.callapi('/clan_battle/top', {'clan_id': clan_id, 'is_first': 1, 'current_clan_battle_coin': coin})
            clan_battle_id = res['clan_battle_id']
    
            page = int((goal-1)/10)
            indi = goal%10
            if indi == 0:
                indi = 10
            
            page_info = await client.callapi('/clan_battle/period_ranking', {'clan_id': clan_id, 'clan_battle_id': clan_battle_id, 'period': 1, 'month': 0, 'page': page, 'is_my_clan': 0, 'is_first': 1})
            if page_info['period_ranking'] == []:
                await bot.send(ev,'当前会战排名正在结算，无法获取数据，请等待官方结算完成后再使用本功能~')
                return
            #print(page_info)
            num = 0
            
            lap = 0
            boss = 0
            
            stage = [207300000,859700000,4771700000,9017700000,999999999999]
            l1 = [[7200000,9600000,13000000,16800000,22500000],[9600000,12800000,18000000,22800000,30000000],[24000000,28000000,40800000,45600000,57200000],[66500000,70000000,85100000,95000000,108000000],[297500000,315000000,351500000,380000000,440000000]]
            lp = [3,10,30,40,999]
            
            for rank in page_info['period_ranking']:
                num += 1
                if num == indi:
                    rank_num = rank['rank']
                    dmg = rank['damage']
                    mem = rank['member_num']
                    name = rank['clan_name']
                    lvid = rank['leader_viewer_id']
                    lname = rank['leader_name']
                    lunit = rank['leader_favorite_unit']['id']
                    grank = rank['grade_rank']
                    
                    
                    for stag in stage:
                        lap += 1
                        if dmg <= stag:
                            dmg_left = dmg - stage[lap-2]
                            break
                    
                    llps = 0
                    while(dmg_left > 0):
                        boss = 0
                        for i in l1[lap-1]:
                            if dmg_left - i > 0:
                                boss += 1 
                                dmg_left -= i
                            else:
                                final_dmg = dmg_left
                                final_dmgg = i
                                dmg_left = -1
                                break
                        llps += 1
                        #print(1)
                    final_lap = lp[lap-2] + llps
                    progress = (float(final_dmg/i)*100)
                    progress = round(progress, 2)
                    msg = f'当前第 {lap} 阶段 | 第 {final_lap} 周目 {boss+1} 王 | 进度 {progress}%'
                    # print(msg)
                    
                    R_n = 0
                    for RA in RANK_LST:
                        if rank_num < RA:
                            prev_r = RA
                            next_r = RANK_LST[R_n-1]
                            break
                        R_n += 1
                    img_file2 = '/data_new/Hoshino/res/img/priconne/unit'
                    icon_unit = rank['leader_favorite_unit']['id']
                    stars = rank['leader_favorite_unit']['unit_rarity']
                    st = 1 if stars < 3 else 3
                    st = st if st != 6 else 6
                    chara_id = str(icon_unit)[:-2]           
         ############################################           
                    clan_ids = ''
                    clan_idsss = 0
                    for n in range(0,6):
                        clan_info = await client.callapi('/clan/search_clan', {'clan_name': name, 'join_condition': 1, 'member_condition_range': 0, 'activity': 0, 'clan_battle_mode': 0})
                        #print(clan_info)
                        try:
                            clan_ids = clan_info['list']
                            for clan_idss in clan_ids:
                                clan_lid = clan_idss['leader_viewer_id']
                                if lvid == clan_lid:
                                    clan_idsss = clan_idss['clan_id']
                                    break
                        except:
                            result = f'获取行会信息失败{n}/n'
                            print(result)
                            
                            pass
                    img = Image.open(img_file + f'//bkg.png')
                    draw = ImageDraw.Draw(img)            
                    if clan_idsss == 0:
                        info_msg = f'获取行会信息失败(该行会未开放搜索或同名过多)'
                        setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 15)
                        draw.text((350,250), f'{info_msg}', font=setFont, fill="#4A515A")
                    else:
                        clan_most_info = await client.callapi('/clan/others_info', {'clan_id': clan_idsss})
                        clan_member = clan_most_info['clan']['members']
                        descrip = clan_most_info['clan']['detail']['description']
                        join_con = clan_most_info['clan']['detail']['join_condition']
        
                    
                    wi = 0
                    de = 0
                    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 15)
                    try:
                        for member in clan_member:
                            vid = member['viewer_id']
                            usr_name = member['name']
                            level = member['level']
                            lg_time = member['last_login_time']
                            power = member['total_power']
                            #clan_point = member['clan_point']
                            time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(lg_time))
                            draw.text((350+wi*120,250+de*20), f'{usr_name}', font=setFont, fill="#4A515A")
                            wi += 1
                            if wi >= 5:
                                wi = 0
                                de += 1
                    except:
                        pass
                    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 20)
                    draw.text((20,220), f'当前位次: {rank_num}位', font=setFont, fill="#4A515A")
                    draw.text((20,240), f'会长: {lname}', font=setFont, fill="#4A515A")
                    draw.text((20,260), f'VID: [{lvid}]', font=setFont, fill="#4A515A")
                    draw.text((20,280), f'上期位次: {grank}位', font=setFont, fill="#4A515A")
                    try:
                        draw.text((20,180), f'{descrip}', font=setFont, fill="#4A515A")
                    except:
                        pass
                    draw.text((350,220), msg, font=setFont, fill="#4A515A")
                    
                    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 30)
                    draw.text((750,75), f'{dmg}', font=setFont, fill="#4A515A")
                    draw.text((850,135), f'{mem}/30', font=setFont, fill="#4A515A")
                    draw.text((50,440), f'{prev_r}位', font=setFont, fill="#4A515A")
                    draw.text((850,440), f'{next_r}位', font=setFont, fill="#4A515A")
                    
                    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 40)
                    draw.text((500,15), f'{name}', font=setFont, fill="#4A515A")
                    
                    try:
                            
                        img3 = R.img(f'priconne/unit/icon_unit_{chara_id}{st}1.png').open()
                        img3 = img3.resize((160, 160))
                        img.paste(img3, (17,17))            
                    except:
                        pass
                    
                    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 50)
                    #draw.text((270,10), f'--位', font=setFont, fill="#CC9900")
                    
                    if len(goal_list) != 1:
                        
                        
                        img4.paste(img, (0,500*all_num))
                    
                    
                        
                    all_num+=1    
                    
        if len(goal_list) != 1:
            imgq = pic2b64(img4)
            imgq = MessageSegment.image(imgq)
        else:
            imgq = pic2b64(img)
            imgq = MessageSegment.image(imgq)        
        await bot.send(ev,imgq)
    except Exception as e:
        print(e)
        await bot.send(ev,'获取数据时发生错误，请重试')
        pass



chat_list = {}
#留言功能
@sv.on_prefix('会战留言')
async def chat(bot,ev):
    global chat_list
    msg = ev.message.extract_plain_text().strip()
    uid = ev.user_id
    qid = ev.group_id
    if msg == '':
        await bot.send(ev,'你想说些什么呢^^')
    t = int(time.time())
    if qid not in chat_list:
        chat_list[qid] = {
            "uid": [],
            "text": [],
            "time": [],
            "extra": [],
        }    
    
    if len(chat_list[qid]["uid"]) > max_chat_list:   
        del chat_list[qid]["uid"][0]
        del chat_list[qid]["text"][0]
        del chat_list[qid]["time"][0]
    if len(chat_list[qid]["uid"]) <= max_chat_list:
        chat_list[qid]["uid"].append(int(uid))
        chat_list[qid]["text"].append(str(msg))
        chat_list[qid]["time"].append(int(t))

    await bot.send(ev,'已添加留言！')


@sv.on_prefix('会战留言板','留言板')
async def chat_board(bot,ev):
    qid = ev.group_id
    if qid not in chat_list:
        await bot.send(ev,'本群暂时没有留言！')
        return
    else:
        msg = '留言板：\n'
        for i in range(0,len(chat_list[qid]["uid"])):
            time_now = int(time.time())
            time_diff = time_now - chat_list[qid]["time"][i]
            if time_diff <= 60:
                time_diff = '刚刚'
            else:
                time_diff = int(time_diff/60)
                time_diff = f'{time_diff}分钟前'
            nickname = chat_list[qid]["uid"][i]
            try:
                nickname = await bot.get_group_member_info(group_id = qid,user_id = (chat_list[qid]["uid"][i]))
                nickname = nickname['nickname']
            except:
                pass
            chat = chat_list[qid]["text"][i]
            msg += f'[{time_diff}]{nickname}:{chat}\n'
        await bot.send(ev,msg)
        return

@sv.on_fullmatch('清空留言板')
async def clear_chat(bot,ev):
    qid = ev.group_id
    u_priv = priv.get_user_priv(ev)
    if u_priv < sv.manage_priv and acinfo["only_admin"] == 1:
        await bot.send(ev,'权限不足，当前指令仅管理员可用!')
        return
    del chat_list[qid]
    await bot.send(ev,'已清空本群记录')

@sv.on_fullmatch('出刀时段统计')
async def stats1(bot,ev):
    BTime = Image.new("RGBA",(1020,520),'#FFE4C4')
    draw = ImageDraw.Draw(BTime)
    setFont = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 20)
    setFont2 = ImageFont.truetype(img_file+'//pcrcnfont.ttf', 15)    

    time_array = []
    for i in range(0,24):
        draw.text((50 + 40*i ,500), f'{i}', font=setFont, fill="#4A515A")
        time_array.append(0)
    for i in range(1,6):
        draw.text((0, 520 - i*100), f'{i}0', font=setFont, fill="#4A515A")
        draw.line((33, 520 - i*100) + (1000, 520 - i*100), fill='#191970', width=1)

    for line in open(current_folder + "/Output.txt",encoding='utf-8'):
        values = line.split(",")
        if values[0] == 'SL':
            continue
        battle_time = int(values[1])
        time_array[battle_time] += 1

    maxtime = max(time_array)
    overline = False
    linecolor = {
        0: '#808080',
        6: '#9CC5B0',
        12: '#C54730',
        18: '#384B5A'
    }
    for i in range(0,24):
        if time_array[i] >= 50:
            overline = True
        elif time_array[i] == 0:
            continue
        for color in linecolor:
            if i >= color:
                color2 = linecolor[color]
        y_axis = 520 - time_array[i]*10 if overline == False else 20
        y_axis = 500 - time_array[i]*10 if time_array[i] <= 4 else y_axis
        fontcolor = 'black' if overline == False else 'purple'
        if time_array[i] == maxtime:
            draw.line((60 + 40*i, 500) + (60 + 40*i, y_axis-5), fill='#00008B', width=30)
        draw.line((60 + 40*i, 500) + (60 + 40*i, y_axis), fill=color2, width=20)
        draw.text((48 + 40*i, y_axis - 20), f'{(time_array[i])}', font=setFont2, fill=fontcolor)
    draw.line((30, 500) + (1000, 500), fill=128, width=5)
    draw.line((30, 20) + (30, 500), fill=128, width=5)

    img = pic2b64(BTime)
    img = MessageSegment.image(img)        
    await bot.send(ev,img)



def drawjingdutiao(percent,img,boss_num):           #血量百分比进度条，返回一个image对象
    width = 907 
    height = 214
    circlelist = [59,365,671,977,1283]
    # 定义半圆弧形的参数
    center_x2 = 700  # 右侧弧形的中心点x坐标
    center_y = height // 2  # 弧形的中心点y坐标
    radius = height // 2  # 弧形的半径
    start_angle = 270  # 弧形的起始角度（逆时针方向）
    end_angle = 90  # 弧形的结束角度（逆时针方向）
    bg_image = img
    final = Image.new("RGBA", bg_image.size)  
    if percent<1:
        image = Image.new("RGBA", (width, height))
        # 创建绘制对象
        draw = ImageDraw.Draw(image)
        center_x1 = (percent)*7*100  # 左侧弧形的中心点x坐标
        # 绘制左侧半圆弧形
        draw.arc((center_x1 - radius, center_y - radius, center_x1 + radius, center_y + radius), start_angle, end_angle, fill=(255, 255, 255, 0))
        # 绘制右侧半圆弧形
        draw.arc((center_x2 - radius, center_y - radius, center_x2 + radius, center_y + radius), start_angle, end_angle, fill=(255, 255, 255, 100))
        # 绘制连接的直线
        line_start = (center_x1, center_y - radius)  # 连接直线的起始点坐标
        line_end = (center_x2, center_y - radius)  # 连接直线的结束点坐标
        draw.line((line_start, line_end), fill=(255, 255, 255, 100))
        line_start = (center_x1, center_y + radius)  # 连接直线的起始点坐标
        line_end = (center_x2, center_y + radius)  # 连接直线的结束点坐标
        draw.line((line_start, line_end), fill=(255, 255, 255, 100))
        ImageDraw.floodfill(image, (center_x2-1, center_y + radius-1), value=(239, 246, 252,190), border=None, thresh=0)
        r, g, b, a = image.split() 
        final.paste(image, (394, circlelist[boss_num-1]))
    final = Image.alpha_composite(bg_image, final)   #paste不能用于半透明的东西
    return final    


def line_break(line):
    LINE_CHAR_COUNT = 15*2  # 每行字符数：15个中文字符(=30)    #####这段是切割长文本，用于drawtext换行
    TABLE_WIDTH = 4
    ret = ''
    width = 0
    for c in line:
        if len(c.encode('utf8')) == 3:  # 中文
            if LINE_CHAR_COUNT == width + 1:  # 剩余位置不够一个汉字
                width = 2
                ret += '\n' + c
            else: # 中文宽度加2，注意换行边界
                width += 2
                ret += c
        else:
            if c == '\t':
                space_c = TABLE_WIDTH - width % TABLE_WIDTH  # 已有长度对TABLE_WIDTH取余
                ret += ' ' * space_c
                width += space_c
            elif c == '\n':
                width = 0
                ret += c
            else:
                width += 1
                ret += c
        if width >= LINE_CHAR_COUNT:
            ret += '\n'
            width = 0
    if ret.endswith('\n'):
        return ret
    return ret + '\n'


@sv.on_prefix('会战绑定')#不会写这个，先用着等会改
async def binduid(bot,ev):
    uid = ev.message.extract_plain_text().strip()
    gid = str(ev.group_id)
    qid = str(ev.user_id)
    with open(join(curpath, 'bind.json')) as fp:
        binds = load(fp)
    if gid not in binds:
        binds[gid] = {}
    if qid not in binds[gid]:
        user_bind = {
            "uid": int(uid),
            "qid": int(qid)
        }
        binds[gid][qid] = user_bind

    with open(join(curpath, 'bind.json'), mode="w") as fp:
        json.dump(binds, fp, indent=4, ensure_ascii=False)
    await bot.send(ev,'绑定完成')




@sv.on_prefix(f'修改星级')#修改工具号助战星级
async def change_star(bot,ev):
    u_priv = priv.get_user_priv(ev)
    if u_priv < sv.manage_priv:
        await bot.send(ev,'权限不足，当前指令仅管理员可用!')
        return
        
    param = ev.message.extract_plain_text().strip()
    param = param.split(' ')
    try:
        ms = param[0]
        st = param[1]
        await verify()
        cha_fin = 0
        for CHARA in CHARA_NAME:
            cha = CHARA
            if ms in CHARA_NAME[cha]:
                print(ms)
                cha_fin = cha
                unis = CHARA_NAME[cha][0]
                await bot.send(ev,f'已找到{unis},正在尝试更改星级...')  #角色存在
                break
    
        await verify()
        unit_id = int(str(cha_fin) + '01')
        res = await client.callapi('/unit/change_rarity', {'change_rarity_unit_list': [{'unit_id': unit_id, 'battle_rarity': st}]})
        await bot.send(ev,f'{unis}已经更改星级至{st}星')
    except:
        await bot.send(ev,f'发生了错误！可能是:参数出现错误|星级不可更改|没有该角色!')
        pass

@sv.on_prefix(f'修改助战')
async def clan_uni(bot,ev):
    u_priv = priv.get_user_priv(ev)
    if u_priv < sv.manage_priv:
        await bot.send(ev,'权限不足，当前指令仅管理员可用!')
        return
    ms = ev.message.extract_plain_text().strip()
    cha_fin = 0
    for CHARA in CHARA_NAME:
        cha = CHARA
        if ms in CHARA_NAME[cha]:
            print(ms)
            cha_fin = cha
            unis = CHARA_NAME[cha][0]
            await bot.send(ev,f'已找到{unis},正在尝试挂至助战...')  #角色存在
            break

    await verify()
    prof = await client.callapi('/support_unit/get_setting', {})
    u1 = prof['clan_support_units']
    
    for uni in u1:
        unit_id = int(str(uni['unit_id'])[:-2])
        if cha_fin == unit_id:
            await bot.send(ev,f'操作失败，角色已经在助战中!')   #已经在助战中
            return
    
    num = 0
    for uni in u1:
        if num >= 2:
            unit_time = uni['support_start_time']
            now = time.time()
            diff = int(now - unit_time)
            print(diff)
            if int(diff) > 1800:
                unit_id = int(str(cha_fin) + '01')
                try:
                    info = await client.callapi('/support_unit/change_setting', {'support_type': 1, 'position': num+1, 'action': 2, 'unit_id': unit_id})
                    time.sleep(3)
                    info2 = await client.callapi('/support_unit/change_setting', {'support_type': 1, 'position': num+1, 'action': 1, 'unit_id': unit_id})
                    msg = f'已将{unis}挂至{num-1}号助战位中'
                    await bot.send(ev,msg)
                except:
                    await bot.send(ev,'操作失败')
                    pass
                return 
        num += 1

        #print(CHARA)
    await bot.send(ev,'发生了错误！可能是：没有找到相应角色|角色名输入错误|两个助战位都未超过30分钟!')

@sv.on_fullmatch(f'会战助战')
async def clan_un(bot,ev):
    await verify()
    msg = ''
    prof = await client.callapi('/support_unit/get_setting', {})
    u1 = prof['clan_support_units']
    num = 0
    for uni in u1:
        if num >= 2:
            unit_id = int(str(uni['unit_id'])[:-2])
            unit_time = uni['support_start_time']
            if unit_id in CHARA_NAME:
                unit_id = CHARA_NAME[unit_id][0]
            now = time.time()
            diff = int(now - unit_time)
            if diff > 1800:
                replace = '可替换'
            else:
                replace = '不能替换'
            f_t = time.strftime("%H时%M分%S秒", gmtime(diff))
            msg += f'{unit_id}正在助战{f_t}s    {replace}\n'
            
        num += 1

    await bot.send(ev,msg)
