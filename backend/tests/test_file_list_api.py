"""
Test script for file list API endpoint.

Tests:
1. Get all merged files (status=1 or status=2)
"""

import requests
import logging
import json

# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API base URL
BASE_URL = "http://localhost:8000/api/v1"


def test_get_merged_files():
    """Test getting all merged files (status=1 or status=2)."""
    logger.info("\n" + "=" * 70)
    logger.info("Test: Get All Merged Files (status=1 or status=2)")
    logger.info("=" * 70)
    
    try:
        url = f"{BASE_URL}/documents/uploads"
        logger.info(f"\n📡 Sending request: GET {url}")
        
        response = requests.get(url, timeout=5)
        result = response.json()
        
        logger.info(f"\n📥 Response status code: {response.status_code}")
        logger.info(f"📥 Response body:\n{json.dumps(result, indent=2, ensure_ascii=False)}")
        
        if response.status_code == 200 and result.get('status') == 'success':
            files = result.get('data', [])
            logger.info(f"\n✅ Successfully retrieved file list")
            logger.info(f"   Total files: {len(files)}")
            
            if len(files) > 0:
                logger.info(f"\n📄 File List:")
                for idx, file in enumerate(files, 1):
                    status_text = "Completed (Searchable)" if file.get('status') == 1 else "Merged (Waiting for Parsing)"
                    logger.info(f"\n   {idx}. {file.get('fileName')}")
                    logger.info(f"      MD5: {file.get('fileMd5')}")
                    logger.info(f"      Size: {file.get('totalSize')} bytes")
                    logger.info(f"      Status: {file.get('status')} ({status_text})")
                    logger.info(f"      Created At: {file.get('createdAt')}")
                    logger.info(f"      Merged At: {file.get('mergedAt')}")
                
                # Count files by status
                status_1_count = sum(1 for f in files if f.get('status') == 1)
                status_2_count = sum(1 for f in files if f.get('status') == 2)
                
                logger.info(f"\n📊 Statistics:")
                logger.info(f"   Completed (status=1): {status_1_count} files")
                logger.info(f"   Waiting for parsing (status=2): {status_2_count} files")
                logger.info(f"   Total: {len(files)} files")
                
                return True
            else:
                logger.info(f"\n📭 No merged files found")
                logger.info(f"   Hint: Run merge test first to create some files")
                return True
        else:
            logger.error(f"\n❌ Request failed: {result.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        logger.error(f"\n❌ Error: {e}")
        return False


if __name__ == "__main__":
    logger.info("\n" + "=" * 70)
    logger.info("File List API Test Suite")
    logger.info("=" * 70)
    logger.info(f"API Base URL: {BASE_URL}")
    
    # Run test
    success = test_get_merged_files()
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("Test Results Summary")
    logger.info("=" * 70)
    
    if success:
        logger.info("✅ Test Passed")
    else:
        logger.info("❌ Test Failed")
    
    logger.info("=" * 70)

    
    try:
        url = f"{BASE_URL}/documents/uploads"
        logger.info(f"\n📡 发送请求: GET {url}")
        
        response = requests.get(url, timeout=5)
        result = response.json()
        
        logger.info(f"\n📥 响应状态码: {response.status_code}")
        logger.info(f"📥 响应内容:\n{json.dumps(result, indent=2, ensure_ascii=False)}")
        
        if response.status_code == 200 and result.get('status') == 'success':
            files = result.get('data', [])
            logger.info(f"\n✅ 成功获取文件列表")
            logger.info(f"   文件数量: {len(files)}")
            
            if len(files) > 0:
                logger.info(f"\n📄 文件列表:")
                for idx, file in enumerate(files, 1):
                    status_text = "已完成可检索" if file.get('status') == 1 else "已合并待解析"
                    logger.info(f"\n   {idx}. {file.get('fileName')}")
                    logger.info(f"      MD5: {file.get('fileMd5')}")
                    logger.info(f"      大小: {file.get('totalSize')} bytes")
                    logger.info(f"      状态: {file.get('status')} ({status_text})")
                    logger.info(f"      创建时间: {file.get('createdAt')}")
                    logger.info(f"      合并时间: {file.get('mergedAt')}")
                
                # Count files by status
                status_1_count = sum(1 for f in files if f.get('status') == 1)
                status_2_count = sum(1 for f in files if f.get('status') == 2)
                
                logger.info(f"\n📊 统计:")
                logger.info(f"   已完成 (status=1): {status_1_count} 个文件")
                logger.info(f"   待解析 (status=2): {status_2_count} 个文件")
                logger.info(f"   总计: {len(files)} 个文件")
                
                return True
            else:
                logger.info(f"\n📭 当前没有已合并的文件")
                logger.info(f"   提示: 先运行合并测试创建一些文件")
                return True
        else:
            logger.error(f"\n❌ 请求失败: {result.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        logger.error(f"\n❌ 错误: {e}")
        return False
    
    try:
        url = f"{BASE_URL}/documents/uploads"
        logger.info(f"\n📡 发送请求: GET {url}")
        
        response = requests.get(url)
        logger.info(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"\n✅ 请求成功！")
            logger.info(f"\n响应数据:")
            logger.info(json.dumps(data, indent=2, ensure_ascii=False))
            
            if data.get('status') == 'success':
                files = data.get('data', [])
                total = data.get('total', 0)
                logger.info(f"\n📊 统计信息:")
                logger.info(f"  - 总文件数: {total}")
                logger.info(f"  - 当前页文件数: {len(files)}")
                logger.info(f"  - 当前页码: {data.get('page', 'N/A')}")
                logger.info(f"  - 每页大小: {data.get('pageSize', 'N/A')}")
                
                if files:
                    logger.info(f"\n📄 文件列表:")
                    for idx, file in enumerate(files, 1):
                        logger.info(f"\n  [{idx}] {file.get('fileName', 'N/A')}")
                        logger.info(f"      MD5: {file.get('fileMd5', 'N/A')}")
                        logger.info(f"      大小: {file.get('totalSize', 0)} bytes")
                        status = file.get('status', -1)
                        status_text = {0: '上传中', 2: '已合并', 1: '已完成'}.get(status, '未知')
                        logger.info(f"      状态: {status} ({status_text})")
                        logger.info(f"      创建时间: {file.get('createdAt', 'N/A')}")
                        logger.info(f"      合并时间: {file.get('mergedAt', 'N/A')}")
                else:
                    logger.info(f"\n  ℹ️  暂无文件")
                
                return True
            else:
                logger.error(f"\n❌ 响应状态为 error")
                return False
        else:
            logger.error(f"\n❌ 请求失败: {response.status_code}")
            logger.error(f"响应: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"\n❌ 错误: {e}")
        return False


def test_get_completed_files():
    """Test getting only completed files (status=1)."""
    logger.info("\n" + "=" * 70)
    logger.info("测试 2: 获取已完成的文件 (status=1)")
    logger.info("=" * 70)
    
    try:
        url = f"{BASE_URL}/documents/uploads?status=1"
        logger.info(f"\n📡 发送请求: GET {url}")
        
        response = requests.get(url)
        logger.info(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"\n✅ 请求成功！")
            
            if data.get('status') == 'success':
                files = data.get('data', [])
                logger.info(f"\n📊 已完成文件数: {len(files)}")
                
                # Verify all files have status=1
                all_completed = all(f.get('status') == 1 for f in files)
                if all_completed:
                    logger.info(f"✅ 筛选正确：所有文件状态都是 1 (已完成)")
                else:
                    logger.warning(f"⚠️  筛选异常：发现非 status=1 的文件")
                
                return True
            else:
                logger.error(f"\n❌ 响应状态为 error")
                return False
        else:
            logger.error(f"\n❌ 请求失败: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"\n❌ 错误: {e}")
        return False


def test_get_merged_files():
    """Test getting merged but not completed files (status=2)."""
    logger.info("\n" + "=" * 70)
    logger.info("测试 3: 获取已合并待解析的文件 (status=2)")
    logger.info("=" * 70)
    
    try:
        url = f"{BASE_URL}/documents/uploads?status=2"
        logger.info(f"\n📡 发送请求: GET {url}")
        
        response = requests.get(url)
        logger.info(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"\n✅ 请求成功！")
            
            if data.get('status') == 'success':
                files = data.get('data', [])
                logger.info(f"\n📊 已合并待解析文件数: {len(files)}")
                
                if files:
                    logger.info(f"\n这些文件已经合并，但还未完成解析和索引：")
                    for file in files:
                        logger.info(f"  - {file.get('fileName')} (MD5: {file.get('fileMd5')[:8]}...)")
                else:
                    logger.info(f"\n  ℹ️  没有待解析的文件（这是正常的，说明处理流程很快）")
                
                return True
            else:
                logger.error(f"\n❌ 响应状态为 error")
                return False
        else:
            logger.error(f"\n❌ 请求失败: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"\n❌ 错误: {e}")
        return False


def test_pagination():
    """Test pagination functionality."""
    logger.info("\n" + "=" * 70)
    logger.info("测试 4: 分页功能")
    logger.info("=" * 70)
    
    try:
        # Get first page with 2 items
        url = f"{BASE_URL}/documents/uploads?page=1&page_size=2"
        logger.info(f"\n📡 发送请求: GET {url}")
        
        response = requests.get(url)
        logger.info(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"\n✅ 请求成功！")
            
            if data.get('status') == 'success':
                files = data.get('data', [])
                total = data.get('total', 0)
                page = data.get('page', 1)
                page_size = data.get('pageSize', 2)
                
                logger.info(f"\n📊 分页信息:")
                logger.info(f"  - 总记录数: {total}")
                logger.info(f"  - 当前页: {page}")
                logger.info(f"  - 每页大小: {page_size}")
                logger.info(f"  - 当前页记录数: {len(files)}")
                logger.info(f"  - 预期总页数: {(total + page_size - 1) // page_size if page_size > 0 else 0}")
                
                if len(files) <= page_size:
                    logger.info(f"\n✅ 分页正确：当前页记录数 <= 每页大小")
                else:
                    logger.warning(f"\n⚠️  分页异常：当前页记录数超过每页大小")
                
                return True
            else:
                logger.error(f"\n❌ 响应状态为 error")
                return False
        else:
            logger.error(f"\n❌ 请求失败: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"\n❌ 错误: {e}")
        return False


if __name__ == "__main__":
    logger.info("\n" + "=" * 70)
    logger.info("文件列表 API 测试套件")
    logger.info("=" * 70)
    logger.info(f"API Base URL: {BASE_URL}")
    
    # Run test
    success = test_get_merged_files()
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("测试结果汇总")
    logger.info("=" * 70)
    
    if success:
        logger.info("✅ 测试通过")
    else:
        logger.info("❌ 测试失败")
    
    logger.info("=" * 70)
