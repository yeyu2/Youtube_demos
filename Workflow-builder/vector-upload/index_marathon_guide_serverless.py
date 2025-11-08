import os
from pinecone import Pinecone, ServerlessSpec
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tqdm.auto import tqdm # For a nice progress bar

# --- 1. Configuration ---
# Make sure to set these as environment variables for security
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")

PDF_FILE_PATH = "TCSNYCM25_RunnerGuide_Mobile_M.pdf"
INDEX_NAME = "simple-ai-rag"
NAMESPACE = "marathon-guide"  # Namespace to organize the data

# --- 2. Initialize Pinecone Connection ---
pc = Pinecone(api_key=PINECONE_API_KEY)

# --- 3. Connect to Existing Index ---
# Using existing index: simple-ai-rag
print(f"Connecting to existing index: {INDEX_NAME}")
index = pc.Index(INDEX_NAME)
index_stats = index.describe_index_stats()
print("\nConnected to the index. Index stats:")
print(index_stats)


# --- 4. Load and Chunk the PDF Document (Same as before) ---

print(f"\nLoading PDF from: {PDF_FILE_PATH}")
loader = PyPDFLoader(PDF_FILE_PATH)
documents = loader.load()

print(f"PDF loaded. It has {len(documents)} pages.")

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=100
)
chunked_docs = text_splitter.split_documents(documents)
print(f"PDF split into {len(chunked_docs)} chunks.")


# --- 5. Upsert Text Records to Pinecone ---

print("\nUpserting text chunks to Pinecone in batches...")

# We will upsert in batches to be more efficient
# For text upserts with integrated embedding, max batch size is 96 records
batch_size = 96

for i in tqdm(range(0, len(chunked_docs), batch_size)):
    i_end = min(i + batch_size, len(chunked_docs))
    batch = chunked_docs[i:i_end]
    
    # Prepare records with text content
    # Pinecone will handle the embedding automatically
    records = []
    for doc_num, doc in enumerate(batch):
        record = {
            "_id": f"doc_{os.path.basename(PDF_FILE_PATH)}_chunk_{i + doc_num}",
            "text": doc.page_content,  # Text field for embedding (must match index field_map)
            "source": os.path.basename(PDF_FILE_PATH),
            "page_number": doc.metadata.get('page', 'N/A')
        }
        records.append(record)
    
    # Upsert the batch using upsert_records method
    # This method handles text-to-vector conversion automatically
    index.upsert_records(
        namespace=NAMESPACE,
        records=records
    )

print("\n--- Indexing Complete! ---")
print("Final index stats:")
print(index.describe_index_stats())