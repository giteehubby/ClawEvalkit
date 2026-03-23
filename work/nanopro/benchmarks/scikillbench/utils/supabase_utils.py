"""
Supabase utilities for research agent.
"""

import os
from supabase import create_client, Client

def get_supabase_client() -> Client:
    """
    Get a Supabase client instance.
    
    Returns:
        Client: A Supabase client instance
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables must be set")
    
    return create_client(url, key) 

def clear_supabase_tables(supabase_client):
    """Clear the extracted_code table in Supabase."""
    print("🧹 Clearing Supabase tables...")
    
    tables_to_clear = [
        # ("crawled_pages", "id", 0),
        # ("code_examples", "id", 0), 
        # ("sources", "source_id", ""),
        ("extracted_code", "id", 0)
    ]
    
    for table_name, id_column, neq_value in tables_to_clear:
        try:
            result = supabase_client.table(table_name).delete().neq(id_column, neq_value).execute()
            count = len(result.data) if result.data else 0
            print(f"   ✅ Cleared {count} records from {table_name} table")
        except Exception as e:
            print(f"   ⚠️  Error clearing {table_name} table: {e}")
            try:
                if id_column == "source_id":
                    result = supabase_client.table(table_name).delete().gte("created_at", "1970-01-01").execute()
                else:
                    result = supabase_client.table(table_name).delete().gte(id_column, 0).execute()
                count = len(result.data) if result.data else 0
                print(f"   ✅ Cleared {table_name} table using alternative method ({count} records)")
            except Exception as e2:
                print(f"   ❌ Failed to clear {table_name} table: {e2}")

def view_supabase_tables(supabase_client, limit: int = 10):
    """
    View the contents of tables in Supabase.
    
    Args:
        supabase_client: Supabase client instance
        limit: Maximum number of records to show per table (default: 10)
    """
    print("📊 Viewing Supabase tables contents...")
    
    # Define table configurations with their primary key columns
    table_configs = [
        ("crawled_pages", "id"),
        ("code_examples", "id"), 
        ("sources", "source_id"),  # sources table uses source_id as primary key
        ("extracted_code", "url")  # extracted_code table uses url as primary key
    ]
    
    for table_name, primary_key in table_configs:
        print(f"\n" + "="*60)
        print(f"Table: {table_name}")
        print("="*60)
        
        try:
            # Get total count using the correct primary key
            count_result = supabase_client.table(table_name).select(primary_key, count="exact").execute()
            total_count = count_result.count if hasattr(count_result, 'count') else len(count_result.data)
            
            print(f"Total records: {total_count}")
            
            if total_count > 0:
                # Get sample records
                result = supabase_client.table(table_name).select("*").limit(limit).execute()
                
                if result.data:
                    print(f"Showing first {len(result.data)} records:")
                    for i, record in enumerate(result.data, 1):
                        print(f"\n--- Record {i} ---")
                        for key, value in record.items():
                            # Skip embedding output to reduce verbosity
                            if key == 'embedding':
                                print(f"  {key}: [vector with {len(value)} dimensions]")
                            elif key == 'content' and isinstance(value, str) and len(value) > 200:
                                print(f"  {key}: {value[:200]}...")
                            elif key == 'code' and isinstance(value, str) and len(value) > 200:
                                print(f"  {key}: {value[:200]}...")
                            else:
                                print(f"  {key}: {value}")
                else:
                    print("No records found")
            else:
                print("Table is empty")
                
        except Exception as e:
            print(f"❌ Error viewing {table_name} table: {e}")

def get_table_statistics(supabase_client):
    """
    Get statistics about the contents of tables.
    
    Args:
        supabase_client: Supabase client instance
    """
    print("📈 Supabase tables statistics:")
    print("="*50)
    
    # Define table configurations with their primary key columns
    table_configs = [
        ("crawled_pages", "id"),
        ("code_examples", "id"), 
        ("sources", "source_id"),  # sources table uses source_id as primary key
        ("extracted_code", "url")  # extracted_code table uses url as primary key
    ]
    
    for table_name, primary_key in table_configs:
        try:
            count_result = supabase_client.table(table_name).select(primary_key, count="exact").execute()
            total_count = count_result.count if hasattr(count_result, 'count') else len(count_result.data)
            print(f"  {table_name}: {total_count} records")
        except Exception as e:
            print(f"  {table_name}: Error - {e}")