import io
import sys
import uuid

sys.path.insert(0, "packages/rag-document-pipeline/src")

from rag_document_pipeline.storage import S3ObjectNotFoundError, S3Storage


class NotFound(Exception):
    def __init__(self):
        self.response = {"Error": {"Code": "NoSuchKey"}}


class FakeClient:
    def __init__(self):
        self.store = {}

    def put_object(self, Bucket, Key, Body, ContentLength, ContentType):
        self.store[(Bucket, Key)] = Body.read()

    def get_object(self, Bucket, Key):
        try:
            return {"Body": io.BytesIO(self.store[(Bucket, Key)])}
        except KeyError:
            raise NotFound()

    def delete_object(self, Bucket, Key):
        self.store.pop((Bucket, Key), None)

    def head_object(self, Bucket, Key):
        try:
            return {"ContentLength": len(self.store[(Bucket, Key)])}
        except KeyError:
            raise NotFound()


c = FakeClient()
s = S3Storage(bucket_name="rag-documents", client=c)
ws = uuid.uuid4()
uri = s.save("doc_layout.json", b'{"a": 1}', ws)
print(uri)
assert uri == f"s3://rag-documents/workspaces/{ws}/doc_layout.json", uri
assert s.get(uri) == b'{"a": 1}'
assert s.exists(uri) is True
assert s.get_size(uri) == 8
assert s.delete(uri) is True
assert s.exists(uri) is False
try:
    s.get(uri)
    raise AssertionError("expected not found")
except S3ObjectNotFoundError:
    pass

uri2 = s.save("doc_layout.json", b'{"b": 2}', ws)
print("re-chunking from layout:", s.get(uri2))

uri3 = s.save("report.pdf", b"pdf", ws)
print(uri3)
try:
    s.get("http://x/y")
    raise AssertionError("expected ValueError")
except ValueError:
    pass
print("OK")
