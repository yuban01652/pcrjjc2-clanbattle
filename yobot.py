import datetime
import aiohttp
import asyncio
import traceback
import math
import nonebot
import hoshino
from typing import Tuple, Union

try:
    from ..yobot_remix.yobot_remix.src.client.ybplugins.clan_battle import \
        ClanBattle
except:
    pass

__all__ = [
    'is_auto_report_enable',
    'format_yobot_report_message',
    'set_yobot_state',
    'get_embedded_yobot_ClanBattle_instance',
    'report_process',
    'get_unknown_members_report',
    ]

### 缝合模式功能

#获取插件版yobot的ClanBattle实例
def get_embedded_yobot_ClanBattle_instance() -> ClanBattle:
    plugins = nonebot.get_loaded_plugins()
    for plugin in plugins:
        m = str(plugin.module)
        m = m.replace('\\\\', '/')
        m = m.replace('\\', '/')
        if 'modules/yobot_remix/yobot_remix/__init__.py' in m:
            passive_list = []
            try:
                passive_list = plugin.module.src.client.nonebot_plugin.bot.plug_passive
            except:
                continue
            for module in passive_list:
                if type(module).__name__ == 'ClanBattle':
                    return module
    return None

#插件版yobot报刀
def embedded_yobot_add_challenge(group_id: str, challenge):
    msg = ''
    clanbattle = get_embedded_yobot_ClanBattle_instance()
    if not clanbattle:
        msg = '无法获取ClanBattle实例,请检查yobot部署.'
        return 1, msg
    defeat = False
    if challenge['kill'] == 1:
        defeat = True
    is_continue = False
    if challenge['reimburse'] == 1:
        is_continue = True
    previous_day = False
    dt = datetime.datetime.fromtimestamp(challenge['datetime'])
    if get_pcr_days_from(dt) > 0:
        previous_day = True
    try:
        result = clanbattle.challenge(int(group_id), challenge['qqid'], defeat, challenge['damage'], None, is_continue=is_continue, boss_num=str(challenge['boss'] + 1), previous_day=previous_day)
        msg = 'yobot新增出刀记录:\n' + str(result)
    except Exception as e:
        msg = 'yobot添加出刀记录失败:\n' + str(e)
        if '您没有补偿刀' in str(e):
            return 2, msg
        return 1, msg
    return 0, msg

### 通用功能

def get_pcr_days_from(dt):
    pcr_today = datetime.datetime.now()
    #pcr_today = datetime.datetime(2020,8,25,20,0)
    if pcr_today.hour < 5:  #众所周知,兰德索尔的一天从凌晨5点开始
        pcr_today -= datetime.timedelta(days=1)
    pcr_today = pcr_today.replace(hour=5, minute=0, second=0, microsecond=0)
    return math.ceil((pcr_today - dt) / datetime.timedelta(days=1))

def check_challenge_equal(challenge: dict, yobot_challenge: dict):
    if challenge['qqid'] != yobot_challenge['qqid']:
        return False
    if challenge['lap_num'] != yobot_challenge['cycle']:
        return False
    if challenge['boss'] + 1 != yobot_challenge['boss_num']:
        return False
    if abs(challenge['damage'] - yobot_challenge['damage']) < 5: #忽略5以内偏差,避免尾数问题
        return True
    if challenge['kill'] == 1 and yobot_challenge['health_remain'] == 0 \
        and abs(challenge['damage'] - yobot_challenge['damage']) < 10000:   #尾刀容许偏差1w
        return True
    return False

#获取yobot最后一条出刀记录
async def get_yobot_challenges(group_id):
    yobot_challenges = []

    clanbattle = get_embedded_yobot_ClanBattle_instance()
    if not clanbattle:
        return 1, 'get_yobot_challenges: 无法获取ClanBattle实例'
    yobot_challenges = clanbattle.get_report(group_id, None, None, None)

    return 0, yobot_challenges

#等待yobot同步当前出刀记录
#ret: 0 成功 1 出错 2 超时
# 由于yobot内部get_report有时间缓存机制, 获取到最新记录最多要等待10秒
async def wait_yobot_sync(group_id: str, challenge: dict):
    group_id = str(group_id)
    for _ in range(10):
        await asyncio.sleep(3)
        ret, yobot_challenges = await get_yobot_challenges(group_id)
        if ret != 0:
            return 1, 'wait_for_challenge_sync:' + yobot_challenges
        if len(yobot_challenges) == 0:
            continue
        #对比本条记录和Yobot最新记录的qq,伤害,boss,周目,一致则认为同步成功
        #对于尾刀,允许一定的误差(暂定1w内)
        for yobot_challenge in yobot_challenges:
            if check_challenge_equal(challenge, yobot_challenge):
                return 0, 'ok'

    yobot_challenge = {}
    if len(yobot_challenges) > 0:
        yobot_challenge = yobot_challenges[-1]
    msg = f'最新上报记录匹配失败,请手动修正出刀数据.\n本次上报出刀数据:\n{format_challenge(challenge)}yobot最近出刀数据:\n{format_yobot_challenge(yobot_challenge)}'
    return 2, msg

async def generate_name2qq(group_id: str, yobot_members = None) -> Tuple[int, str]:
    name2qq = {}
    yobot_members = []
    if not yobot_members:
        #从yobot获取成员表
        clanbattle = get_embedded_yobot_ClanBattle_instance()
        if not clanbattle:
            return 1, '无法获取ClanBattle实例,请检查yobot部署情况.'
        yobot_members = clanbattle.get_member_list(int(group_id))

    #优先级: 插件本地members -> yobot members -> 群成员列表
    #生成昵称-QQ对应表 
    for item in yobot_members:
        if item['nickname'] not in name2qq:
            name2qq[item['nickname']] = item['qqid']

    bot = hoshino.get_bot()
    mlist = await bot.get_group_member_list(group_id=int(group_id))
    for m in mlist:
        name = m['card'] or m['nickname']
        if name not in name2qq:
            name2qq[name] =  m['user_id']
    return 0, name2qq


async def report_process(bot, group_id: str, item):
    if 'finish' in item.keys():
        ret, result = await wait_yobot_sync(group_id, item)
        if ret != 0: #同步失败
            await bot.send_group_msg(group_id=int(group_id), message = result)
            return 1
    else:
        ret, result = embedded_yobot_add_challenge(group_id, item)
        if ret == 2:
            item['reimburse'] = 0
            ret, result = embedded_yobot_add_challenge(group_id, item)
        await bot.send_group_msg(group_id=int(group_id), message = result)
        if ret != 0:
            return 1
    return 0
