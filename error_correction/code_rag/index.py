import os
import sys
#import openai
import numpy as np
import faiss
import csv
from sentence_transformers import SentenceTransformer
import torch
import logging
from huggingface_hub import InferenceClient
import requests

try:
    from config import hf_token
except ModuleNotFoundError:
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from config import hf_token


#model = SentenceTransformer("Qwen/Qwen3-Embedding-0.6B")
index = None
EMBEDDING_DIM = None
metadata = []
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WATCHED_DIR = os.path.join(BASE_DIR, "knowledge_base")
RAG_DIR = WATCHED_DIR
FAISS_INDEX_FILE = os.path.join(RAG_DIR, 'coderag_index.faiss')
METADATA_FILE = os.path.join(RAG_DIR, "metadata.csv")

def generate_embeddings(content: str, local=False):
    if not local:
        try:
            API_URL = "https://router.huggingface.co/hf-inference/models/sentence-transformers/all-MiniLM-L6-v2/pipeline/feature-extraction"
            headers = {
                "Authorization": f"Bearer {hf_token}",
                "Content-Type": "application/json",
            }

            response = requests.post(API_URL, headers=headers, json={"inputs": content})
            response.raise_for_status()
            output = response.json()

            if isinstance(output, list):
                if isinstance(output[0], list):
                    embedding = np.array(output[0]).astype('float32')
                else:
                    embedding = np.array(output).astype('float32')
            else:
                print(f"Unexpected response format: {output}")
                return None

            return embedding.reshape(1, -1)

        except Exception as e:
            print(f"Error generating embeddings: {e}")
            return None


def clear_index():
    global index, metadata, EMBEDDING_DIM

    if os.path.exists(FAISS_INDEX_FILE):
        os.remove(FAISS_INDEX_FILE)

    if os.path.exists(METADATA_FILE):
        os.remove(METADATA_FILE)

    index = None
    EMBEDDING_DIM = None
    metadata = []

def add_to_index(embeddings, full_content, file_name, file_path):
    global index, metadata, EMBEDDING_DIM

    if index is None:
        EMBEDDING_DIM = embeddings.shape[1]
        index = faiss.IndexFlatL2(EMBEDDING_DIM)

    if embeddings.shape[1] != index.d:
        raise ValueError(
            f"Embedding dimension {embeddings.shape[1]} does not match FAISS index dimension {index.d}"
        )

    keyword = full_content.split('\n')[0].split('[Keyword]: ')[1]
    relative_file_path = os.path.relpath(file_path, WATCHED_DIR)

    index.add(embeddings)

    metadata.append({
        "keyword": keyword,
        "content": full_content,
        "filename": file_name,
        "filepath": relative_file_path
    })

def save_index():
    faiss.write_index(index, FAISS_INDEX_FILE)
    with open(METADATA_FILE, "w", newline="", encoding = 'utf-8') as f:
        fieldnames = ['keyword', 'content', 'filename', 'filepath']
        writer = csv.DictWriter(f, fieldnames = fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(metadata)

def load_index():
    global index, metadata, EMBEDDING_DIM

    index = faiss.read_index(FAISS_INDEX_FILE)
    EMBEDDING_DIM = index.d

    loaded_metadata = []
    csv.field_size_limit(10 * 1024 * 1024)

    with open(METADATA_FILE, "r", encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            loaded_metadata.append(row)

    metadata = loaded_metadata

    return index, metadata



def retrieve_vectors(n=5):
    n = min(n, index.ntotal)
    vectors = np.zeros((n, EMBEDDING_DIM), dtype=np.float32)
    for i in range(n):
        vectors[i] = index.reconstruct(i)
    return vectors

def inspect_metadata(n=5):
    print(f"Inspecting the first {n} metadata entries:")
    for i, data in enumerate(metadata[:n]):
        print(f"Entry {i}:")
        print(f"Filename: {data['filename']}")
        print(f"Filepath: {data['filepath']}")
        print(f"Content: {data['content'][:100]}...")  # Show the first 100 characters
        print()

def full_reindex():
    logging.info("Starting full reindexing of the codebase...")
    files_processed = 0
        
    for root, _, files in os.walk(WATCHED_DIR):
        for file in files:
            filepath = os.path.join(root, file)
            print(filepath)
            try:
                with open(filepath, "r", encoding = 'utf-8') as file: full_content = file.read()
                
                # only embedding text
                if "[Design Detail]:" in full_content:
                    embed_content = full_content.split("[Design Detail]:")[0]
                else:
                    embed_content = full_content

                embeddings = generate_embeddings(embed_content)
                if embeddings is not None:
                    add_to_index(embeddings, full_content, file, filepath)
                else:
                    logging.warning(f"Failed to generate embeddings for {filepath}")
                files_processed += 1
            except Exception as e:
                logging.error(f"Error processing file {filepath}: {e}")

    save_index()
    logging.info(f"Full reindexing completed. {files_processed} files processed.")
    
if __name__ == "__main__":
    
    clear_index()
    full_reindex()
