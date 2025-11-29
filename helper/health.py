# test_db.py
import psycopg
print(psycopg.__version__)
from pgvector.psycopg import register_vector


conn = psycopg.connect(
    dbname="postgres", user="postgres", 
    password="amangntil", host="localhost", port=5432
)
register_vector(conn)
print("[+] Database connected!")
conn.close()
