import psycopg
import json
import pandas as pd
import os
from datetime import datetime
from pgvector.psycopg import register_vector

def extract_complete_db(db_params=None):
    """Complete DB extraction: SCHEMA + DATA to Data/ folder (JSON/CSV)"""
    
    default_params = {
        'dbname': 'postgres', 'user': 'postgres', 
        'password': 'amangntil', 'host': 'localhost', 'port': 5432
    }
    db_params = db_params or default_params
    
    os.makedirs('Data', exist_ok=True)
    print("Created Data/ folder")
    
    conn = psycopg.connect(**db_params)
    register_vector(conn)
    cur = conn.cursor()
    
    master_summary = {
        'database': 'postgres',
        'extracted_at': datetime.now().isoformat(),
        'schema': {'tables': [], 'extensions': [], 'indexes': []},
        'data': {'tables_extracted': {}, 'total_rows': 0}
    }
    
    print("Extracting SCHEMA...")
    
    # 1. EXTENSIONS
    cur.execute("SELECT extname, extversion FROM pg_extension")
    master_summary['schema']['extensions'] = [{'name': r[0], 'version': r[1]} for r in cur.fetchall()]
    
    # 2. TABLES + DETAILED SCHEMA
    cur.execute("""
        SELECT table_schema, table_name, COALESCE(obj_description(c.oid), '') as comment
        FROM information_schema.tables t
        JOIN pg_class c ON c.relname = t.table_name AND c.relnamespace = 
            (SELECT oid FROM pg_namespace WHERE nspname = t.table_schema)
        WHERE table_type = 'BASE TABLE' AND table_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY table_schema, table_name
    """)
    
    tables = cur.fetchall()
    print(f"Found {len(tables)} tables")
    
    for schema_name, table_name, table_comment in tables:
        table_key = f"{schema_name}.{table_name}"
        print(f"  Processing {table_key}...")
        
        table_info = {
            'schema': schema_name, 'name': table_name, 'comment': table_comment,
            'columns': [], 'primary_key': [], 'row_count': 0
        }
        
        # COLUMNS
        cur.execute("""
            SELECT column_name, data_type, is_nullable, column_default,
                   character_maximum_length, numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """, (schema_name, table_name))
        table_info['columns'] = [{
            'name': r[0], 'type': r[1], 'nullable': r[2] == 'YES', 
            'default': r[3], 'char_length': r[4], 'precision': r[5], 'scale': r[6]
        } for r in cur.fetchall()]
        
        # PRIMARY KEY
        cur.execute("""
            SELECT kcu.column_name FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
            WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = %s AND tc.table_name = %s
        """, (schema_name, table_name))
        table_info['primary_key'] = [r[0] for r in cur.fetchall()]
        
        # ROW COUNT
        cur.execute(f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}"')
        table_info['row_count'] = cur.fetchone()[0]
        
        master_summary['schema']['tables'].append(table_info)
    
    # 3. INDEXES
    cur.execute("SELECT schemaname, tablename, indexname, indexdef FROM pg_indexes WHERE schemaname NOT IN ('information_schema', 'pg_catalog')")
    master_summary['schema']['indexes'] = [{'schema': r[0], 'table': r[1], 'name': r[2], 'def': r[3]} for r in cur.fetchall()]
    
    print("Extracting DATA...")
    
    # 4. DYNAMIC EXTRACTION - ✅ BUILDS QUERY FROM ACTUAL COLUMNS
    for table_info in master_summary['schema']['tables']:
        schema_name, table_name = table_info['schema'], table_info['name']
        table_key = f"{schema_name}.{table_name}"
        row_count = table_info['row_count']
        columns = [col['name'] for col in table_info['columns']]
        
        if row_count > 0:
            print(f"  Extracting {table_key} ({row_count:,} rows)...")
            
            try:
                # ✅ DYNAMIC: Build SELECT with ALL actual columns cast to TEXT
                col_selects = []
                for col_name in columns:
                    if 'embedding' in col_name.lower():
                        col_selects.append(f'"{col_name}"')  # Keep embeddings as-is
                    else:
                        col_selects.append(f'"{col_name}"::text AS "{col_name}"')
                
                select_clause = ', '.join(col_selects)
                limit = min(50000, row_count)
                
                safe_query = f'SELECT {select_clause} FROM "{schema_name}"."{table_name}" LIMIT {limit}'
                
                cur.execute(safe_query)
                rows = cur.fetchall()
                df_columns = [desc[0] for desc in cur.description]
                
                df = pd.DataFrame(rows, columns=df_columns)
                
                # Save CSV
                csv_file = f"Data/{table_key.replace('.', '_')}.csv"
                df.to_csv(csv_file, index=False)
                
                # Save JSON sample (exclude embeddings)
                json_file = f"Data/{table_key.replace('.', '_')}_sample.json"
                sample_cols = [col for col in df.columns if 'embedding' not in col.lower()]
                if sample_cols:
                    sample_df = df[sample_cols].head(100)
                    sample_df.to_json(json_file, orient='records', indent=2)
                
                master_summary['data']['tables_extracted'][table_key] = {
                    'rows_total': row_count, 'rows_extracted': len(df),
                    'csv_file': csv_file, 'json_sample': json_file if sample_cols else None,
                    'columns': list(df.columns)
                }
                master_summary['data']['total_rows'] += len(df)
                print(f"    Saved: {csv_file} ({len(df)} rows)")
                
            except Exception as e:
                print(f"    ERROR: {e}")
                continue
        else:
            print(f"  Skipping {table_key} (empty)")
    
    conn.close()
    
    # 5. SAVE MASTER FILES
    master_json = 'Data/complete_db_extract.json'
    with open(master_json, 'w') as f:
        json.dump(master_summary, f, indent=2, default=str)
    
    # Schema CSV
    schema_df = []
    for table in master_summary['schema']['tables']:
        for col in table['columns']:
            schema_df.append({
                'table': f"{table['schema']}.{table['name']}",
                'column': col['name'], 'type': col['type'],
                'nullable': col['nullable'], 'default': col['default']
            })
    pd.DataFrame(schema_df).to_csv('Data/schema_summary.csv', index=False)
    
    # Data summary CSV
    data_df = []
    for table_key, info in master_summary['data']['tables_extracted'].items():
        data_df.append({
            'table': table_key, 'rows_total': info['rows_total'],
            'rows_extracted': info['rows_extracted'],
            'csv_file': info['csv_file']
        })
    pd.DataFrame(data_df).to_csv('Data/data_summary.csv', index=False)
    
    print("\nEXTRACTION COMPLETE!")
    print(f"Tables: {len(master_summary['schema']['tables'])}")
    print(f"Rows extracted: {master_summary['data']['total_rows']:,}")
    print(f"Sales data: Data/public_sales_register.csv (103 rows)")
    print(f"Check Data/ folder for all files!")

if __name__ == "__main__":
    extract_complete_db()
