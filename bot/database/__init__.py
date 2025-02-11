import time
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, ScoredPoint, Record, Filter, FieldCondition, MatchValue, \
    PayloadSchemaType, WriteOrdering, OrderBy
from sentence_transformers import SentenceTransformer

client = QdrantClient()
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

if not client.collection_exists("articles"):
    client.create_collection(
        collection_name="articles",
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    )

if not client.collection_exists("messages"):
    client.create_collection(
        collection_name="messages",
        vectors_config=VectorParams(size=1, distance=Distance.COSINE),
    )
client.create_payload_index(
    collection_name="messages",
    field_name="timestamp",
    field_schema=PayloadSchemaType.INTEGER,
)


def find_suitable_article_by_query(query) -> list[ScoredPoint]:
    query_vector = model.encode(query).tolist()

    search_results = client.search(
        collection_name="articles",
        query_vector=query_vector,

        limit=4,
    )

    return search_results


def find_articles_by_id(article_id) -> Record | None:
    search_results = client.retrieve(
        collection_name="articles",
        ids=[article_id],
    )
    return search_results[0] if search_results else None


def find_message(chat_id, message_id) -> Record | None:
    results = client.scroll(
        collection_name="messages",
        scroll_filter=Filter(
            must=[
                FieldCondition(key="chat_id", match=MatchValue(value=chat_id)),
                FieldCondition(key="message_id", match=MatchValue(value=message_id)),
            ]
        ),
        order_by=OrderBy(
            key="timestamp",
            direction="desc",  # default is "asc"
        ),
        limit=1
    )
    return results[0][0] if len(results[0]) > 0 else None


def save_message(data):
    search_results = client.scroll(
        collection_name="messages",
        scroll_filter=Filter(
            must=[
                FieldCondition(key="chat_id", match=MatchValue(value=data["chat_id"])),
                FieldCondition(key="message_id", match=MatchValue(value=data["message_id"])),
            ]
        ),
        limit=1
    )

    if search_results[0]:  # If we found the existing record
        # Assuming the first record is the one we need to update
        existing_record = search_results[0][0]

        # Now we can perform the upsert to update the existing record
        client.upsert(
            collection_name="messages",
            points=[
                {
                    "id": existing_record.payload["id"],  # Use the existing ID to update the record
                    "vector": [0] * 1,  # You may want to update the vector here as well
                    "payload": {
                        "chat_id": data["chat_id"],
                        "message_id": data["message_id"],
                        "role": data["role"],
                        "content": data["content"],  # New content
                        "sources": data["sources"],
                        "timestamp": int(time.time()),  # New timestamp
                        "deleted": data.get("deleted", False)
                    }
                }
            ],
        )
    else:
        # If no record was found, insert a new one
        client.upsert(
            collection_name="messages",
            points=[
                {
                    "id": str(uuid.uuid4()),  # New ID for the new record
                    "vector": [0] * 1,
                    "payload": {
                        "chat_id": data["chat_id"],
                        "message_id": data["message_id"],
                        "role": data["role"],
                        "content": data["content"],
                        "sources": data["sources"],
                        "timestamp": int(time.time()),
                        "deleted": False
                    }
                }
            ],
        )
