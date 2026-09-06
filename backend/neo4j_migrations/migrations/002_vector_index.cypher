// Create vector index on Chunk embedding
// For sentence-transformers (all-MiniLM-L6-v2), dimension is 384
// We use cosine similarity
CREATE VECTOR INDEX chunk_embeddings IF NOT EXISTS
FOR (c:Chunk) ON (c.embedding)
OPTIONS {indexConfig: {
 `vector.dimensions`: 384,
 `vector.similarity_function`: 'cosine'
}};
