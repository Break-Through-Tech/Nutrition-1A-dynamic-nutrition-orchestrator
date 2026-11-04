# Database Vectorization

## Overview

Vector databases allow applications to store and retrieve numerical representations of data called *embeddings*. Embeddings capture semantic information about text, allowing an application to retrieve results based on meaning rather than relying exclusively on exact keyword matches.

For the Nutrition Orchestrator, vectorization could improve ingredient matching and semantic recipe retrieval. For example, a user might search for "scallions" while the USDA database lists an ingredient as "Onions, spring or scallions, raw." Traditional keyword matching may not consistently identify these relationships, whereas semantic search can retrieve conceptually similar descriptions.

We are considering two options for vector storage and retrieval for the project:

- ChromaDB
- PostgreSQL with pgvector

## 1. ChromaDB

ChromaDB is an open-source vector database designed for storing embeddings and performing similarity searches. It provides a relatively straightforward way to incorporate semantic retrieval into Python applications.

### Key Features

- **Vector similarity search:** Retrieves records based on the semantic similarity of their embeddings.
- **Metadata filtering:** Supports filtering search results using associated metadata, such as ingredient categories or USDA identifiers.
- **Python integration:** Provides a Python client and APIs for adding, querying, updating, and deleting records.
- **Persistence:** Supports persistent storage so embeddings can be retained between application sessions.
- **Open-source:** Can be run locally without requiring a managed cloud database service.

### Advantages

- Lightweight and relatively easy to set up.
- Designed specifically for vector storage and semantic retrieval.
- Straightforward integration with Python-based machine learning and AI workflows.
- Useful for prototyping and testing different embedding models.
- Supports metadata filtering alongside vector similarity search.

### Disadvantages

- Does not provide the same relational database functionality as PostgreSQL.
- Applications requiring complex relationships and SQL queries may need a separate relational database.
- Maintaining synchronization between ChromaDB and another database can introduce additional complexity.
- More advanced hybrid retrieval workflows may require additional implementation.

### Potential Application

ChromaDB could store embeddings generated from USDA ingredient descriptions and common ingredient aliases. When a user provides an ingredient name, the application could generate an embedding for the input and retrieve the most semantically similar USDA records.

## 2. PostgreSQL with pgvector

pgvector is an open-source PostgreSQL extension that adds vector similarity search capabilities to a traditional relational database. It allows applications to store embeddings alongside structured records and retrieve them using SQL.

Unlike a dedicated vector database, pgvector extends an existing database system rather than adding a separate storage layer.

### Key Features

- **Vector similarity search:** Supports nearest-neighbor searches using distance measures such as cosine distance, inner product, and Euclidean distance.
- **Relational data storage:** Stores embeddings alongside structured information in PostgreSQL tables.
- **Indexing:** Supports approximate nearest-neighbor indexing through HNSW and IVFFlat to improve search performance.
- **SQL integration:** Allows vector searches to be combined with standard SQL queries, joins, and filtering.
- **Hybrid retrieval:** Can be combined with PostgreSQL full-text search to incorporate both semantic similarity and keyword matching.
- **Python integration:** Works with PostgreSQL Python libraries and integrations such as SQLAlchemy and Psycopg.

### Advantages

- Allows structured data and vector embeddings to be stored in one database.
- Supports complex SQL queries, joins, and relational data management.
- Can combine semantic search with exact keyword matching and metadata filtering.
- Avoids maintaining separate databases for structured information and vector embeddings.
- Supports indexing strategies for improving retrieval performance as the dataset grows.
- Provides flexibility for applications that need both traditional database functionality and semantic search.

### Disadvantages

- Requires PostgreSQL setup and installation of the pgvector extension.
- Has a somewhat steeper initial learning curve compared with ChromaDB.
- Requires consideration of indexing strategies and query optimization as the dataset grows.
- May introduce unnecessary database complexity if the application only needs basic vector retrieval.

### Potential Application

pgvector could store USDA ingredient records, nutritional information, ingredient metadata, and their corresponding embeddings within PostgreSQL. This would allow the application to retrieve semantically similar ingredients while also filtering by attributes such as USDA data type, food category, or preparation method.

For example, a query could retrieve ingredients similar to "unsalted butter" while prioritizing records with the appropriate food description and USDA data type.

## 3. Comparison

| Consideration | ChromaDB | PostgreSQL + pgvector |
|---|---|---|
| Primary purpose | Dedicated vector database | Relational database with vector search |
| Setup | Lightweight and straightforward | Requires PostgreSQL and pgvector |
| Python integration | Native Python client | PostgreSQL Python libraries |
| Semantic search | Supported | Supported |
| Metadata filtering | Supported | Supported through SQL |
| Relational queries | Limited | Full SQL support |
| Full-text search | Additional implementation may be needed | PostgreSQL full-text search |
| Vector indexing | Supported | HNSW and IVFFlat |
| Structured data storage | Supported as metadata and documents | Full relational database functionality |
| Scalability | Suitable for a range of vector workloads | Can support growing relational and vector workloads |
| Best use case | Rapid prototyping and vector-focused applications | Applications combining structured data and semantic retrieval |

## 4. Relevance to the Nutrition Orchestrator

The Nutrition Orchestrator needs to identify ingredients from recipe text and retrieve the corresponding USDA food records. This requires more than finding semantically similar descriptions. The application must also preserve the correct nutritional information and distinguish between ingredients with different preparation methods or forms.

For example:

- "Scallions" should retrieve relevant USDA records for spring onions.
- "Unsalted butter" should prioritize unsalted butter rather than other butter products.
- "Raw chicken breast" should not retrieve cooked chicken breast as an equivalent ingredient.
- "Almond butter" should not be confused with dairy butter.

Vector similarity can improve the initial retrieval of potential matches, but semantic similarity alone does not guarantee nutritional equivalence.

A hybrid retrieval approach would likely be most effective:

1. Convert the user's ingredient description into an embedding.
2. Retrieve semantically similar USDA records using vector similarity search.
3. Apply metadata filters to narrow candidates based on relevant characteristics.
4. Combine semantic retrieval with keyword matching to preserve exact ingredient details.
5. Rank the retrieved candidates using the existing `rank_food_candidates()` function.
6. Pass the selected USDA record and its nutritional information to the deterministic macro calculator.

This approach would allow vector search to complement the existing keyword-matching implementation rather than replace it.

## 5. Preliminary Recommendation

Both ChromaDB and pgvector are viable options for the Nutrition Orchestrator.

ChromaDB may be the better choice for an initial proof of concept because it is lightweight, relatively easy to configure, and specifically designed for vector retrieval.
However, pgvector may be a stronger long-term architectural choice if the application plans to centralize recipe data, ingredient records, nutritional information, and embeddings within PostgreSQL.
The primary consideration is whether the project needs a dedicated vector database or would benefit more from integrating semantic retrieval directly into its relational database.
A final decision should be based on a small comparative experiment measuring retrieval accuracy, query performance, and implementation complexity.

## References

- ChromaDB Documentation: https://docs.trychroma.com/
- ChromaDB GitHub Repository: https://github.com/chroma-core/chroma
- pgvector GitHub Repository: https://github.com/pgvector/pgvector
- pgvector Python Integration: https://github.com/pgvector/pgvector-python
- PostgreSQL Documentation: https://www.postgresql.org/docs/
