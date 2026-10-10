import os
import threading
from datetime import timedelta

import INICIAR_CON_SUPABASE as connector

app = connector.app
original_init_db = app.init_db
TEAM = ('Mariana', 'Itzel', 'Eduardo', 'Anya', 'Melody')
VERSION = 'equipo_octubre_2026_v1'


def read_pin(key):
    pin = os.getenv(key, '').strip()
    if not pin.isdigit() or len(pin) < 4:
        raise RuntimeError(f'Configura {key} en Render: PIN numerico de al menos 4 digitos.')
    return pin


def shifts_for(day):
    weekday = day.weekday()
    shifts = []
    if weekday <= 5:
        shifts.append(('Mariana', '10:00', '16:30'))
    if weekday in (5, 6):
        shifts.extend([('Melody', '13:30', '21:30'),
                       ('Eduardo', '13:30', '21:30')])
    if weekday in (3, 4, 5):
        shifts.append(('Itzel', '16:30', '21:30'))
    if weekday == 6:
        shifts.append(('Itzel', '10:00', '16:30'))
    if weekday != 5:
        shifts.append(('Anya', '16:30', '21:30'))
    return shifts


def seed_current_week():
    start, end = app.current_week()
    marker = VERSION + ':' + str(start)
    with app.db() as connection:
        if connection.execute('SELECT 1 FROM settings WHERE key=?', (marker,)).fetchone():
            return
        ids = {row['name']: row['id'] for row in connection.execute(
            'SELECT id,name FROM employees WHERE active=1')}
        if any(name not in ids for name in TEAM):
            raise RuntimeError('El equipo actual no esta completo.')
        # Solo sustituye el calendario de la semana actual; conserva semanas anteriores.
        connection.execute('DELETE FROM schedules WHERE work_date BETWEEN ? AND ?',
                           (str(start), str(end)))
        for offset in range(7):
            day = start + timedelta(days=offset)
            for name, entry, exit_time in shifts_for(day):
                connection.execute(
                    'INSERT INTO schedules(employee_id,work_date,start_time,end_time) VALUES(?,?,?,?)',
                    (ids[name], str(day), entry, exit_time))
        for name in TEAM:
            connection.execute(
                'INSERT OR IGNORE INTO weekly_targets(employee_id,week_start,target,bonus) VALUES(?,?,?,?)',
                (ids[name], str(start), 18000, 0))
        connection.execute('INSERT INTO settings(key,value) VALUES(?,?)', (marker, 'aplicado'))


def init_current_team():
    # Los PIN nuevos se guardan en Render, nunca en este repositorio publico.
    new_pins = {name: read_pin(name.upper() + '_PIN') for name in ('Mariana', 'Melody')}
    # Evita generar el calendario anterior antes de registrar el nuevo equipo.
    app.seed_week_if_missing = lambda: None
    try:
        original_init_db()
    finally:
        app.seed_week_if_missing = seed_current_week
    with app.db() as connection:
        for name in TEAM:
            row = connection.execute('SELECT id FROM employees WHERE name=?', (name,)).fetchone()
            if not row:
                pin = new_pins.get(name)
                if not pin:
                    raise RuntimeError(f'No existe el acceso de {name}.')
                connection.execute('INSERT INTO employees(name,pin_hash,active) VALUES(?,?,1)',
                                   (name, app.hpin(pin)))
            elif name in new_pins:
                connection.execute('UPDATE employees SET pin_hash=? WHERE id=?',
                                   (app.hpin(new_pins[name]), row['id']))
        connection.execute('UPDATE employees SET active=0')
        for name in TEAM:
            connection.execute('UPDATE employees SET active=1 WHERE name=?', (name,))
    seed_current_week()


app.init_db = init_current_team
app.seed_week_if_missing = seed_current_week


if __name__ == '__main__':
    restored = connector.restore()
    if restored is None:
        raise RuntimeError('No se pudo restaurar Supabase. Se detiene para proteger el historial.')
    # Inicializa antes de arrancar las copias automaticas.
    app.init_db()
    threading.Thread(target=connector.backup_loop, args=(True,),
                     name='supabase-backup', daemon=True).start()
    app.main()
