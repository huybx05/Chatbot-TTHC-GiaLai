# Triển khai TTHC Gia Lai lên VPS + Cloudflare

Tài liệu này hướng dẫn triển khai hệ thống với:

```text
Tên miền:        tthc-gialai.id.vn
Client:          chat.tthc-gialai.id.vn
Admin:           admin.tthc-gialai.id.vn
VPS:             103.199.11.73
VPS:             4 vCPU / 8 GB RAM / 50 GB SSD
Kiến trúc:       Docker Compose + Cloudflare Tunnel
```

Mục tiêu:

```text
- Không mở port 80/443 ra Internet
- Không lộ IP VPS
- Client và admin tách subdomain
- Admin được bảo vệ thêm bởi Cloudflare Access
- RAM được giới hạn theo từng container
```

---

# 0. Kiểm tra IP VPS

SSH vào VPS:

```bash
ssh root@103.199.11.73
```

Khi được hỏi, nhập mật khẩu root.

> Không ghi mật khẩu root vào file `.md`, script hay Git.
> Mật khẩu chỉ nhập tại prompt SSH.

Kiểm tra IP công khai:

```bash
curl -4 ifconfig.me
```

Nếu kết quả là:

```text
103.199.11.73
```

thì VPS có IPv4 công khai.

Nếu kết quả là IP private:

```text
10.x.x.x
172.16.x.x
192.168.x.x
```

thì **bắt buộc dùng Cloudflare Tunnel** hoặc NAT của nhà cung cấp.

Khuyến nghị cho dự án này:

```text
Dùng Cloudflare Tunnel
```

---

# 1. Chuẩn bị VPS

## 1.1 Cập nhật hệ điều hành

Giả sử Ubuntu 22.04/24.04:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y curl ca-certificates gnupg git ufw
```

## 1.2 Tạo user triển khai

```bash
sudo adduser deploy
sudo usermod -aG sudo deploy
```

Copy SSH key sang user mới:

```bash
sudo mkdir -p /home/deploy/.ssh
sudo cp ~/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
sudo chown -R deploy:deploy /home/deploy/.ssh
sudo chmod 700 /home/deploy/.ssh
sudo chmod 600 /home/deploy/.ssh/authorized_keys
```

Đăng nhập lại:

```bash
ssh deploy@103.199.11.73
```

## 1.3 Cấu hình SSH

Mở:

```bash
sudo nano /etc/ssh/sshd_config
```

Đặt:

```text
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```

Kiểm tra cấu hình:

```bash
sudo sshd -t
sudo systemctl restart ssh
```

> Giữ phiên SSH hiện tại mở cho đến khi đăng nhập lại thành công.

## 1.4 Firewall

Chỉ mở SSH:

```bash
sudo ufw allow 22/tcp
sudo ufw enable
sudo ufw status
```

Không mở:

```text
80
443
5432
6379
6333
7474
7687
9200
```

Cloudflare Tunnel sẽ tự kết nối ra ngoài, không cần inbound 80/443.

## 1.5 Swap 2 GB

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Kiểm tra:

```bash
free -h
```

## 1.6 Sysctl cho Elasticsearch/Neo4j

```bash
sudo sysctl -w vm.max_map_count=262144
echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf
```

Có thể thêm:

```bash
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
```

---

# 2. Cài Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy
```

Đăng xuất rồi đăng nhập lại:

```bash
exit
ssh deploy@103.199.11.73
```

Kiểm tra:

```bash
docker --version
docker compose version
```

Kiểm tra quyền Docker của user:

```bash
groups
docker info
```

Kỳ vọng `groups` có:

```text
deploy sudo users docker
```

Nếu `docker info` báo:

```text
permission denied while trying to connect to the Docker daemon socket
```

thì thêm user vào group `docker` và đăng nhập lại:

```bash
sudo usermod -aG docker deploy
newgrp docker
# hoặc logout rồi ssh lại
```

Kiểm tra lại:

```bash
docker info
```

## Nếu xóa và tạo lại user `deploy`

