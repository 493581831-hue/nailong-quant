"""
数据获取模块 — 多层数据源

数据源架构:
  1. 实时行情(最新价/涨跌幅): Sina API (主) -> Tencent API (备)
  2. 历史日K线: Tencent API (主, HTTP稳定) -> baostock (备, 本地数据)
  3. 模拟数据: 内置生成器(离线测试)

Sina API:    https://hq.sinajs.cn/list=sh600519
Tencent API: http://web.ifzq.gtimg.cn/appstock/app/fqkline/get (K线)
             http://qt.gtimg.cn/q=sh600519 (行情)
baostock:    本地证券数据服务器 (备用)
"""

import pandas as pd
import streamlit as st
import time
import random
import numpy as np
import urllib.request
import urllib.parse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

try:
    import baostock as bs
except Exception:  # 允许仅使用腾讯/Sina/模拟数据运行
    bs = None


# ═══════════════════════════════════════════════════════════
#  Sina / Tencent 实时行情
# ═══════════════════════════════════════════════════════════

_SINA_HEADERS = {'Referer': 'https://finance.sina.com.cn', 'Accept-Encoding': 'identity'}
_TENCENT_HEADERS = {'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'identity'}


def _code_to_sc(code):
    """600519 -> sh600519, 000001 -> sz000001"""
    code = str(code).strip().zfill(6)
    if code.startswith('6') or code.startswith('5'):
        return 'sh' + code
    return 'sz' + code


def get_realtime_quote(code: str) -> dict:
    """实时行情快照: Sina主 -> Tencent备"""
    result = _get_rt_sina(code)
    if result:
        return result
    return _get_rt_tencent(code)


def _get_rt_sina(code):
    try:
        sc = _code_to_sc(code)
        url = f'https://hq.sinajs.cn/list={sc}'
        req = urllib.request.Request(url, headers=_SINA_HEADERS)
        r = urllib.request.urlopen(req, timeout=10)
        text = r.read().decode('gbk')
        data = text.split('"')[1].split(',')
        if len(data) >= 32:
            return {
                'name': data[0],
                'open': float(data[1]) if data[1] else 0,
                'prev_close': float(data[2]) if data[2] else 0,
                'price': float(data[3]) if data[3] else 0,
                'high': float(data[4]) if data[4] else 0,
                'low': float(data[5]) if data[5] else 0,
                'volume': int(float(data[8])) if data[8] else 0,
                'amount': float(data[9]) if data[9] else 0,
                'change_pct': round(
                    (float(data[3]) - float(data[2])) / float(data[2]) * 100, 2
                ) if float(data[2]) > 0 else 0,
            }
    except Exception:
        pass
    return {}


def _get_rt_tencent(code):
    try:
        sc = _code_to_sc(code)
        url = f'http://qt.gtimg.cn/q={sc}'
        req = urllib.request.Request(url, headers=_TENCENT_HEADERS)
        r = urllib.request.urlopen(req, timeout=10)
        text = r.read().decode('gbk')
        data = text.split('"')[1].split('~')
        if len(data) >= 40:
            return {
                'name': data[1],
                'code': data[2],
                'price': float(data[3]) if data[3] else 0,
                'prev_close': float(data[4]) if data[4] else 0,
                'open': float(data[5]) if data[5] else 0,
                'volume': int(data[6]) if data[6] else 0,
                'high': float(data[33]) if len(data) > 33 and data[33] else 0,
                'low': float(data[34]) if len(data) > 34 and data[34] else 0,
                'amount': float(data[37]) if len(data) > 37 and data[37] else 0,
                'change_pct': float(data[32]) if len(data) > 32 and data[32] else 0,
            }
    except Exception:
        pass
    return {}


def get_realtime_batch(codes: list, max_workers=6) -> dict:
    """批量获取实时行情"""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        fut_map = {ex.submit(get_realtime_quote, c): c for c in codes}
        for fut in as_completed(fut_map):
            c = fut_map[fut]
            try:
                r = fut.result()
                if r:
                    results[c] = r
            except:
                pass
    return results


def check_network() -> bool:
    """检测至少一条真实行情链路，避免把单一供应商故障误报为离线。"""
    try:
        result = _get_rt_sina('600519')
        if result and result.get('price', 0) > 0:
            return True
        result = _get_rt_tencent('600519')
        if result and result.get('price', 0) > 0:
            return True
        end = pd.Timestamp.today().normalize()
        start = end - pd.Timedelta(days=20)
        history = _fetch_tencent_kline('600519', start, end, 'qfq')
        return history is not None and len(history) > 0
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════
#  日K线数据 — Tencent API (主) + baostock (备)
# ═══════════════════════════════════════════════════════════

def _fetch_tencent_kline(code, start_date=None, end_date=None, adjust="qfq", limit=500):
    """
    Tencent K-line API (HTTP, 稳定可靠)
    API: http://web.ifzq.gtimg.cn/appstock/app/fqkline/get
    返回格式: [日期, 开盘, 收盘, 最高, 最低, 成交量(手)]
    """
    try:
        sc = _code_to_sc(code)
        adj_map = {'qfq': 'qfq', 'hfq': 'hfq', '': ''}
        adj_param = adj_map.get(adjust, 'qfq')
        # Tencent caps a single response at roughly 640 trading days. Split
        # explicit history requests into two-calendar-year windows so an old
        # start date is not silently truncated to the latest ~500 rows.
        if start_date and end_date:
            start_ts, end_ts = pd.Timestamp(start_date), pd.Timestamp(end_date)
            requests_to_make = []
            year = start_ts.year
            while year <= end_ts.year:
                chunk_start = max(start_ts, pd.Timestamp(year=year, month=1, day=1))
                chunk_end = min(end_ts, pd.Timestamp(year=min(year + 1, end_ts.year), month=12, day=31))
                requests_to_make.append((chunk_start.strftime('%Y-%m-%d'), chunk_end.strftime('%Y-%m-%d')))
                year += 2
        else:
            requests_to_make = [(None, None)]

        klines = []
        for chunk_start, chunk_end in requests_to_make:
            if chunk_start:
                param = f'{sc},day,{chunk_start},{chunk_end},640,{adj_param}'
            else:
                param = f'{sc},day,,,{limit},{adj_param}'
            url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=' + urllib.parse.quote(param)
            req = urllib.request.Request(url, headers=_TENCENT_HEADERS)
            r = urllib.request.urlopen(req, timeout=15)
            data = json.loads(r.read())
            d = data.get('data', {})
            stock_key = sc if sc in d else next(iter(d), sc)
            stock_data = d.get(stock_key, {})
            kline_key = adj_param + 'day' if adj_param else 'day'
            klines.extend(stock_data.get(kline_key, stock_data.get('day', [])))
        if not klines:
            return pd.DataFrame()

        rows = []
        for item in klines:
            rows.append({
                'date': pd.Timestamp(item[0]),
                'open': float(item[1]),
                'close': float(item[2]),
                'high': float(item[3]),
                'low': float(item[4]),
                'volume': int(float(item[5])) * 100,  # 手转股
            })
        df = pd.DataFrame(rows)
        df = df.drop_duplicates(subset='date').sort_values('date').reset_index(drop=True)

        if start_date:
            df = df[df['date'] >= pd.Timestamp(start_date)]
        if end_date:
            df = df[df['date'] <= pd.Timestamp(end_date)]

        return df.reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
#  baostock 连接管理 (备用)
# ═══════════════════════════════════════════════════════════

_BS_LOGIN = False


def _ensure_bs_login():
    global _BS_LOGIN
    if bs is None:
        raise ImportError("baostock 未安装；已跳过 baostock 备用数据源")
    if not _BS_LOGIN:
        lg = bs.login()
        if lg.error_code == "0":
            _BS_LOGIN = True
        else:
            raise ConnectionError(f"baostock登录失败: {lg.error_msg}")
    return _BS_LOGIN


def _map_symbol(code: str) -> str:
    code = str(code).strip().zfill(6)
    if code.startswith("6"):
        return f"sh.{code}"
    elif code.startswith("0") or code.startswith("3"):
        return f"sz.{code}"
    elif code.startswith("5"):
        return f"sh.{code}"
    else:
        return f"sz.{code}"


def _map_adjust(adjust: str) -> str:
    return {"qfq": "2", "hfq": "3", "": "1"}.get(adjust, "2")


def _bs_to_df(rs) -> pd.DataFrame:
    if rs is None:
        return pd.DataFrame()
    if rs.error_code != "0":
        return pd.DataFrame()
    data_list = []
    while rs.next():
        data_list.append(rs.get_row_data())
    if not data_list:
        return pd.DataFrame()
    cols = rs.fields
    df = pd.DataFrame(data_list, columns=cols)
    num_cols = [c for c in df.columns if c not in ("date", "code")]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    col_map = {'turn': 'turnover', 'pctChg': 'pct_chg', 'tradestatus': 'trade_status'}
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    if 'volume' in df.columns:
        df['volume'] = df['volume'].fillna(0).astype(np.int64)
    if 'amount' in df.columns:
        df['amount'] = df['amount'].fillna(0).astype(np.int64)
    return df


def _fetch_bs(code, start_date, end_date, adjust="qfq", max_retries=2):
    """baostock获取日K线 (备用)"""
    for attempt in range(max_retries):
        try:
            _ensure_bs_login()
            bs_code = _map_symbol(code)
            adj_flag = _map_adjust(adjust)
            fields = "date,open,close,high,low,volume,amount"
            rs = bs.query_history_k_data_plus(
                bs_code, fields,
                start_date=start_date, end_date=end_date,
                frequency="d", adjustflag=adj_flag,
            )
            if rs is None:
                continue
            if rs.error_code != "0":
                continue
            df = _bs_to_df(rs)
            if df is not None and len(df) > 0:
                df["date"] = pd.to_datetime(df["date"])
                df = df.sort_values("date").reset_index(drop=True)
                keep = ["date", "open", "close", "high", "low", "volume", "amount"]
                keep = [c for c in keep if c in df.columns]
                return df[keep]
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(0.5 + random.random())
    return pd.DataFrame()


def _fetch_kline(code, start_date, end_date, adjust="qfq"):
    """
    获取日K线 (主: 腾讯API -> 备: baostock)
    """
    df = _fetch_tencent_kline(code, start_date, end_date, adjust)
    if df is not None and len(df) > 0:
        return df
    return _fetch_bs(code, start_date, end_date, adjust)


@st.cache_data(ttl=3600, show_spinner=False)
def get_daily_data(code, start_date, end_date, adjust="qfq"):
    """获取个股日K线数据"""
    try:
        return _fetch_kline(code, start_date, end_date, adjust)
    except Exception:
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
#  股票列表 (内置)
# ═══════════════════════════════════════════════════════════

A_STOCK_LIST_MAIN = [
    ("600519", "贵州茅台"), ("000858", "五粮液"), ("000568", "泸州老窖"),
    ("002304", "洋河股份"), ("600809", "山西汾酒"), ("000799", "酒鬼酒"),
    ("603369", "今世缘"), ("600559", "老白干酒"), ("002568", "百润股份"),
    ("600132", "重庆啤酒"), ("000729", "燕京啤酒"), ("600600", "青岛啤酒"),
    ("600036", "招商银行"), ("601398", "工商银行"), ("601939", "建设银行"),
    ("601288", "农业银行"), ("601988", "中国银行"), ("601328", "交通银行"),
    ("600016", "民生银行"), ("600000", "浦发银行"), ("601166", "兴业银行"),
    ("000001", "平安银行"), ("002142", "宁波银行"), ("601009", "南京银行"),
    ("600015", "华夏银行"), ("601818", "光大银行"), ("601229", "上海银行"),
    ("601318", "中国平安"), ("601628", "中国人寿"), ("601601", "中国太保"),
    ("601336", "新华保险"), ("600030", "中信证券"), ("601688", "华泰证券"),
    ("600837", "海通证券"), ("601211", "国泰君安"), ("000776", "广发证券"),
    ("601066", "中信建投"), ("600999", "招商证券"), ("300059", "东方财富"),
    ("000002", "万科A"), ("600048", "保利发展"), ("001979", "招商蛇口"),
    ("600383", "金地集团"), ("000069", "华侨城A"),
    ("000333", "美的集团"), ("000651", "格力电器"), ("600690", "海尔智家"),
    ("000100", "TCL科技"), ("002050", "三花智控"),
    ("600276", "恒瑞医药"), ("300760", "迈瑞医疗"), ("300015", "爱尔眼科"),
    ("603259", "药明康德"), ("000538", "云南白药"), ("600196", "复星医药"),
    ("002007", "华兰生物"), ("300122", "智飞生物"), ("600763", "通策医疗"),
    ("300347", "泰格医药"), ("002821", "凯莱英"), ("603392", "万泰生物"),
    ("600085", "同仁堂"), ("000423", "东阿阿胶"), ("600436", "片仔癀"),
    ("002594", "比亚迪"), ("000625", "长安汽车"), ("600104", "上汽集团"),
    ("600733", "北汽蓝谷"), ("300750", "宁德时代"), ("002074", "国轩高科"),
    ("300014", "亿纬锂能"), ("002812", "恩捷股份"), ("300450", "先导智能"),
    ("002460", "赣锋锂业"), ("002466", "天齐锂业"), ("300124", "汇川技术"),
    ("002415", "海康威视"), ("002236", "大华股份"), ("603501", "韦尔股份"),
    ("002371", "北方华创"), ("688981", "中芯国际"), ("603986", "兆易创新"),
    ("600703", "三安光电"), ("002049", "紫光国微"), ("300661", "圣邦股份"),
    ("688012", "中微公司"), ("600745", "闻泰科技"), ("002185", "华天科技"),
    ("300782", "卓胜微"), ("688008", "澜起科技"),
    ("000977", "浪潮信息"), ("002230", "科大讯飞"), ("688111", "金山办公"),
    ("600570", "恒生电子"), ("002410", "广联达"), ("300454", "深信服"),
    ("300033", "同花顺"), ("300624", "万兴科技"),
    ("600941", "中国移动"), ("601728", "中国电信"), ("600050", "中国联通"),
    ("000063", "中兴通讯"), ("300308", "中际旭创"),
    ("002624", "完美世界"), ("300413", "芒果超媒"), ("603444", "吉比特"),
    ("002555", "三七互娱"), ("300418", "昆仑万维"), ("002602", "世纪华通"),
    ("600887", "伊利股份"), ("603288", "海天味业"), ("002714", "牧原股份"),
    ("000895", "双汇发展"), ("002557", "洽洽食品"), ("603345", "安井食品"),
    ("601012", "隆基绿能"), ("600438", "通威股份"), ("688599", "天合光能"),
    ("002459", "晶澳科技"), ("300274", "阳光电源"), ("601615", "明阳智能"),
    ("600089", "特变电工"), ("300751", "迈为股份"), ("688390", "固德威"),
    ("600900", "长江电力"), ("600886", "国投电力"), ("600011", "华能国际"),
    ("600905", "三峡能源"), ("601985", "中国核电"),
    ("601088", "中国神华"), ("600188", "兖矿能源"), ("601225", "陕西煤业"),
    ("601899", "紫金矿业"), ("600547", "山东黄金"), ("002155", "湖南黄金"),
    ("000831", "中国稀土"), ("600111", "北方稀土"),
    ("600019", "宝钢股份"), ("000932", "华菱钢铁"),
    ("600309", "万华化学"), ("002601", "龙佰集团"),
    ("600150", "中国船舶"), ("600893", "航发动力"), ("600760", "中航沈飞"),
    ("002179", "中航光电"), ("000768", "中航西飞"),
    ("601668", "中国建筑"), ("601390", "中国中铁"), ("601186", "中国铁建"),
    ("600585", "海螺水泥"), ("002271", "东方雨虹"),
    ("601919", "中远海控"), ("002352", "顺丰控股"), ("601111", "中国国航"),
    ("600009", "上海机场"),
    ("002475", "立讯精密"), ("601138", "工业富联"), ("000725", "京东方A"),
    ("603659", "璞泰来"), ("002920", "德赛西威"),
    ("601857", "中国石油"), ("600028", "中国石化"), ("600346", "恒力石化"),
    ("688256", "寒武纪"),
]


@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_list():
    """获取当前可交易的沪深全市场 A 股，失败时明确降级到内置样本池。"""
    try:
        _ensure_bs_login()
        rs = bs.query_stock_basic()
        if rs is None or rs.error_code != "0":
            raise RuntimeError("baostock 证券列表查询失败")
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        raw = pd.DataFrame(rows, columns=rs.fields)
        if raw.empty:
            raise RuntimeError("baostock 返回空证券列表")

        raw = raw[(raw["type"] == "1") & (raw["status"] == "1")].copy()
        raw["market"] = raw["code"].str.split(".").str[0]
        raw["plain_code"] = raw["code"].str.split(".").str[-1].str.zfill(6)
        sh_a = (raw["market"] == "sh") & raw["plain_code"].str.startswith(
            ("600", "601", "603", "605", "688", "689")
        )
        sz_a = (raw["market"] == "sz") & raw["plain_code"].str.startswith(
            ("000", "001", "002", "003", "300", "301")
        )
        raw = raw[sh_a | sz_a].copy()
        raw["board"] = np.select(
            [
                raw["plain_code"].str.startswith(("688", "689")),
                raw["plain_code"].str.startswith(("300", "301")),
                raw["market"].eq("sh"),
            ],
            ["科创板", "创业板", "沪市主板"],
            default="深市主板",
        )
        # Keep the BaoStock-qualified symbol (for example ``sh.600519``)
        # out of the public frame before renaming. Otherwise pandas sees both
        # it and ``plain_code`` as a column named ``code``.
        result = raw[
            ["plain_code", "code_name", "market", "board", "ipoDate", "outDate"]
        ].rename(columns={"plain_code": "code", "code_name": "name"})
        result["is_st"] = result["name"].str.contains(r"ST|退", case=False, regex=True, na=False)
        result = result.drop_duplicates("code").sort_values("code").reset_index(drop=True)
        result.attrs["source"] = "BaoStock 沪深全市场"
        result.attrs["is_full_market"] = True
        return result
    except Exception as exc:
        result = pd.DataFrame(A_STOCK_LIST_MAIN, columns=["code", "name"])
        result = result.drop_duplicates(subset="code").reset_index(drop=True)
        result["code"] = result["code"].astype(str).str.zfill(6)
        result["market"] = np.where(result["code"].str.startswith("6"), "sh", "sz")
        result["board"] = "内置样本"
        result["is_st"] = False
        result.attrs["source"] = f"内置样本池（全市场源不可用: {exc}）"
        result.attrs["is_full_market"] = False
        return result


@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_list_extended():
    return get_stock_list()


@st.cache_data(ttl=21600, show_spinner=False)
def get_value_stock_pool(limit: int = 500) -> pd.DataFrame:
    """Return a compact, investable research universe for signal screening.

    The primary universe is the latest CSI A500 constituent set (000510).
    Compared with truncating the market by code, this gives the screener a
    liquid, industry-representative 500-stock base selected by a published
    index methodology. If the constituent endpoint is unavailable, the pool
    falls back to a union of CSI 300 and CSI 500 constituents from BaoStock.
    """
    limit = max(1, min(500, int(limit)))
    primary_error = None

    try:
        import akshare as ak

        raw = ak.index_stock_cons_csindex(symbol="000510")
        required = {"成分券代码", "成分券名称"}
        if raw is None or raw.empty or not required.issubset(raw.columns):
            raise RuntimeError("中证 A500 成分股接口返回空数据")

        result = raw.rename(columns={"成分券代码": "code", "成分券名称": "name"}).copy()
        result["code"] = result["code"].astype(str).str.extract(r"(\d{6})", expand=False)
        result = result.dropna(subset=["code", "name"]).drop_duplicates("code")
        result["is_st"] = result["name"].str.contains(r"ST|退", case=False, regex=True, na=False)
        result = result[~result["is_st"]].head(limit).copy()
        if len(result) < limit:
            raise RuntimeError(f"中证 A500 有效成分不足 {limit} 只")

        full_market = get_stock_list()
        metadata_columns = [
            column for column in ["code", "market", "board", "ipoDate", "outDate"]
            if column in full_market.columns
        ]
        if metadata_columns:
            result = result.merge(
                full_market[metadata_columns].drop_duplicates("code"),
                on="code", how="left",
            )
        inferred_market = pd.Series(
            np.where(result["code"].str.startswith("6"), "sh", "sz"),
            index=result.index,
        )
        if "market" not in result.columns:
            result["market"] = inferred_market
        else:
            result["market"] = result["market"].fillna(inferred_market)
        inferred_board = pd.Series(
            np.select(
                [
                    result["code"].str.startswith(("688", "689")),
                    result["code"].str.startswith(("300", "301", "302")),
                    result["code"].str.startswith("6"),
                ],
                ["科创板", "创业板", "沪市主板"],
                default="深市主板",
            ),
            index=result.index,
        )
        if "board" not in result.columns:
            result["board"] = inferred_board
        else:
            result["board"] = result["board"].fillna(inferred_board)

        as_of = ""
        if "日期" in raw.columns:
            dates = pd.to_datetime(raw["日期"], errors="coerce").dropna()
            if not dates.empty:
                as_of = dates.max().strftime("%Y-%m-%d")
        keep = [
            column for column in ["code", "name", "market", "board", "ipoDate", "outDate", "is_st"]
            if column in result.columns
        ]
        result = result[keep].reset_index(drop=True)
        result.attrs["source"] = "中证指数 / 中证 A500（000510）"
        result.attrs["as_of"] = as_of
        result.attrs["method"] = "市值代表性·流动性·行业均衡的指数成分池"
        result.attrs["is_fallback"] = False
        return result
    except Exception as exc:
        primary_error = str(exc)

    try:
        _ensure_bs_login()
        frames = []
        for label, query in [("沪深300", bs.query_hs300_stocks), ("中证500", bs.query_zz500_stocks)]:
            rs = query()
            if rs is None or rs.error_code != "0":
                continue
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            if rows:
                frame = pd.DataFrame(rows, columns=rs.fields)
                frame["index_source"] = label
                frames.append(frame)
        if not frames:
            raise RuntimeError("BaoStock 宽基成分股返回空数据")

        raw = pd.concat(frames, ignore_index=True)
        result = raw.rename(columns={"code_name": "name", "updateDate": "update_date"})
        result["code"] = result["code"].astype(str).str.split(".").str[-1].str.zfill(6)
        result = result.drop_duplicates("code").head(limit).copy()
        result["market"] = np.where(result["code"].str.startswith("6"), "sh", "sz")
        result["board"] = result["index_source"]
        result["is_st"] = result["name"].str.contains(r"ST|退", case=False, regex=True, na=False)
        result = result[~result["is_st"]].reset_index(drop=True)
        if len(result) < limit:
            supplement = get_stock_list()
            supplement = supplement[~supplement["code"].isin(result["code"])].copy()
            if "is_st" in supplement.columns:
                supplement = supplement[~supplement["is_st"]]
            needed = limit - len(result)
            supplement = supplement.head(needed)
            result = pd.concat([result, supplement], ignore_index=True, sort=False)

        result = result.head(limit).reset_index(drop=True)
        as_of = str(raw["update_date"].max()) if "update_date" in raw.columns else ""
        result.attrs["source"] = "BaoStock 沪深300 + 中证500 备用池"
        result.attrs["as_of"] = as_of
        result.attrs["method"] = "宽基指数成分优先的 500 只备用池"
        result.attrs["is_fallback"] = True
        result.attrs["primary_error"] = primary_error
        return result
    except Exception as fallback_exc:
        result = get_stock_list().copy()
        if "is_st" in result.columns:
            result = result[~result["is_st"]]
        result = result.head(limit).reset_index(drop=True)
        result.attrs["source"] = f"全市场顺序备用池（{fallback_exc}）"
        result.attrs["as_of"] = ""
        result.attrs["method"] = "数据源异常时的临时降级"
        result.attrs["is_fallback"] = True
        result.attrs["primary_error"] = primary_error
        return result


# ═══════════════════════════════════════════════════════════
#  指数数据 (Tencent API)
# ═══════════════════════════════════════════════════════════

_INDEX_MAP = {
    "000300": ("sh.000300", "沪深300"),
    "000001": ("sh.000001", "上证综指"),
    "399001": ("sz.399001", "深证成指"),
    "399006": ("sz.399006", "创业板指"),
    "000016": ("sh.000016", "上证50"),
    "000688": ("sh.000688", "科创50"),
}


@st.cache_data(ttl=86400, show_spinner=False)
def get_index_data(start_date, end_date, index_code="000300") -> pd.DataFrame:
    """获取市场指数数据 (Tencent API -> baostock)"""
    if index_code not in _INDEX_MAP:
        return pd.DataFrame()
    sc, _ = _INDEX_MAP[index_code]

    # 主: Tencent K-line API
    try:
        url = f'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sc},day,,,500,'
        req = urllib.request.Request(url, headers=_TENCENT_HEADERS)
        r = urllib.request.urlopen(req, timeout=15)
        data = json.loads(r.read())
        d = data.get('data', {})
        stock_key = sc
        if stock_key not in d:
            for k in d:
                stock_key = k
                break
        stock_data = d.get(stock_key, {})
        klines = stock_data.get('day', [])
        if klines:
            rows = [{
                'date': pd.Timestamp(item[0]),
                'open': float(item[1]),
                'close': float(item[2]),
                'high': float(item[3]),
                'low': float(item[4]),
                'volume': int(float(item[5])) * 100,
            } for item in klines]
            df = pd.DataFrame(rows)
            df = df.drop_duplicates(subset='date').sort_values('date').reset_index(drop=True)
            mask = (df['date'] >= pd.Timestamp(start_date)) & (df['date'] <= pd.Timestamp(end_date))
            result = df[mask].reset_index(drop=True)
            keep = [c for c in ["date", "open", "close", "high", "low", "volume"] if c in result.columns]
            return result[keep]
    except Exception:
        pass

    # 备: baostock
    try:
        _ensure_bs_login()
        bs_code = sc
        fields = "date,open,close,high,low,volume,amount"
        rs = bs.query_history_k_data_plus(
            bs_code, fields,
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="2",
        )
        if rs is None:
            return pd.DataFrame()
        df = _bs_to_df(rs)
        if df is not None and len(df) > 0:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            mask = (df["date"] >= pd.Timestamp(start_date)) & (df["date"] <= pd.Timestamp(end_date))
            result = df[mask].reset_index(drop=True)
            keep = [c for c in ["date", "open", "close", "high", "low", "volume"] if c in result.columns]
            return result[keep]
    except Exception:
        pass
    return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
#  模拟数据生成
# ═══════════════════════════════════════════════════════════

def get_test_data(days=500, volatility=0.02, start_price=100.0, code="TEST", seed=42):
    """生成模拟数据用于离线测试"""
    rng = np.random.RandomState(seed)
    t = np.arange(days)
    trend = 0.00015 * t
    returns = rng.normal(trend, volatility, days)
    price = start_price * np.exp(np.cumsum(returns))
    price = np.maximum(price, start_price * 0.2)
    closes = price
    daily_ret = np.diff(np.log(closes), prepend=0)
    intraday_vol = np.abs(daily_ret) * 0.5 + 0.005
    opens = closes * np.exp(rng.normal(0, intraday_vol * 0.3, days))
    highs = np.maximum(opens, closes) * (1 + rng.uniform(0, intraday_vol, days))
    lows = np.minimum(opens, closes) * (1 - rng.uniform(0, intraday_vol, days))
    dates = pd.bdate_range(end=pd.Timestamp("today"), periods=days, freq="B")
    volumes = rng.randint(500000, 50000000, days).astype(float)
    amounts = volumes * (opens + closes) / 2
    df = pd.DataFrame({
        "date": dates,
        "open": np.round(opens, 2),
        "close": np.round(closes, 2),
        "high": np.round(highs, 2),
        "low": np.round(lows, 2),
        "volume": volumes.astype(int),
        "amount": amounts.astype(int),
    })
    df["high"] = df[["open", "close", "high"]].max(axis=1).round(2)
    df["low"] = df[["open", "close", "low"]].min(axis=1).round(2)
    return df


def _efinance_secid(code: str) -> str:
    """Convert an A-share/ETF code to Eastmoney's market-qualified secid."""
    value = str(code).strip()
    if "." in value:
        return value
    value = value.zfill(6)
    market = "1" if value.startswith(("5", "6")) else "0"
    return f"{market}.{value}"


@st.cache_data(ttl=3600, show_spinner=False)
def get_daily_data_efinance(code, start_date, end_date, adjust="qfq"):
    """Fetch efinance-compatible daily history without the blocking ID lookup.

    ``efinance`` ultimately reads Eastmoney's ``push2his`` K-line endpoint. Its
    symbol-discovery request can block indefinitely on some macOS/network
    combinations even though the K-line endpoint is healthy.  This adapter
    builds the deterministic market-qualified id locally and calls the same
    upstream contract with an explicit timeout. If that upstream is blocked,
    the adapter transparently uses the existing Tencent real-market route and
    labels it as an efinance compatibility path. No synthetic prices are ever
    returned and the exact route is recorded in ``DataFrame.attrs``.
    """
    fqt = {"": 0, "qfq": 1, "hfq": 2}.get(adjust, 1)
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "beg": pd.Timestamp(start_date).strftime("%Y%m%d"),
        "end": pd.Timestamp(end_date).strftime("%Y%m%d"),
        "rtntype": "6",
        "secid": _efinance_secid(code),
        "klt": "101",
        "fqt": str(fqt),
    }
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urllib.parse.urlencode(params, safe=",")
    upstream_error = None
    try:
        completed = subprocess.run(
            [
                "curl", "-k", "-fsSL", "--connect-timeout", "5", "--max-time", "12", url,
            ],
            check=True, capture_output=True, timeout=15,
        )
        payload = json.loads(completed.stdout)
    except Exception as exc:
        upstream_error = str(exc)
        fallback = _fetch_tencent_kline(code, start_date, end_date, adjust)
        if fallback is not None and not fallback.empty:
            fallback.attrs["provider"] = "efinance 兼容链路 / 腾讯证券"
            fallback.attrs["upstream"] = "web.ifzq.gtimg.cn"
            fallback.attrs["efinance_error"] = upstream_error
            fallback.attrs["synthetic"] = False
            return fallback
        raise RuntimeError(f"efinance/东方财富行情请求失败，腾讯兼容链路也不可用: {exc}") from exc

    node = payload.get("data") or {}
    rows = node.get("klines") or []
    if not rows:
        fallback = _fetch_tencent_kline(code, start_date, end_date, adjust)
        if fallback is not None and not fallback.empty:
            fallback.attrs["provider"] = "efinance 兼容链路 / 腾讯证券"
            fallback.attrs["upstream"] = "web.ifzq.gtimg.cn"
            fallback.attrs["efinance_error"] = "东方财富返回空行情"
            fallback.attrs["synthetic"] = False
            return fallback
        return pd.DataFrame()

    columns = [
        "date", "open", "close", "high", "low", "volume", "amount",
        "amplitude", "change_pct", "change", "turnover_rate",
    ]
    records = [row.split(",")[:len(columns)] for row in rows]
    result = pd.DataFrame(records, columns=columns)
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    for column in columns[1:]:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = (
        result.dropna(subset=["date", "open", "close", "high", "low"])
        .drop_duplicates("date")
        .sort_values("date")
        .reset_index(drop=True)
    )
    result.attrs["provider"] = "efinance / 东方财富直连"
    result.attrs["upstream"] = "push2his.eastmoney.com"
    result.attrs["synthetic"] = False
    return result


