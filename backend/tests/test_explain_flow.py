import asyncio
import pytest

from scripts import explain_file

class DummyGPT:
    async def stream_response_async(self, user_message=None, **kwargs):
        return "DUMMY AI EXPLANATION"

class DummyAzureSearchService:
    def __init__(self, *args, **kwargs):
        pass
    def search(self, *args, **kwargs):
        # return two chunks as search results
        return [
            {"content": "Chunk one content about topic.", "chunk_id": "1", "file_name": "PPA_2_MB.txt"},
            {"content": "Chunk two content with more details.", "chunk_id": "2", "file_name": "PPA_2_MB.txt"}
        ]

class DummyFileContentService:
    def __init__(self, *args, **kwargs):
        pass
    def get_file_snippets(self, file_md5, db, max_snippets=5):
        return [{"content": "Snippet A"}, {"content": "Snippet B"}]
    def get_file_content_by_md5(self, file_md5, db):
        return "Full file fallback content"

@pytest.mark.asyncio
async def test_explain_document_uses_snippets_and_search(monkeypatch):
    # Arrange: patch dependencies in explain_file
    monkeypatch.setattr(explain_file, 'GPTClient', DummyGPT)
    monkeypatch.setattr(explain_file, 'AzureSearchService', DummyAzureSearchService)
    monkeypatch.setattr(explain_file, 'FileContentService', DummyFileContentService)

    # Act
    result = await explain_file.explain_document(file_md5='fake-md5', question='What is this about?')

    # Assert
    assert isinstance(result, dict)
    assert result.get('response') == 'DUMMY AI EXPLANATION'
    # citations come from AzureSearchService.search in explain_document
    assert isinstance(result.get('citations'), list)
    assert result['citations'][0]['file_name'] == 'PPA_2_MB.txt'

@pytest.mark.asyncio
async def test_explain_document_fallbacks_to_full_content(monkeypatch):
    # Arrange: FileContentService returns no snippets, but full content exists
    class FileContentNoSnippets(DummyFileContentService):
        def get_file_snippets(self, file_md5, db, max_snippets=5):
            return []
    monkeypatch.setattr(explain_file, 'GPTClient', DummyGPT)
    monkeypatch.setattr(explain_file, 'AzureSearchService', DummyAzureSearchService)
    monkeypatch.setattr(explain_file, 'FileContentService', FileContentNoSnippets)

    # Act
    result = await explain_file.explain_document(file_md5='fake-md5', question=None)

    # Assert
    assert result.get('response') == 'DUMMY AI EXPLANATION'
    assert result.get('citations') == [] or isinstance(result.get('citations'), list)
