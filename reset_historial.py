"""
Borra TODO el historial de pedidos (solicitudes e ítems) y reinicia el contador.
Los usuarios y los datos de productos NO se tocan.
Uso (una sola vez, en una consola Bash de PythonAnywhere):
    cd App-Pedidos
    python reset_historial.py
"""
from database import get_db, init_db

def main():
    init_db()  # asegura que las tablas existan
    conn = get_db()
    n_sol = conn.execute("SELECT COUNT(*) FROM solicitudes").fetchone()[0]
    n_item = conn.execute("SELECT COUNT(*) FROM items_solicitud").fetchone()[0]

    conn.execute("DELETE FROM items_solicitud")
    conn.execute("DELETE FROM solicitudes")
    try:
        conn.execute("DELETE FROM envios")
    except Exception:
        pass
    # Reinicia el autoincrement de IDs (si la tabla existe)
    try:
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('solicitudes','items_solicitud','envios')")
    except Exception:
        pass
    conn.commit()
    conn.close()
    print(f"Listo. Borradas {n_sol} solicitudes y {n_item} items.")
    print("El proximo pedido sera SOL-000001.")

if __name__ == '__main__':
    main()
