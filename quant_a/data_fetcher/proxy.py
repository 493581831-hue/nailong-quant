"""
数据获取代理 — 使用bundled Python(OpenSSL 3.5)通过东方财富直接HTTP API获取数据
"""

import json
import sys
import urllib.request
import concurrent.futures

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Referer': 'https://quote.eastmoney.com/',
}
_TIMEOUT = 15


def _secid(code):
    code = str(code).strip().zfill(6)
    if code.startswith('6') or code.startswith('5'):
        return '1.' + code
    return '0.' + code


def get_kline(code, adjust='qfq', limit=500):
    sid = _secid(code)
    fqt_map = {'qfq': '1', 'hfq': '2', '': '0'}
    fqt = fqt_map.get(adjust, '1')
    url = ('https://push2his.eastmoney.com/api/qt/stock/kline/get?'
           f'secid={sid}&fields1=f1,f2,f3,f4,f5,f6'
           '&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61'
           f'&klt=101&fqt={fqt}&end=20500101&lmt={limit}')
    req = urllib.request.Request(url, headers=_HEADERS)
    r = urllib.request.urlopen(req, timeout=_TIMEOUT)
    data = json.loads(r.read())
    if data.get('data') and data['data'].get('klines'):
        return [item.split(',') for item in data['data']['klines']]
    return []


def get_realtime(code):
    sid = _secid(code)
    url = (f'https://push2.eastmoney.com/api/qt/stock/get?'
           f'secid={sid}'
           '&fields=f43,f44,f45,f46,f47,f48,f50,f57,f58,f170,f171')
    req = urllib.request.Request(url, headers=_HEADERS)
    r = urllib.request.urlopen(req, timeout=_TIMEOUT)
    data = json.loads(r.read())
    d = data.get('data')
    if d:
        return {
            'code': str(d.get('f57', '')),
            'name': str(d.get('f58', '')),
            'price': (d.get('f43') or 0) / 100,
            'open': (d.get('f46') or 0) / 100,
            'high': (d.get('f44') or 0) / 100,
            'low': (d.get('f45') or 0) / 100,
            'prev_close': (d.get('f47') or 0) / 100,
            'volume': d.get('f50') or 0,
            'amount': (d.get('f48') or 0) / 100,
            'change_pct': d.get('f170') or 0,
            'turnover': d.get('f171') or 0,
        }
    return {}


def batch_kline(codes, adjust='qfq', limit=500, max_workers=6):
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        fut_map = {ex.submit(get_kline, c, adjust, limit): c for c in codes}
        for fut in concurrent.futures.as_completed(fut_map):
            code = fut_map[fut]
            try:
                klines = fut.result()
                if klines:
                    results[code] = klines
            except Exception:
                pass
    return results


def batch_realtime(codes, max_workers=6):
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        fut_map = {ex.submit(get_realtime, c): c for c in codes}
        for fut in concurrent.futures.as_completed(fut_map):
            code = fut_map[fut]
            try:
                result = fut.result()
                if result:
                    results[code] = result
            except Exception:
                pass
    return results


def check_network():
    try:
        get_kline('600519', limit=1)
        return True
    except Exception:
        return False


if __name__ == '__main__':
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'help'
    if cmd == 'kline':
        code = sys.argv[2] if len(sys.argv) > 2 else '600519'
        adjust = sys.argv[3] if len(sys.argv) > 3 else 'qfq'
        limit = int(sys.argv[4]) if len(sys.argv) > 4 else 500
        result = get_kline(code, adjust, limit)
        print(json.dumps(result))
    elif cmd == 'realtime':
        code = sys.argv[2] if len(sys.argv) > 2 else '600519'
        result = get_realtime(code)
        print(json.dumps(result))
    elif cmd == 'batch_kline':
        codes = sys.argv[2:8] if len(sys.argv) > 2 else ['600519']
        adjust = sys.argv[8] if len(sys.argv) > 8 else 'qfq'
        limit = int(sys.argv[9]) if len(sys.argv) > 9 else 200
        result = batch_kline(codes, adjust, limit)
        print(json.dumps(result))
    elif cmd == 'check':
        print(json.dumps({'ok': check_network()}))
    else:
        print(json.dumps({'error': 'unknown command'}))