```bash
sudo adduser deploy
sudo usermod -aG sudo deploy
sudo usermod -aG docker deploy
```

Sau đó copy SSH key và đăng nhập lại:

```bash
sudo mkdir -p /home/deploy/.ssh
sudo cp /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
sudo chown -R deploy:deploy /home/deploy/.ssh
sudo chmod 700 /home/deploy/.ssh
sudo chmod 600 /home/deploy/.ssh/authorized_keys

ssh deploy@103.199.11.73
```

Kiểm tra:

```bash
id deploy
groups
docker info
```

---

# 3. Đưa code lên VPS

## 3.1 Clone repository

```bash
sudo mkdir -p /opt/tra_cuu_tthc
sudo chown deploy:deploy /opt/tra_cuu_tthc
git clone <REPO_URL> /opt/tra_cuu_tthc
cd /opt/tra_cuu_tthc
```

## 3.2 Tạo file `.env`

```bash
nano .env
chmod 600 .env
```

Nội dung tối thiểu:

```env
APP_ENV=production
DEBUG=False
FORCE_HTTPS=False
LOG_LEVEL=INFO
API_V1_PREFIX=/api/v1

ALLOWED_HOSTS=chat.tthc-gialai.id.vn,admin.tthc-gialai.id.vn
CORS_ORIGINS=https://chat.tthc-gialai.id.vn,https://admin.tthc-gialai.id.vn

SECRET_KEY=<chuỗi-random-64-byte>
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=30
MAX_FAILED_ATTEMPTS=5
LOCKOUT_MINUTES=15

POSTGRES_ADMIN_PASSWORD=<mật-khẩu-admin-postgres>
DATABASE_DB=chatbot_tthc
DATABASE_USER=chatbot_app
DATABASE_PASSWORD=<mật-khẩu-app>
DATABASE_URL=postgresql+psycopg://chatbot_app:<mật-khẩu-app>@postgres:5432/chatbot_tthc

REDIS_PASSWORD=<mật-khẩu-redis>
REDIS_URL=redis://:<mật-khẩu-redis>@redis:6379/0

NEO4J_URL=neo4j://neo4j:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<mật-khẩu-neo4j>
NEO4J_DATABASE=neo4j
NEO4J_RUN_ID=full

ELASTICSEARCH_HOST=http://elasticsearch:9200
QDRANT_HOST=http://qdrant:6333

S3_ENDPOINT=http://localhost:8333
S3_ENDPOINT_DOCKER=http://s3:8333
S3_BUCKET=procedure-documents
S3_ACCESS_KEY=<access-key-trong-s3.json>
S3_SECRET_KEY=<secret-key-trong-s3.json>
S3_REGION=ap-southeast-1

CLOUDFLARE_TUNNEL_TOKEN=<token-tunnel>

QWEN_BASE_URL=<...>
QWEN_API_KEY=<...>
DEEPSEEK_BASE_URL=<...>
DEEPSEEK_API_KEY=<...>
```

Sinh khóa:

```bash
openssl rand -base64 48
```

Dùng kết quả cho `SECRET_KEY`.

> Không commit `.env` lên Git.

## 3.3 Kiểm tra cấu hình Compose

```bash
docker compose -f docker-compose.prod.yml config
```

Nếu báo thiếu biến, kiểm tra lại `.env`.

## 3.4 Tạo cấu hình SeaweedFS S3

Compose mount file này vào container:

```text
/opt/seaweedfs/s3.json
```

Tạo thư mục:

```bash
sudo mkdir -p /opt/seaweedfs
sudo chown deploy:deploy /opt/seaweedfs
```

Sinh key:

```bash
openssl rand -hex 16
openssl rand -hex 32
```

Tạo file:

```bash
nano /opt/seaweedfs/s3.json
```

Nội dung:

```json
{
  "identities": [
    {
      "name": "tthc",
      "credentials": [
        {
          "accessKey": "<ACCESS_KEY>",
          "secretKey": "<SECRET_KEY>"
        }
      ],
      "actions": [
        "Admin",
        "Read",
        "Write"
      ]
    }
  ]
}
```

