"""Local sentence-transformers embeddings, via LangChain's Embeddings interface
(specs/010-langchain-integration) — no custom Embedder ABC; `langchain_core.embeddings.Embeddings`
(`embed_documents`/`embed_query`) is the interface calling code (retriever.py, api.py) depends
on directly, since `Chroma(embedding_function=...)` expects that interface and a bridging
adapter would just be hand-written glue for a problem `Embeddings` already solves.
"""

from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings


def get_embeddings(model_name: str = "BAAI/bge-small-en-v1.5") -> Embeddings:
    return HuggingFaceEmbeddings(model_name=model_name)
