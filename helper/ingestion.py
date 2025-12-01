import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
import psycopg
from pgvector.psycopg import register_vector

def etl_preprocess_sales_data(file_path):
    """ETL: Load Excel → Clean categorical columns → Generate embeddings"""
    df = pd.read_excel(file_path)
    
    categorical_cols = ['Doc Type', 'Department', 'Revenue Account', 'Region Desc', 
                       'Sales Emp', 'MANUFACTURE NAME']
    
    for col in categorical_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.lower()
    
    df['item_desc_combined'] = (
        df['Item Name'].fillna('').astype(str) + ' ' + 
        df['Additional Desc'].fillna('').astype(str)
    )
    
    df['manufacturer_clean'] = df['MANUFACTURE NAME'].fillna('- no manufacturer -')
    
    model = SentenceTransformer('all-MiniLM-L6-v2')
    item_embeddings = model.encode(df['item_desc_combined'].tolist())
    manufacturer_embeddings = model.encode(df['manufacturer_clean'].tolist())
    
    df['item_embedding'] = list(item_embeddings)
    df['manufacturer_embedding'] = list(manufacturer_embeddings)
    
    print(f"[+] ETL Complete: {len(df)} rows processed")
    print("Sample normalized categorical data:")
    for col in categorical_cols:
        if col in df.columns:
            print(f"  {col}: {df[col].unique()[:5]}")
    
    return df

def store_to_postgres(df, db_params=None):
    """Store preprocessed DataFrame to PostgreSQL with pgvector"""
    default_params = {
        'dbname': 'postgres', 
        'user': 'postgres', 
        'password': 'amangntil', 
        'host': 'localhost', 
        'port': 5432
    }
    db_params = db_params or default_params
    
    conn = psycopg.connect(**db_params)
    register_vector(conn)
    cur = conn.cursor()
    
    # Create table first
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales_register (
            id SERIAL PRIMARY KEY,
            doc_type VARCHAR,
            invoice_no VARCHAR,
            invoice_date DATE,
            party_name TEXT,
            party_code VARCHAR,
            industry_name VARCHAR,
            ref_no TEXT,
            item_code VARCHAR,
            item_name TEXT,
            revenue_account VARCHAR,
            item_group VARCHAR,
            u_item_gr_name VARCHAR,
            additional_desc TEXT,
            quantity NUMERIC,
            price NUMERIC,
            manufacture_name VARCHAR,
            basic_amt NUMERIC,
            disc_amount NUMERIC,
            total_amt NUMERIC,
            department VARCHAR,
            region_desc VARCHAR,
            sales_emp VARCHAR,
            sales_emp_2 VARCHAR,
            sales_emp_3 VARCHAR,
            deal_per_sales_emp1 NUMERIC,
            deal_per_sales_emp2 NUMERIC,
            deal_per_sales_emp3 NUMERIC,
            new_presales_person_1 VARCHAR,
            new_deal_perc_presales_1 NUMERIC,
            new_presales_person_2 VARCHAR,
            new_deal_perc_presales_2 NUMERIC,
            deal_pre_sales1_amount NUMERIC,
            deal_pre_sales2_amount NUMERIC,
            actual_billing_date DATE,
            pay_to VARCHAR,
            bill_to TEXT,
            item_embedding VECTOR(384),
            manufacturer_embedding VECTOR(384)
        );
    """)
    
    #DYNAMIC: Count exactly what's needed
    columns = ['Doc Type', 'Invoice No.', 'Invoice Date', 'Party Name', 'PartyCode', 
              'Industry Name', 'Ref No', 'ItemCode', 'Item Name', 'Revenue Account',
              'Item Group', 'U_ItemGrName', 'Additional Desc', 'Quantity', 'Price',
              'MANUFACTURE NAME', 'Basic Amt', 'Disc Amount', 'Total Amt', 'Department',
              'Region Desc', 'Sales Emp', 'Sales Emp 2', 'Sales Emp 3',
              'Deal Per Sales Emp1', 'Deal Per Sales Emp2', 'Deal Per Sales Emp3',
              'New Presales Person 1', 'New Deal % Presales 1', 'New Presales Person 2',
              'New Deal % Presales 2', 'Deal Pre Sales1 Amount', 'Deal Pre Sales2 Amount',
              'Actual Billing Date', 'Pay To', 'Bill To']
    
    # Table columns (EXCLUDING id)
    table_columns = [
        'doc_type', 'invoice_no', 'invoice_date', 'party_name', 'party_code', 
        'industry_name', 'ref_no', 'item_code', 'item_name', 'revenue_account',
        'item_group', 'u_item_gr_name', 'additional_desc', 'quantity', 'price',
        'manufacture_name', 'basic_amt', 'disc_amount', 'total_amt', 'department',
        'region_desc', 'sales_emp', 'sales_emp_2', 'sales_emp_3',
        'deal_per_sales_emp1', 'deal_per_sales_emp2', 'deal_per_sales_emp3',
        'new_presales_person_1', 'new_deal_perc_presales_1', 'new_presales_person_2',
        'new_deal_perc_presales_2', 'deal_pre_sales1_amount', 'deal_pre_sales2_amount',
        'actual_billing_date', 'pay_to', 'bill_to', 'item_embedding', 'manufacturer_embedding'
    ]
    
    # Verify column count matches
    assert len(columns) + 2 == len(table_columns), f"Column mismatch: {len(columns)}+2 != {len(table_columns)}"
    
    values = []
    for _, row in df.iterrows():
        row_data = tuple(row.get(col, None) for col in columns)
        row_data += (row['item_embedding'].tolist(), row['manufacturer_embedding'].tolist())
        values.append(row_data)
    
    # EXACTLY 37 placeholders (manually counted)
    placeholders = ','.join(['%s'] * len(table_columns))
    insert_sql = f"""
        INSERT INTO sales_register ({','.join(table_columns)}) 
        VALUES ({placeholders})
    """
    
    print(f"[DEBUG] Inserting {len(values)} rows with {len(table_columns)} columns")
    cur.executemany(insert_sql, values)
    
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"[+] Stored {len(df)} records to PostgreSQL!")

# Keep your etl_preprocess_sales_data and if __name__ == "__main__" unchanged


if __name__ == "__main__":
    processed_df = etl_preprocess_sales_data(r'D:\Workspace\data_analyst_chabot\helper\Dummy_Sales_Register.xlsx')
    store_to_postgres(processed_df)