Phân quyền:

```bash
chmod 600 /opt/seaweedfs/s3.json
```

Hai giá trị `<ACCESS_KEY>` và `<SECRET_KEY>` phải trùng với:

```env
S3_ACCESS_KEY=<ACCESS_KEY>
S3_SECRET_KEY=<SECRET_KEY>
```

Nếu file này không tồn tại, service `s3` sẽ không khởi động được.

---

# 4. Build image

```bash
docker compose -f docker-compose.prod.yml build
```

Kiểm tra:

```bash
docker images | grep tracuutthc
```

---

# 5. Khởi động hạ tầng

## 5.1 Đồng bộ phiên bản với local

`docker-compose.prod.yml` đang pin:

```text
postgres:18-alpine
elasticsearch:9.5.4
qdrant:v1.19.0
seaweedfs:4.50
```

Nếu VPS đang có volume tạo bởi phiên bản cũ:

```text
PostgreSQL 16
Elasticsearch 8
Qdrant 1.15
```

thì **không được dùng lại volume cũ** với image mới.

Với VPS mới hoặc dữ liệu chưa cần giữ:

```bash
docker compose -f docker-compose.prod.yml down

docker volume rm \
  tracuutthc_postgres-data \
  tracuutthc_elasticsearch-data \
  tracuutthc_qdrant-data
```

Không xóa các volume sau nếu muốn giữ dữ liệu:

```text
tracuutthc_seaweedfs-data
tracuutthc_neo4j-data
tracuutthc_neo4j-logs
```

Nếu có dữ liệu cần giữ, phải dump/backup trước rồi restore sau.

> PostgreSQL 18 dùng volume `/var/lib/postgresql`, không phải
> `/var/lib/postgresql/data`. Compose đã cấu hình đúng; nếu tự sửa file,
> giữ nguyên mount này.

Khởi động database, search store và SeaweedFS trước:

```bash
docker compose -f docker-compose.prod.yml up -d \
  postgres redis qdrant neo4j elasticsearch s3
```

Kiểm tra:

```bash
docker compose -f docker-compose.prod.yml ps
docker stats
```

Xem log nếu có lỗi:

```bash
docker compose -f docker-compose.prod.yml logs -f postgres
docker compose -f docker-compose.prod.yml logs -f elasticsearch
docker compose -f docker-compose.prod.yml logs -f neo4j
```

---

# 6. Khởi tạo database và đưa dữ liệu lên

## 6.0 Dữ liệu nào đi vào đâu?

| Dữ liệu | Đích | Bước |
|---|---|---|
| Thủ tục, chunk, FAQ, tài liệu metadata | PostgreSQL | Bước 6 |
| File PDF/Word đính kèm | S3/SeaweedFS | Bước 6C |
| Đồ thị tri thức | Neo4j | Bước 9 |
| Chỉ mục tìm kiếm BM25 | Elasticsearch | Bước 10 |
| Vector embedding | Qdrant | Bước 10 |
| File `data/json_normalized` | Chỉ dùng để rebuild, không cần runtime | Tùy chọn |

Điểm quan trọng:

```text
Dữ liệu KHÔNG nằm trong Docker image.
Dữ liệu phải được restore/import vào database và các store.
```

Có 2 cách:

```text
6A. Database mới → tạo schema rỗng, sau đó chạy pipeline/import
6B. Có dữ liệu local → dump/restore PostgreSQL
```

Khuyến nghị với dự án hiện tại:

```text
Dùng 6B để đưa dữ liệu đã crawl/index lên VPS.
```

## 6A. Database mới hoàn toàn

Chỉ dùng khi chưa có dữ liệu.

Áp schema gốc:

```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U postgres -d chatbot_tthc -v ON_ERROR_STOP=1 < config/schema.sql
```

Áp migrations:

```bash
for f in db/migrations/*.sql; do
  echo "Applying $f"
  docker compose -f docker-compose.prod.yml exec -T postgres \
    psql -U postgres -d chatbot_tthc -v ON_ERROR_STOP=1 < "$f"
done
```

