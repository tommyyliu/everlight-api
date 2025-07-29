from functools import cache
import os

import numpy as np
from google import genai
from google.genai import types

@cache
def get_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is required for embeddings")
    return genai.Client(api_key=api_key)

def embed_document(text: str) -> np.ndarray:
    result = get_client().models.embed_content(
        model="gemini-embedding-001",
        contents=[text],
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )

    embeddings = np.array(result.embeddings[0].values)
    return embeddings

def embed_query(query: str) -> np.ndarray:
    result = get_client().models.embed_content(
        model="gemini-embedding-001",
        contents=[query],
        config=types.EmbedContentConfig(task_type="QUESTION_ANSWERING"),
    )

    embeddings = np.array(result.embeddings[0].values)
    return embeddings