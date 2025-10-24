### 安装ElasticSearch（v：9.2.0）

```python
curl -O https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-9.2.0-darwin-x86_64.tar.gz
curl https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-9.2.0-darwin-x86_64.tar.gz.sha512 | shasum -a 512 -c -
tar -xzf elasticsearch-9.2.0-darwin-x86_64.tar.gz
cd elasticsearch-9.2.0/
```

**启动Elasticsearch**

```python
./bin/elasticsearch
```

当您第一次启动时，系统会：

- 生成密码和证书
- 显示初始的超级用户（elastic）密码
- 会显示以下内容：
    Elasticsearch security features have been automatically configured!

    ✅ Authentication is enabled and cluster connections are encrypted.

    ℹ️  Password for the **elastic** user (reset with `bin/elasticsearch-reset-password -u elastic`): xxxxx

**测试ES是否正确运行**

`curl -u elastic:你的密码 [https://localhost:9200](https://localhost:9200/) -k`

**安装Kibana（可视化ES）**

```python
   # 下载 Kibana（确保版本与您的 ES 版本匹配：9.2.0）
   curl -O https://artifacts.elastic.co/downloads/kibana/kibana-9.2.0-darwin-x86_64.tar.gz
   
   # 解压
   tar -xzf kibana-9.2.0-darwin-x86_64.tar.gz
   
   # 进入 Kibana 目录
   cd kibana-9.2.0
   
   # 启动 Kibana
   ./bin/kibana
```

如果您之前的 token 已经过期（超过30分钟），可以生成新的 token：

`./bin/elasticsearch-create-enrollment-token --scope kibana`
