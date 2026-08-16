import base64
import json
import os
import sqlite3
import threading
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timezone

import COCO_POPS_PERFORMANCE_V8_EFECTIVO as app

STATE_ID = 'coco_pops_main'
LOCK = threading.Lock()


def config():
    url = os.getenv('SUPABASE_URL', '').strip().rstrip('/')
    key = (os.getenv('SUPABASE_KEY', '').strip()
           or os.getenv('SUPABASE_PUBLISHABLE_KEY', '').strip())
    if not url or not key:
        raise RuntimeError('Faltan SUPABASE_URL y SUPABASE_KEY en Render')
    return url, key


def request(method, path, data=None, prefer=None):
    url, key = config()
    headers = {
        'apikey': key,
        'Authorization': 'Bearer ' + key,
        'Content-Type': 'application/json',
    }
    if prefer:
        headers['Prefer'] = prefer
    body = None if data is None else json.dumps(data, separators=(',', ':')).encode()
    req = urllib.request.Request(url + '/rest/v1/' + path,
                                 data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=45) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def restore():
    try:
        rows = request('GET', 'app_state?id=eq.' + urllib.parse.quote(STATE_ID)
                       + '&select=payload&limit=1') or []
        if not rows:
            print('Supabase conectado; se creará la primera copia permanente.')
            return False
        raw = zlib.decompress(base64.b64decode(rows[0]['payload']))
        temp = app.DB.with_suffix('.restore')
        temp.write_bytes(raw)
        check = sqlite3.connect(temp)
        result = check.execute('PRAGMA integrity_check').fetchone()[0]
        check.close()
        if result != 'ok':
            raise RuntimeError('La copia remota no pasó la revisión de integridad')
        temp.replace(app.DB)
        print('Metas, horarios y ventas restaurados desde Supabase.')
        return True
    except Exception as error:
        print('ERROR AL RESTAURAR DESDE SUPABASE:', error)
        return None


def save():
    temp = app.DB.with_suffix('.snapshot')
    with LOCK:
        try:
            if not app.DB.exists():
                return False
            if temp.exists():
                temp.unlink()
            source = sqlite3.connect(app.DB)
            snapshot = sqlite3.connect(temp)
            source.backup(snapshot)
            snapshot.close()
            source.close()
            payload = base64.b64encode(zlib.compress(temp.read_bytes(), 9)).decode()
            request('POST', 'app_state', {
                'id': STATE_ID,
                'payload': payload,
                'updated_at': datetime.now(timezone.utc).isoformat(),
            }, 'resolution=merge-duplicates,return=minimal')
            return True
        except Exception as error:
            print('ERROR AL GUARDAR EN SUPABASE:', error)
            return False
        finally:
            try:
                if temp.exists():
                    temp.unlink()
            except Exception:
                pass


def backup_loop(allow_first_save):
    # Da tiempo a que V8 inicialice SQLite y luego respalda cada 10 segundos.
    threading.Event().wait(5)
    while True:
        if allow_first_save:
            save()
        threading.Event().wait(10)


if __name__ == '__main__':
    restored = restore()
    # Si Supabase respondió correctamente (con copia o sin ella), se permite guardar.
    threading.Thread(target=backup_loop, args=(restored is not None,),
                     name='supabase-backup', daemon=True).start()
    app.main()
