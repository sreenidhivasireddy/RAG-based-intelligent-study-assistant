"""
Example usage of ParseService

This script demonstrates how to use the ParseService to parse documents.
"""

import sys
import io
from pathlib import Path

# Add the backend directory to the path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.services.parse_service import ParseService


def example_1_basic_text_splitting():
    """Example 1: Basic text splitting"""
    print("=" * 60)
    print("Example 1: Basic Text Splitting")
    print("=" * 60)
    
    service = ParseService(chunk_size=100)
    
    text = """
    人工智能（Artificial Intelligence，AI）是计算机科学的一个分支。
    
    它试图了解智能的实质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。
    
    该领域的研究包括机器人、语言识别、图像识别、自然语言处理和专家系统等。
    """
    
    chunks = service.split_text_into_chunks_with_semantics(text)
    
    print(f"\nOriginal text length: {len(text)} characters")
    print(f"Number of chunks: {len(chunks)}")
    print("\nChunks:")
    for i, chunk in enumerate(chunks, 1):
        print(f"\n  Chunk {i} ({len(chunk)} chars):")
        print(f"  {chunk[:80]}...")
    
    print("\n✓ Example 1 completed\n")


def example_2_sentence_splitting():
    """Example 2: Sentence splitting"""
    print("=" * 60)
    print("Example 2: Sentence Splitting")
    print("=" * 60)
    
    service = ParseService(chunk_size=50)
    
    paragraph = "机器学习是人工智能的核心。它使计算机能够从数据中学习。深度学习是机器学习的一个分支。神经网络是深度学习的基础。"
    
    chunks = service.split_paragraph_into_sentences(paragraph)
    
    print(f"\nOriginal paragraph: {paragraph}")
    print(f"\nNumber of sentence chunks: {len(chunks)}")
    print("\nSentence chunks:")
    for i, chunk in enumerate(chunks, 1):
        print(f"  {i}. {chunk}")
    
    print("\n✓ Example 2 completed\n")


def example_3_long_sentence_splitting():
    """Example 3: Long sentence splitting by words"""
    print("=" * 60)
    print("Example 3: Long Sentence Splitting (Word Level)")
    print("=" * 60)
    
    service = ParseService(chunk_size=30)
    
    # Chinese long sentence
    long_sentence = "机器学习算法通过分析大量数据来识别模式和规律，从而能够对新的输入数据做出准确的预测和决策"
    
    chunks = service.split_long_sentence(long_sentence)
    
    print(f"\nLong sentence ({len(long_sentence)} chars):")
    print(f"  {long_sentence}")
    print(f"\nSplit into {len(chunks)} word-level chunks:")
    for i, chunk in enumerate(chunks, 1):
        print(f"  Chunk {i} ({len(chunk)} chars): {chunk}")
    
    # English long sentence
    english_sentence = "Machine learning algorithms analyze large amounts of data to identify patterns and regularities"
    
    chunks_en = service.split_long_sentence(english_sentence)
    
    print(f"\nEnglish long sentence ({len(english_sentence)} chars):")
    print(f"  {english_sentence}")
    print(f"\nSplit into {len(chunks_en)} word-level chunks:")
    for i, chunk in enumerate(chunks_en, 1):
        print(f"  Chunk {i} ({len(chunk)} chars): {chunk}")
    
    print("\n✓ Example 3 completed\n")


def example_4_file_type_detection():
    """Example 4: File type detection"""
    print("=" * 60)
    print("Example 4: File Type Detection")
    print("=" * 60)
    
    service = ParseService()
    
    test_files = [
        "document.pdf",
        "report.docx",
        "notes.txt",
        "readme.md",
        "data.csv",
        "image.jpg"
    ]
    
    print("\nFile type detection results:")
    for filename in test_files:
        file_type = service._detect_file_type(filename)
        print(f"  {filename:20} -> {file_type}")
    
    print("\n✓ Example 4 completed\n")


def example_5_streaming_text():
    """Example 5: Streaming text processing"""
    print("=" * 60)
    print("Example 5: Streaming Text Processing")
    print("=" * 60)
    
    service = ParseService()
    
    # Create a text stream
    text_content = "Line 1: Introduction\nLine 2: Main content\nLine 3: Conclusion"
    stream = io.BytesIO(text_content.encode('utf-8'))
    
    # Get the appropriate iterator
    iterator = service.get_iterator("test.txt", stream)
    
    print("\nProcessing text stream:")
    chunk_count = 0
    for chunk in iterator:
        chunk_count += 1
        print(f"  Chunk {chunk_count}: {chunk[:50]}...")
    
    print(f"\nTotal chunks processed: {chunk_count}")
    print("\n✓ Example 5 completed\n")


def example_6_configuration():
    """Example 6: Custom configuration"""
    print("=" * 60)
    print("Example 6: Custom Configuration")
    print("=" * 60)
    
    # Create service with custom settings
    service = ParseService(
        chunk_size=200,
        parent_chunk_size=2048,
        buffer_size=1024,
        max_memory_threshold=0.85
    )
    
    print("\nCustom configuration:")
    print(f"  Chunk size: {service.chunk_size}")
    print(f"  Parent chunk size: {service.parent_chunk_size}")
    print(f"  Buffer size: {service.buffer_size}")
    print(f"  Max memory threshold: {service.max_memory_threshold}")
    
    # Test with custom settings
    text = "这是一个测试文本。" * 20
    chunks = service.split_text_into_chunks_with_semantics(text)
    
    print(f"\nProcessed text ({len(text)} chars) into {len(chunks)} chunks")
    print("\n✓ Example 6 completed\n")


def main():
    """Run all examples"""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 10 + "ParseService Usage Examples" + " " * 21 + "║")
    print("╚" + "═" * 58 + "╝")
    print("\n")
    
    try:
        example_1_basic_text_splitting()
        example_2_sentence_splitting()
        example_3_long_sentence_splitting()
        example_4_file_type_detection()
        example_5_streaming_text()
        example_6_configuration()
        
        print("=" * 60)
        print("✅ All examples completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