Sau đó vẫn phải nạp dữ liệu thủ tục/FAQ bằng pipeline hoặc import.

## 6B. Phục hồi dữ liệu từ local

### Cách khuyến nghị: chỉ dump dữ liệu nghiệp vụ

Không mang theo chat log, session, audit log test từ local.

Trên máy local:

```powershell
pg_dump `
  -h localhost `
  -U postgres `
  -d chatbot_tthc `
  -Fc `
  -t procedures `
  -t procedure_agencies `
  -t procedure_sections `
  -t procedure_documents `
  -t procedure_time_cases `
  -t procedure_themes `
  -t faq `
  -t ai_models `
  -t ai_price_versions `
  -f tthc_business.dump
```

Giải thích:

```text
procedures              → thủ tục
procedure_agencies      → cơ quan
procedure_sections      → chunk
procedure_documents     → metadata file đính kèm
procedure_time_cases    → thời hạn theo case
procedure_themes        → nhóm chủ đề
faq                     → FAQ đã duyệt
ai_models/ai_price_versions → bảng giá chi phí
```

Nếu muốn giữ tài khoản người dùng hiện có, thêm:

```powershell
-t users
```

Nhưng nên tạo admin mới bằng `seed_user.py`.

> Nếu không chắc về sequence/index đi kèm khi dump chọn bảng, dùng
> **dump toàn bộ database** ở mục dưới; an toàn hơn cho lần deploy đầu.

### Copy lên VPS

```powershell
scp tthc_business.dump deploy@103.199.11.73:/opt/tra_cuu_tthc/
```

Trên VPS:

```bash
cd /opt/tra_cuu_tthc

docker compose -f docker-compose.prod.yml cp \
  tthc_business.dump postgres:/tmp/tthc_business.dump

docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_restore -U postgres -d chatbot_tthc \
  --clean --if-exists --no-owner --no-privileges \
  /tmp/tthc_business.dump
```

### Nếu muốn dump toàn bộ database

```powershell
pg_dump -h localhost -U postgres -d chatbot_tthc -Fc -f chatbot_tthc_full.dump
```

Cách này mang theo cả:

```text
users
sessions
chat_sessions
chat_messages
audit_logs
```

Chỉ dùng nếu thật sự muốn giữ lịch sử chat và tài khoản.

## 6C. File đính kèm (PDF/Word) với SeaweedFS

PostgreSQL chỉ lưu metadata trong `procedure_documents`.

File thật nằm ở SeaweedFS S3 gateway, service `s3` trong compose.

### Cấu hình

Trong `.env`:

```env
S3_ENDPOINT=http://localhost:8333
S3_ENDPOINT_DOCKER=http://s3:8333
S3_BUCKET=procedure-documents
S3_ACCESS_KEY=<access-key-trong-/opt/seaweedfs/s3.json>
S3_SECRET_KEY=<secret-key-trong-/opt/seaweedfs/s3.json>
S3_REGION=ap-southeast-1
```

Service `s3` và backend cùng network `data`, nên backend gọi:

```text
http://s3:8333
```

Không mở port 8333 ra Internet.

### Tạo bucket

Chạy từ container backend:

```bash
docker compose -f docker-compose.prod.yml exec -T backend \
  python -c "import boto3, os; s=boto3.client('s3', endpoint_url='http://s3:8333', aws_access_key_id=os.environ['S3_ACCESS_KEY'], aws_secret_access_key=os.environ['S3_SECRET_KEY'], region_name='ap-southeast-1'); s.create_bucket(Bucket='procedure-documents')"
```

Nếu bucket đã tồn tại, lệnh có thể báo `BucketAlreadyOwnedByYou`; bỏ qua.

### Copy file lên SeaweedFS

Cách đơn giản: chạy một container AWS CLI tạm trong cùng network:

