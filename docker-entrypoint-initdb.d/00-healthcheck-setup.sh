#!/bin/bash
set -e

# healthcheck용 스크립트 생성 (환경변수 사용)
cat > /usr/local/bin/healthcheck.sh << EOF
#!/bin/bash
pg_isready -U \${POSTGRES_USER:-postgres}
EOF

chmod +x /usr/local/bin/healthcheck.sh
