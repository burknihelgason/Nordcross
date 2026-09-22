import pyodbc

from nordcross.config import DB_DRIVER, DB_NAME, DB_PASSWORD, DB_SERVER, DB_USER


def create_database_if_missing() -> None:
    conn_str = (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DB_SERVER};"
        "DATABASE=master;"
        f"UID={DB_USER};"
        f"PWD={DB_PASSWORD};"
        "TrustServerCertificate=yes;"
    )
    conn = pyodbc.connect(conn_str, autocommit=True)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT database_id FROM sys.databases WHERE name = ?", DB_NAME)
        exists = cursor.fetchone() is not None
        if not exists:
            cursor.execute(f"CREATE DATABASE [{DB_NAME}]")
            print(f"Created database '{DB_NAME}'.")
        else:
            print(f"Database '{DB_NAME}' already exists.")
    finally:
        conn.close()


if __name__ == "__main__":
    create_database_if_missing()
