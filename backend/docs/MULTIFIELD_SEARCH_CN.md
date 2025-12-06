# 多字段混合搜索

本文档描述 RAG 智能学习助手的多字段混合搜索实现。

## 概述

搜索系统结合 **KNN（向量）** 和 **BM25（关键词）** 搜索，配合多字段文本分析，为中英文混合内容提供精准搜索结果。

## 架构

```
                         用户查询
                            │
                            ▼
┌───────────────────────────────────────────────────────────┐
│                     查询处理                              │
│                                                           │
│  1. 生成查询向量 (Gemini API)                             │
│  2. 根据查询特征自动调整权重                               │
└───────────────────┬───────────────────────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────────────────────┐
│                 Elasticsearch 查询                        │
├───────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────────┐    ┌──────────────────┐            │
│  │   KNN 搜索       │    │  多字段          │            │
│  │   (语义匹配)      │    │  BM25 搜索      │            │
│  │                  │    │                  │            │
│  │  cosine(q, doc)  │    │  textContent     │ ← 中文(IK) │
│  │                  │    │  textContent.en  │ ← 英文词干 │
│  │                  │    │  textContent.std │ ← 标准分词 │
│  └────────┬─────────┘    └────────┬─────────┘            │
│           │                       │                       │
│           └───────────┬───────────┘                       │
│                       │                                   │
│                       ▼                                   │
│           ┌───────────────────────┐                       │
│           │    RRF 融合           │                       │
│           │                       │                       │
│           │ score = w1*knn +      │                       │
│           │         w2*bm25/(k+bm25)                      │
│           └───────────────────────┘                       │
│                                                           │
└───────────────────────────────────────────────────────────┘
                    │
                    ▼
               排序后的结果
```

## 多字段索引结构

### 字段配置

| 字段 | 分词器 | 用途 |
|------|--------|------|
| `textContent` | IK (chinese_max/smart) | 中文分词 |
| `textContent.english` | english | 英文词干提取 |
| `textContent.standard` | standard | 备用分词 |
| `vector` | - | 768维稠密向量 |

### 索引 Mapping

```json
{
  "mappings": {
    "properties": {
      "textContent": {
        "type": "text",
        "analyzer": "chinese_max",
        "search_analyzer": "chinese_smart",
        "fields": {
          "english": {
            "type": "text",
            "analyzer": "english"
          },
          "standard": {
            "type": "text",
            "analyzer": "standard"
          }
        }
      },
      "vector": {
        "type": "dense_vector",
        "dims": 768,
        "similarity": "cosine"
      }
    }
  }
}
```

## 分词效果对比

### 测试文本

```
"PyTorch 深度学习模型优化"
```

### 不同分词器结果

| 分词器 | 分词结果 |
|--------|---------|
| **standard** | `["pytorch", "深", "度", "学", "习", "模", "型", "优", "化"]` |
| **ik_smart** | `["pytorch", "深度学习", "模型", "优化"]` |
| **ik_max_word** | `["pytorch", "深度学习", "深度", "学习", "模型", "优化"]` |
| **english** | `["pytorch", "深", "度", "学", "习", "模", "型", "优", "化"]` (对中文无效) |

### 英文词干提取示例

| 搜索词 | 可匹配到 |
|--------|---------|
| optimizing | optimize, optimizer, optimization |
| learning | learn, learned, learner |
| running | run, runs, ran |

## 配置说明

### 环境变量 (.env)

```bash
# ===== Elasticsearch 配置 =====
ES_INDEX_NAME=knowledge_base

# ===== 混合搜索权重 (KNN vs BM25) =====
SEARCH_KNN_WEIGHT=0.5          # 0-1，越高越偏向语义搜索
SEARCH_BM25_WEIGHT=0.5         # 0-1，越高越偏向关键词匹配
SEARCH_RRF_K=60                # RRF 常数 (1-200)

# ===== 多字段权重 (BM25 内部) =====
SEARCH_CHINESE_BOOST=1.0       # 中文字段重要性
SEARCH_ENGLISH_BOOST=0.8       # 英文字段重要性
SEARCH_STANDARD_BOOST=0.5      # 标准字段重要性
SEARCH_TIE_BREAKER=0.3         # 非最佳字段贡献度

# ===== 功能开关 =====
SEARCH_MULTIFIELD_ENABLED=true
SEARCH_AUTO_ADJUST_WEIGHTS=true
SEARCH_HIGHLIGHT_ENABLED=true
```

## API 接口

### 搜索接口

```http
POST /api/v1/search/
Content-Type: application/json

{
  "query": "如何优化 PyTorch 模型？",
  "top_k": 10,
  "search_mode": "hybrid",
  "knn_weight": 0.5,
  "bm25_weight": 0.5,
  "auto_adjust": true,
  "use_multifield": true
}
```

### 响应示例