```bash
docker run --rm \
  --network tracuutthc_data \
  -e AWS_ACCESS_KEY_ID=<access-key> \
  -e AWS_SECRET_ACCESS_KEY=<secret-key> \
  -v "$PWD/duong-dan-file:/data:ro" \
  amazon/aws-cli \
  s3 sync /data s3://procedure-documents \
  --endpoint-url http://s3:8333 \
  --region ap-southeast-1
```

Nếu chưa cần tải tài liệu, có thể bỏ qua bước này lúc deploy ban đầu.


---

# 7. Tạo role ứng dụng ít quyền

```bash
docker compose -f docker-compose.prod.yml run --rm --no-deps \
  -e DATABASE_ADMIN_URL="postgresql://postgres:<POSTGRES_ADMIN_PASSWORD>@postgres:5432/chatbot_tthc" \
  -e APP_DB_PASSWORD="<DATABASE_PASSWORD>" \
  backend python scripts/create_app_db_role.py \
  --apply --role chatbot_app
```

Kiểm tra:

```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U postgres -d chatbot_tthc -c "\du chatbot_app"
```

---

# 8. Khởi động backend và frontend

```bash
docker compose -f docker-compose.prod.yml up -d backend frontend
```

Kiểm tra:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend
```

Test nội bộ bằng Host header:

```bash
curl -H "Host: chat.tthc-gialai.id.vn" http://127.0.0.1:8080/health
curl -H "Host: admin.tthc-gialai.id.vn" http://127.0.0.1:8080/health
```

Kỳ vọng:

```json
{"status":"ok"}
```

Kiểm tra redirect:

```bash
curl -I -H "Host: chat.tthc-gialai.id.vn" http://127.0.0.1:8080/admin
```

Kỳ vọng:

```text
302 → https://admin.tthc-gialai.id.vn/admin
```

Kiểm tra chặn API admin ở client:

```bash
curl -i -H "Host: chat.tthc-gialai.id.vn" \
  http://127.0.0.1:8080/api/admin/system/status
```

Kỳ vọng:

```text
404
```

---

# 9. Phục hồi / xây lại Neo4j

Nếu database đã có dữ liệu nhưng Neo4j mới rỗng:

```bash
docker compose -f docker-compose.prod.yml exec -T backend \
  python -m data_pipeline.indexing.neo4j \
  --from-postgres \
  --database neo4j \
  --run-id full \
  --wipe
```

Kiểm tra:

```cypher
MATCH (p:ThuTuc {run_id:"full"}) RETURN count(p);
```

Kỳ vọng:

```text
1869
```

> Docker Compose dùng Neo4j Community, database mặc định là `neo4j`.
> Nếu dùng Neo4j Enterprise và muốn database tên `chatbot`, đổi
> `NEO4J_DATABASE=chatbot` trong compose và tạo database tương ứng.

---

# 10. Phục hồi / xây lại Elasticsearch và Qdrant

Nếu chưa có snapshot:

```bash
docker compose -f docker-compose.prod.yml exec -T backend \
  python scripts/index_search_stores.py --target all --recreate
```

Lưu ý:

```text
- Elasticsearch reindex không tốn embedding
- Qdrant reindex sẽ gọi model embedding và tốn chi phí
- Không chạy lặp lại nếu không cần
```

Kiểm tra:

```bash
docker compose -f docker-compose.prod.yml exec -T backend \
  python -c "from backend.app.config import settings; from qdrant_client import QdrantClient; q=QdrantClient(url=settings.qdrant_host); print(q.get_collection('semantic_search').points_count)"
