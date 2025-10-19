import os, json, tempfile, pathlib
from azure.storage.blob import BlobServiceClient
try:
    import faiss
except Exception:
    faiss = None

CONN = os.getenv("AZURE_BLOB_CONNECTION_STRING")
CONTAINER = os.getenv("JOURNALIST_INDEX_CONTAINER", "indexes")
INDEX_BLOB = os.getenv("JOURNALIST_INDEX_BLOB", "journalists.faiss")
META_BLOB = os.getenv("JOURNALIST_META_BLOB", "journalists_meta.json")

def load_index_and_meta():
    if not CONN or faiss is None:
        return None, []
    svc = BlobServiceClient.from_connection_string(CONN)
    container = svc.get_container_client(CONTAINER)
    with tempfile.NamedTemporaryFile(delete=False) as fidx, tempfile.NamedTemporaryFile(delete=False) as fmeta:
        fidx.write(container.download_blob(INDEX_BLOB).readall())
        fmeta.write(container.download_blob(META_BLOB).readall())
        fidx.flush(); fmeta.flush()
        index = faiss.read_index(fidx.name)
        meta = json.loads(pathlib.Path(fmeta.name).read_text(encoding="utf-8"))
    return index, meta.get("metadata", [])