```json
{
  "query": "如何优化 PyTorch 模型？",
  "total_results": 5,
  "results": [
    {
      "file_md5": "abc123",
      "chunk_id": 1,
      "text_content": "PyTorch 模型优化技巧包括...",
      "score": 1.284,
      "highlights": ["<mark>PyTorch</mark> 模型<mark>优化</mark>..."]
    }
  ],
  "search_mode": "hybrid",
  "metadata": {
    "knn_weight": 0.5,
    "bm25_weight": 0.5,
    "multifield_enabled": true,
    "field_boosts": {
      "chinese": 1.0,
      "english": 0.8,
      "standard": 0.5
    }
  }
}
```

### 索引管理

```http
# 创建索引
POST /api/v1/search/index/create?use_ik=true

# 获取索引信息
GET /api/v1/search/index/info

# 删除索引（危险！）
DELETE /api/v1/search/index/delete

# 重建索引（危险！）
POST /api/v1/search/index/recreate?use_ik=true
```

### 分词测试

```http
POST /api/v1/search/analyze
Content-Type: application/json

{
  "text": "PyTorch 深度学习优化",
  "analyzer": "chinese_smart"
}
```

### 搜索对比

```http
GET /api/v1/search/compare?query=PyTorch%20优化&top_k=5&use_multifield=true
```

## 权重自动调整

系统根据查询特征自动调整 KNN/BM25 权重：

| 查询类型 | KNN 权重 | BM25 权重 | 原因 |
|---------|----------|-----------|------|
| 技术术语 (PyTorch, BERT 等) | 0.3 | 0.7 | 需要精确匹配 |
| 问句 (如何、什么、为什么) | 0.7 | 0.3 | 需要语义理解 |
| 长查询 (>50字符) | 0.7 | 0.3 | 需要语义理解 |
| 默认 | 0.5 | 0.5 | 平衡 |

## IK 分词器安装

IK 分词器用于中文分词，需要单独安装：

```bash
# 进入 ES 目录
cd elasticsearch-9.2.0

# 安装 IK 插件（版本需匹配）
./bin/elasticsearch-plugin install \
  https://github.com/infinilabs/analysis-ik/releases/download/v9.2.0/elasticsearch-analysis-ik-9.2.0.zip

# 重启 Elasticsearch
./bin/elasticsearch
```

### 验证安装

```bash
# 测试 IK 分词
curl -X POST "localhost:9200/_analyze" \
  -H 'Content-Type: application/json' \
  -u elastic:your_password \
  -d '{"tokenizer": "ik_smart", "text": "深度学习模型优化"}'
```

## 测试

### Mock 测试（无需外部服务）

```bash
cd backend
source ../venv/bin/activate
python tests/test_search_mock.py
```

### 集成测试（需要 ES）

```bash
# 启动 Elasticsearch
./elasticsearch-9.2.0/bin/elasticsearch

# 运行多字段测试
python tests/test_multifield_search.py
```

## 文件结构

```
backend/
├── app/
│   ├── api/
│   │   └── search.py              # API 接口
│   ├── core/
│   │   ├── search_config.py       # 配置管理
│   │   └── es_index_config.py     # 索引配置
│   ├── services/
│   │   ├── search.py              # 搜索逻辑
│   │   └── elasticsearch_service.py  # ES 操作
│   └── schemas/
│       └── search.py              # 请求/响应模型
├── tests/
│   ├── test_search_mock.py        # Mock 测试
│   └── test_multifield_search.py  # 集成测试
└── docs/
    ├── MULTIFIELD_SEARCH_EN.md    # 英文文档
    └── MULTIFIELD_SEARCH_CN.md    # 本文档
```

## 常见问题

### 1. IK 插件未找到

如果未安装 IK 插件，系统会自动降级到 standard 分词器：

```
⚠️ IK plugin not available, using standard analyzer
```

**解决方案**：按照上述步骤安装 IK 插件。

### 2. 中文搜索效果差

1. 检查 IK 是否安装：`GET /api/v1/search/index/info`
2. 测试分词效果：`POST /api/v1/search/analyze`
3. 重建索引：`POST /api/v1/search/index/recreate?use_ik=true`

### 3. 英文词干匹配不工作

确保使用 `textContent.english` 字段：

```json
{
  "match": {
    "textContent.english": "optimizing"
  }
}
```

这样可以匹配 "optimize", "optimizer", "optimization" 等。

### 4. 搜索结果不准确

1. 调整权重比例（KNN vs BM25）
2. 调整字段权重（chinese vs english vs standard）
3. 尝试不同的搜索模式（hybrid/knn/bm25）

## 性能优化建议

1. **适当的 top_k**：不要设置过大的 top_k，推荐 10-50
2. **使用过滤**：通过 `file_md5` 过滤可以显著提升性能
3. **合理的权重**：根据内容特点调整 KNN/BM25 权重
4. **索引优化**：定期优化 ES 索引

## 后续扩展

1. **用户权重预设**：提供"专业知识库"、"语义知识库"等预设配置
2. **数据库存储权重**：支持用户自定义权重并持久化
3. **A/B 测试**：支持不同权重配置的效果对比
4. **查询日志**：记录搜索行为用于优化