```

---

# 11. Cấu hình Cloudflare

Chỉ làm bước này sau khi hệ thống nội bộ đã chạy ổn.

## 11.1 Đưa domain vào Cloudflare

Tại nhà đăng ký `tthc-gialai.id.vn`:

```text
Đổi nameserver sang nameserver Cloudflare cung cấp
```

Chờ Cloudflare xác nhận domain active.

## 11.2 Tạo Tunnel

Vào:

```text
Cloudflare Zero Trust
→ Networks
→ Tunnels
→ Create a tunnel
→ Cloudflared
```

Đặt tên:

```text
tthc-gialai
```

Copy token.

Trong `.env`:

```env
CLOUDFLARE_TUNNEL_TOKEN=<token>
```

## 11.3 Public Hostname

Trong Tunnel → Public Hostname, thêm:

```text
Hostname: chat.tthc-gialai.id.vn
Service: http://frontend:80
HTTP Host Header: chat.tthc-gialai.id.vn
```

```text
Hostname: admin.tthc-gialai.id.vn
Service: http://frontend:80
HTTP Host Header: admin.tthc-gialai.id.vn
```

> `HTTP Host Header` là bắt buộc. Nếu thiếu, Nginx có thể trả nhầm giao diện client.

## 11.4 Chạy tunnel

```bash
cd /opt/tra_cuu_tthc
docker compose -f docker-compose.prod.yml --profile tunnel up -d
```

Kiểm tra:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f cloudflared
```

---

# 12. Cấu hình Cloudflare sau khi có tunnel

## SSL/TLS

```text
SSL/TLS → Overview
→ Full (strict)
```

Nếu Cloudflare báo lỗi certificate với tunnel, dùng:

```text
Full
```

Không dùng:

```text
Flexible
```

## Always Use HTTPS

```text
SSL/TLS → Edge Certificates
→ Always Use HTTPS: On
→ Automatic HTTPS Rewrites: On
→ Minimum TLS Version: 1.2
```

## HSTS

Bật sau khi đã kiểm tra HTTPS ổn định:

```text
Strict Transport Security
max-age=31536000
includeSubDomains
```

## WAF

```text
Security → WAF
→ Managed Rules: On
```

## Rate limiting

Tạo rule cho:

```text
/api/v1/auth/login
/api/v1/auth/register
/api/v1/chat
/api/v1/chat/stream
```

## Cloudflare Access cho admin

```text
Zero Trust → Access → Applications
→ Add an application
→ Self-hosted
```

Cấu hình:

```text
Application name: TTHC Admin
Domain: admin.tthc-gialai.id.vn
Policy: chỉ email nội bộ / IP allowlist
Session duration: 8h hoặc 24h
```

---

# 13. Kiểm tra sau khi trỏ domain

## DNS

```bash
dig chat.tthc-gialai.id.vn
dig admin.tthc-gialai.id.vn
```

## HTTPS

```bash
curl -I https://chat.tthc-gialai.id.vn
curl -I https://admin.tthc-gialai.id.vn
```

## Phân tách client/admin

```bash
curl -I https://chat.tthc-gialai.id.vn/admin
```

Kỳ vọng:

```text
302 → https://admin.tthc-gialai.id.vn/admin
```

```bash
curl -I https://admin.tthc-gialai.id.vn/
```

Kỳ vọng:

```text
302 → /admin
```

```bash
curl -i https://chat.tthc-gialai.id.vn/api/admin/system/status
```

Kỳ vọng:

```text
404
```

## Admin login

Mở:

```text
https://admin.tthc-gialai.id.vn/admin
```

Đăng nhập bằng tài khoản admin.

---

# 14. Tạo tài khoản admin đầu tiên

Nếu database chưa có admin:

```bash
docker compose -f docker-compose.prod.yml exec -T backend \
  python scripts/seed_user.py \
  --username admin \
  --role admin \
  --ask-password
```

Không dùng mật khẩu yếu.

---

# 15. Backup

## PostgreSQL

Tạo thư mục:

```bash
sudo mkdir -p /opt/backups/postgres
sudo chown deploy:deploy /opt/backups/postgres
```

Backup thủ công:

```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U postgres -d chatbot_tthc -Fc \
  > /opt/backups/postgres/chatbot_tthc_$(date +%F).dump
```

Cron hằng ngày:

```bash
crontab -e
```

Thêm:

```cron
0 2 * * * cd /opt/tra_cuu_tthc && docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U postgres -d chatbot_tthc -Fc > /opt/backups/postgres/chatbot_tthc_$(date +\%F).dump
```

## Neo4j

```bash
docker compose -f docker-compose.prod.yml exec -T neo4j \
  neo4j-admin database dump neo4j --to-path=/data/backups
```

