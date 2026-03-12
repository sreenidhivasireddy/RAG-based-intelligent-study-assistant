### Install Elasticsearch (v9.2.0)

```bash
curl -O https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-9.2.0-darwin-x86_64.tar.gz
curl https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-9.2.0-darwin-x86_64.tar.gz.sha512 | shasum -a 512 -c -
tar -xzf elasticsearch-9.2.0-darwin-x86_64.tar.gz
cd elasticsearch-9.2.0/
```

**Start Elasticsearch**

```bash
./bin/elasticsearch
```

On first startup Elasticsearch will:
- generate passwords and certificates
- print the initial `elastic` superuser password

**Verify the server**

```bash
curl -u elastic:YOUR_PASSWORD https://localhost:9200 -k
```

**Install Kibana**

```bash
curl -O https://artifacts.elastic.co/downloads/kibana/kibana-9.2.0-darwin-x86_64.tar.gz
tar -xzf kibana-9.2.0-darwin-x86_64.tar.gz
cd kibana-9.2.0
./bin/kibana
```

If your Kibana enrollment token expired, generate a new one:

```bash
./bin/elasticsearch-create-enrollment-token --scope kibana
```