# ═══════════════════════════════════════════════════════════
#  批量获取
# ═══════════════════════════════════════════════════════════

def get_batch_data(codes, start_date, end_date, adjust="qfq", max_workers=4) -> dict:
    """并行批量获取日K线"""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_fetch_kline, code, start_date, end_date, adjust): code
            for code in codes
        }
        for future in as_completed(future_map):
            code = future_map[future]
            try:
                df = future.result()
                if df is not None and len(df) > 0:
                    results[code] = df
            except Exception:
                pass
    return results


@st.cache_data(ttl=86400, show_spinner=False)
def get_stock_info(code):
    """获取个股基本信息 (baostock)"""
    try:
        _ensure_bs_login()
        rs = bs.query_stock_basic(_map_symbol(code))
        if rs.error_code == "0":
            info = {}
            while rs.next():
                row = rs.get_row_data()
                fields = rs.fields
                for i, f in enumerate(fields):
                    if i < len(row):
                        info[f] = row[i]
            return info
    except Exception:
        pass
    return {}


__all__ = [
    "get_stock_list", "get_stock_list_extended", "get_daily_data",
    "get_realtime_quote", "get_realtime_batch", "get_batch_data",
    "get_index_data", "get_test_data", "get_daily_data_efinance", "get_stock_info",
    "check_network",
    "A_STOCK_LIST_MAIN",
]