## Qdrant

```bash
docker compose -f docker-compose.prod.yml exec -T qdrant \
  curl -X POST http://127.0.0.1:6333/collections/semantic_search/snapshots
```

## Elasticsearch

Dùng snapshot repository hoặc chấp nhận reindex từ PostgreSQL.

> Backup phải được lưu offsite và phải thử restore định kỳ.

---

# 16. Monitoring

Tối thiểu:

```text
- Uptime Kuma / Better Stack
- Sentry cho backend/frontend
- Alert dung lượng ổ
- Alert RAM
- Alert 5xx
- Alert container restart
```

Kiểm tra nhanh:

```bash
docker stats
docker system df
df -h
free -h
```

---

# 17. Cập nhật phiên bản mới

```bash
cd /opt/tra_cuu_tthc
git pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

Nếu chỉ đổi frontend:

```bash
docker compose -f docker-compose.prod.yml build frontend
docker compose -f docker-compose.prod.yml up -d frontend
```

Nếu chỉ đổi backend:

```bash
docker compose -f docker-compose.prod.yml build backend
docker compose -f docker-compose.prod.yml up -d backend
```

---

# 18. Xử lý lỗi thường gặp

## Backend không khởi động

```bash
docker compose -f docker-compose.prod.yml logs backend
```

Thường gặp:

```text
- Thiếu ALLOWED_HOSTS
- Thiếu CORS_ORIGINS
- Sai DATABASE_URL
- Chưa tạo role chatbot_app
```

## Frontend 502

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs frontend
docker compose -f docker-compose.prod.yml logs backend
```

## Cloudflare 502

Kiểm tra:

```text
- Tunnel có Running không
- HTTP Host Header đúng chưa
- frontend container healthy không
```

## Neo4j lỗi database

Compose dùng:

```env
NEO4J_DATABASE=neo4j
```

Nếu đổi sang `chatbot`, phải dùng Neo4j Enterprise hoặc tạo database trước.

### Neo4j unhealthy

Kiểm tra:

```bash
docker compose -f docker-compose.prod.yml logs --tail=100 neo4j
docker compose -f docker-compose.prod.yml exec -T neo4j \
  cypher-shell -u neo4j -p '<NEO4J_PASSWORD>' 'RETURN 1'
```

Nếu báo `Unauthorized` / `authentication failure`, volume Neo4j cũ có mật khẩu khác.
Reset volume Neo4j (mất đồ thị, sẽ rebuild từ PostgreSQL):

```bash
docker compose -f docker-compose.prod.yml stop neo4j
docker compose -f docker-compose.prod.yml rm -sf neo4j
docker volume rm tracuutthc_neo4j-data tracuutthc_neo4j-logs
docker compose -f docker-compose.prod.yml up -d neo4j
```

Nếu container vừa khởi động, chờ 60–90 giây rồi kiểm tra lại.

## Không đăng nhập được admin

Kiểm tra:

```text
- APP_ENV=production
- Truy cập bằng https
- Cookie Secure
- Cloudflare Access không chặn nhầm
- Tài khoản admin tồn tại
```

---

# 19. Checklist trước khi public

```text
[ ] SSH key, tắt password login
[ ] UFW chỉ mở 22
[ ] Docker chạy non-root container
[ ] .env quyền 600
[ ] SECRET_KEY mạnh
[ ] DATABASE_USER=chatbot_app, không phải postgres
[ ] Redis có mật khẩu
[ ] Neo4j có mật khẩu
[ ] ALLOWED_HOSTS đúng 2 subdomain
[ ] CORS_ORIGINS đúng 2 domain
[ ] Cloudflare Tunnel chạy
[ ] Cloudflare SSL Full (strict)
[ ] Cloudflare Access bảo vệ admin
[ ] client `/api/admin` trả 404
[ ] admin `/` chuyển `/admin`
[ ] backup PostgreSQL đã chạy thử
[ ] restore thử thành công
[ ] docker stats RAM ổn định
[ ] df -h còn dung lượng
```

