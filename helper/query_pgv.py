import psycopg
import torch
from sentence_transformers import SentenceTransformer

# Load embedding model once
model = SentenceTransformer('all-MiniLM-L6-v2')

def query_pgvector_db(user_query: str, vector_column: str, table_name: str = 'sales_register', top_k: int = 5):
    """
    Query pgvector-enabled PostgreSQL table by user query string similarity.

    Args:
        user_query (str): The input query string from the user.
        vector_column (str): The name of the pgvector column to search (`item_embedding`, for example).
        table_name (str): Name of table to query. Default 'sales_register'.
        top_k (int): Number of nearest neighbors to return.

    Returns:
        List of rows from the database ordered by closest match.
    """
    # 1. Generate embedding for user query
    embedding = model.encode(user_query).tolist()

    # 2. Convert embedding list to Postgres pgvector text format
    embedding_str = '[' + ','.join(map(str, embedding)) + ']'

    # 3. Prepare SQL query using pgvector "<->" distance operator
    # sql = f"""
    # SELECT *, {vector_column} <-> '{embedding_str}' AS distance
    # FROM {table_name}
    # ORDER BY {vector_column} <-> '{embedding_str}'
    # LIMIT {top_k};
    # """

    # Example: hardcoded column list (excluding vector_column)
    columns = [
        "party_code", "item_name", "invoice_no", "additional_desc",
        # add all relevant columns except the vector embedding column(s)
    ]

    columns_str = ', '.join(columns)

    sql = f"""
            SELECT {columns_str}, {vector_column} <-> '{embedding_str}' AS distance
            FROM {table_name}
            ORDER BY distance
            LIMIT {top_k};
            """

    # 4. Connect to PostgreSQL, execute query, fetch results
    conn = psycopg.connect("dbname=postgres user=postgres password=amangntil host=localhost port=5432")
    with conn.cursor() as cur:
        cur.execute(sql)
        results = cur.fetchall()

    conn.close()

    return results

# Example usage:
if __name__ == "__main__":
    user_input = "3 Years Support - Gold Support Mon"
    col = "item_embedding"
    matches = query_pgvector_db(user_input, col)
    for row in matches:
        print(row)
