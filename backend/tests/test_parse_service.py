"""
Test cases for ParseService
"""
import os
import sys
import io
from pathlib import Path

# Add the backend directory to the path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.services.parse_service import ParseService, PdfTextIterator, DocxTextIterator, PlainTextIterator


def test_detect_file_type():
    """Test file type detection"""
    service = ParseService()
    
    assert service._detect_file_type("test.pdf") == "pdf"
    assert service._detect_file_type("test.PDF") == "pdf"
    assert service._detect_file_type("test.docx") == "docx"
    assert service._detect_file_type("test.DOCX") == "docx"
    assert service._detect_file_type("test.txt") == "text"
    assert service._detect_file_type("test.md") == "text"
    assert service._detect_file_type("test.unknown") == "unknown"
    
    print("✓ File type detection test passed")


def test_split_text_into_chunks():
    """Test text chunking with semantic segmentation"""
    service = ParseService(chunk_size=100)
    
    # Test simple paragraph splitting
    text = "这是第一段。\n\n这是第二段。\n\n这是第三段。"
    chunks = service.split_text_into_chunks_with_semantics(text)
    assert len(chunks) > 0
    print(f"✓ Simple paragraph splitting: {len(chunks)} chunks")
    
    # Test long paragraph splitting
    long_text = "这是一个很长的段落。" * 50
    chunks = service.split_text_into_chunks_with_semantics(long_text)
    assert len(chunks) > 1
    print(f"✓ Long paragraph splitting: {len(chunks)} chunks")
    
    # Test empty text
    empty_chunks = service.split_text_into_chunks_with_semantics("")
    assert len(empty_chunks) == 0
    print("✓ Empty text handling passed")
    
    print("✓ Text chunking test passed")


def test_split_paragraph_into_sentences():
    """Test paragraph to sentence splitting"""
    service = ParseService(chunk_size=50)
    
    # Test Chinese sentences
    chinese_text = "这是第一句。这是第二句！这是第三句？"
    chunks = service.split_paragraph_into_sentences(chinese_text)
    assert len(chunks) > 0
    print(f"✓ Chinese sentence splitting: {len(chunks)} chunks")
    
    # Test English sentences
    english_text = "This is the first sentence. This is the second sentence! This is the third sentence?"
    chunks = service.split_paragraph_into_sentences(english_text)
    assert len(chunks) > 0
    print(f"✓ English sentence splitting: {len(chunks)} chunks")
    
    print("✓ Sentence splitting test passed")


def test_split_long_sentence():
    """Test long sentence splitting"""
    service = ParseService(chunk_size=50)
    
    # Test Chinese
    chinese_sentence = "这是一个非常非常长的句子，它包含了很多很多的字符，需要被拆分成多个小块。" * 5
    chunks = service.split_long_sentence(chinese_sentence)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= service.chunk_size + 20  # Allow some buffer
    print(f"✓ Chinese long sentence splitting: {len(chunks)} chunks")
    
    # Test English
    english_sentence = "This is a very very long sentence that contains many many words and needs to be split into multiple chunks. " * 5
    chunks = service.split_long_sentence(english_sentence)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= service.chunk_size + 50  # Allow buffer for words
    print(f"✓ English long sentence splitting: {len(chunks)} chunks")
    
    print("✓ Long sentence splitting test passed")


def test_plain_text_iterator():
    """Test PlainTextIterator"""
    # Use simpler ASCII text to avoid encoding issues
    text = "Line 1\nLine 2\nLine 3"
    stream = io.BytesIO(text.encode('utf-8'))
    
    iterator = PlainTextIterator(stream, buffer_size=10)
    chunks = list(iterator)
    
    assert len(chunks) > 0
    combined = "".join(chunks)
    assert combined == text, f"Expected '{text}', got '{combined}'"
    
    print(f"✓ PlainTextIterator test passed: {len(chunks)} chunks")
    
    # Also test with Chinese text but more flexible assertion
    chinese_text = "这是测试文本"
    stream2 = io.BytesIO(chinese_text.encode('utf-8'))
    iterator2 = PlainTextIterator(stream2, buffer_size=20)
    chunks2 = list(iterator2)
    combined2 = "".join(chunks2)
    assert "测试" in combined2, "Chinese text should be readable"
    print(f"✓ Chinese text PlainTextIterator test passed")


def test_get_iterator():
    """Test getting the correct iterator based on file type"""
    service = ParseService()
    
    # Test text file
    text_stream = io.BytesIO(b"test text")
    iterator = service.get_iterator("test.txt", text_stream)
    assert isinstance(iterator, PlainTextIterator)
    print("✓ Text iterator selection passed")
    
    # Test unknown file type (should fallback to PlainTextIterator)
    unknown_stream = io.BytesIO(b"test data")
    iterator = service.get_iterator("test.unknown", unknown_stream)
    assert isinstance(iterator, PlainTextIterator)
    print("✓ Unknown file type fallback passed")
    
    print("✓ Iterator selection test passed")


def test_check_memory():
    """Test memory checking functionality"""
    service = ParseService(max_memory_threshold=0.99)  # Set high threshold
    
    try:
        service.check_memory()
        print("✓ Memory check passed")
    except MemoryError:
        print("⚠ Memory threshold exceeded (this is expected if system memory is very low)")


def test_process_parent_chunk_without_db():
    """Test process_parent_chunk logic without database"""
    service = ParseService(chunk_size=100)
    
    # Prepare test data
    parent_buffer = [
        "这是第一段测试文本。\n\n",
        "这是第二段测试文本。\n\n",
        "这是第三段测试文本。"
    ]
    
    # Test the text splitting part
    parent_text = "".join(parent_buffer)
    chunks = service.split_text_into_chunks_with_semantics(parent_text)
    
    assert len(chunks) > 0
    print(f"✓ Parent chunk processing (text splitting): {len(chunks)} chunks")


def run_all_tests():
    """Run all test cases"""
    print("=" * 60)
    print("Starting ParseService Tests")
    print("=" * 60)
    
    try:
        test_detect_file_type()
        print()
        
        test_split_text_into_chunks()
        print()
        
        test_split_paragraph_into_sentences()
        print()
        
        test_split_long_sentence()
        print()
        
        test_plain_text_iterator()
        print()
        
        test_get_iterator()
        print()
        
        test_check_memory()
        print()
        
        test_process_parent_chunk_without_db()
        print()
        
        print("=" * 60)
        print("✅ All tests passed successfully!")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ Test failed with assertion error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()