---

# 20. Kết luận

Thứ tự đúng:

```text
1. Chuẩn bị VPS
2. Cài Docker
3. Đưa code + .env
4. Tạo /opt/seaweedfs/s3.json
5. Build
6. Chạy database/search/SeaweedFS
7. Khôi phục dữ liệu
8. Tạo role DB
9. Chạy backend/frontend
10. Test nội bộ bằng Host header
11. Tạo Cloudflare Tunnel
12. Trỏ domain/subdomain
13. Bật Access/WAF/rate limit
14. Backup + monitoring
```

---

# Phụ lục A — Reset VPS để deploy lại từ đầu

> Các lệnh dưới đây **xóa container, volume, image và thư mục dự án**.
> Chỉ chạy khi chắc chắn muốn làm lại từ đầu.

## A.1 Sao lưu nếu cần

```bash
sudo mkdir -p /opt/backups
cd /opt/tra_cuu_tthc 2>/dev/null && \
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U postgres -d chatbot_tthc -Fc \
  > /opt/backups/chatbot_tthc_$(date +%F).dump
```

Nếu không cần dữ liệu cũ, bỏ qua bước này.

## A.2 Dừng và xóa stack

Nếu còn file compose:

```bash
cd /opt/tra_cuu_tthc 2>/dev/null || true

docker compose --profile tunnel -f docker-compose.prod.yml \
  down -v --remove-orphans 2>/dev/null || true

docker compose -f compose.yaml \
  down -v --remove-orphans 2>/dev/null || true
```

Nếu file compose đã mất, xóa theo label project:

```bash
for project in tracuutthc chatbot-tthc-gialai; do
  ids=$(docker ps -aq --filter "label=com.docker.compose.project=$project")
  if [ -n "$ids" ]; then docker rm -f $ids; fi

  volumes=$(docker volume ls -q --filter "label=com.docker.compose.project=$project")
  if [ -n "$volumes" ]; then docker volume rm $volumes; fi

  networks=$(docker network ls -q --filter "label=com.docker.compose.project=$project")
  if [ -n "$networks" ]; then docker network rm $networks 2>/dev/null || true; fi
done
```

## A.3 Xóa image và cache

```bash
docker rmi tracuutthc-backend:latest tracuutthc-frontend:latest 2>/dev/null || true
docker builder prune -af
docker image prune -af
docker network prune -f
```

Không dùng `docker system prune --volumes` nếu VPS còn service khác.

## A.4 Xóa file dự án

Kiểm tra đường dẫn trước:

```bash
realpath /opt/tra_cuu_tthc 2>/dev/null || true
realpath /opt/seaweedfs 2>/dev/null || true
```

Sau đó:

```bash
sudo rm -rf /opt/tra_cuu_tthc
sudo rm -rf /opt/seaweedfs
```

Không xóa:

```text
/home/deploy/.ssh
/opt/backups
/etc/ssh
/etc/ufw
```

## A.5 Xóa cloudflared nếu cài systemd

```bash
sudo systemctl disable --now cloudflared 2>/dev/null || true
sudo rm -f /etc/systemd/system/cloudflared.service
sudo systemctl daemon-reload
sudo rm -rf /etc/cloudflared
```

Nếu Cloudflare Tunnel chỉ chạy trong Docker Compose, bước này không cần.

## A.6 Kiểm tra sạch

```bash
docker ps -a
docker volume ls
docker network ls
ls -la /opt
```

## A.7 Clone lại

```bash
sudo mkdir -p /opt/tra_cuu_tthc
sudo chown deploy:deploy /opt/tra_cuu_tthc
git clone <REPO_URL> /opt/tra_cuu_tthc
cd /opt/tra_cuu_tthc
```

Sau đó làm lại từ mục 3 của tài liệu này.

Lưu ý: `.env` và `/opt/seaweedfs/s3.json` **không có trong Git**, phải tạo lại hoặc copy từ nơi an toàn.




Không mở port 80/443 nếu dùng Cloudflare Tunnel.
