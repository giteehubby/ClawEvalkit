-- Enable pgvector extension for vector operations
-- This must be run first before creating tables with vector columns
CREATE EXTENSION IF NOT EXISTS vector;

-- Create extracted_code table for individual code blocks with separate embeddings
CREATE TABLE IF NOT EXISTS extracted_code (
    id BIGSERIAL PRIMARY KEY,
    url TEXT NOT NULL,
    code_text TEXT NOT NULL,
    summary TEXT NOT NULL,
    context_before TEXT,
    context_after TEXT,
    code_type TEXT,
    language TEXT,
    index INTEGER NOT NULL,
    extraction_method TEXT NOT NULL DEFAULT 'single_page',
    embedding vector(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_extracted_code_url ON extracted_code(url);
CREATE INDEX IF NOT EXISTS idx_extracted_code_type ON extracted_code(code_type);
CREATE INDEX IF NOT EXISTS idx_extracted_code_language ON extracted_code(language);
CREATE INDEX IF NOT EXISTS idx_extracted_code_embedding ON extracted_code USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_extracted_code_created_at ON extracted_code(created_at);

-- Create unique constraint to prevent duplicate code blocks from same URL
CREATE UNIQUE INDEX IF NOT EXISTS idx_extracted_code_url_index ON extracted_code(url, index);

DROP FUNCTION IF EXISTS match_code_blocks(vector(1536), integer, jsonb);

-- Create function for semantic search of code blocks
CREATE OR REPLACE FUNCTION match_code_blocks(
    query_embedding vector(1536),
    match_count int DEFAULT 10,
    filter_metadata jsonb DEFAULT '{}'
)
RETURNS TABLE (
    id bigint,
    url text,
    code_text text,
    summary text,
    context_before text,
    context_after text,
    code_type text,
    language text,
    index int,
    extraction_method text,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ec.id,
        ec.url,
        ec.code_text,
        ec.summary,
        ec.context_before,
        ec.context_after,
        ec.code_type,
        ec.language,
        ec.index,
        ec.extraction_method,
        1 - (ec.embedding <=> query_embedding) as similarity
    FROM extracted_code ec
    WHERE 
        (filter_metadata->>'language' IS NULL OR ec.language = filter_metadata->>'language')
        AND (filter_metadata->>'code_type' IS NULL OR ec.code_type = filter_metadata->>'code_type')
        AND (filter_metadata->>'url' IS NULL OR ec.url = filter_metadata->>'url')
    ORDER BY ec.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Add comments to columns
COMMENT ON COLUMN extracted_code.url IS 'The URL from which the code block was extracted';
COMMENT ON COLUMN extracted_code.code_text IS 'The actual code text content';
COMMENT ON COLUMN extracted_code.summary IS 'AI-generated summary of the code block';
COMMENT ON COLUMN extracted_code.context_before IS 'Text context before the code block';
COMMENT ON COLUMN extracted_code.context_after IS 'Text context after the code block';
COMMENT ON COLUMN extracted_code.code_type IS 'Type of code block (markdown_code_block, command_example, etc.)';
COMMENT ON COLUMN extracted_code.language IS 'Programming language of the code block';
COMMENT ON COLUMN extracted_code.index IS 'Index/position of the code block within the URL';
COMMENT ON COLUMN extracted_code.extraction_method IS 'Method used for extraction (single_page, smart_crawl, etc.)';
COMMENT ON COLUMN extracted_code.embedding IS 'Vector embedding of the code block (code + summary + context) for semantic search';
COMMENT ON COLUMN extracted_code.created_at IS 'Timestamp when the record was created'; 