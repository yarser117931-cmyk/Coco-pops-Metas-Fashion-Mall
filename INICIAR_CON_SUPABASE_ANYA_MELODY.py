import threading

import INICIAR_CON_SUPABASE as connector

app = connector.app
original_init_db = app.init_db


def init_db_with_anya():
    original_init_db()
    connection = app.db()
    cursor = connection.cursor()
    sol = cursor.execute(
        "SELECT id FROM employees WHERE name='Sol'"
    ).fetchone()
    anya = cursor.execute(
        "SELECT id FROM employees WHERE name='Anya'"
    ).fetchone()

    if sol and not anya:
        # Conserva el historial de Sol y cambia únicamente su nombre a Anya.
        cursor.execute(
            "UPDATE employees SET name='Anya' WHERE id=?",
            (sol['id'],),
        )
    elif sol and anya:
        # Si V8 vuelve a crear un registro Sol vacío, conserva Anya
        # y elimina solamente el registro duplicado de Sol.
        cursor.execute(
            "DELETE FROM weekly_targets WHERE employee_id=?",
            (sol['id'],)
        )
        cursor.execute(
            "DELETE FROM schedules WHERE employee_id=?",
            (sol['id'],)
        )
        cursor.execute(
            "DELETE FROM employees WHERE id=?",
            (sol['id'],)
        )

    # Agrega Melody como quinto empleado si todavía no existe.
    melody = cursor.execute(
        "SELECT id FROM employees WHERE name='Melody'"
    ).fetchone()
    if not melody:
        cursor.execute(
            "INSERT INTO employees (name) VALUES (?)",
            ("Melody",),
        )

    connection.commit()
    connection.close()


app.init_db = init_db_with_anya


if __name__ == '__main__':
    restored = connector.restore()
    threading.Thread(
        target=connector.backup_loop,
        args=(restored is not None,),
        name='supabase-backup',
        daemon=True,
    ).start()
    app.main()
