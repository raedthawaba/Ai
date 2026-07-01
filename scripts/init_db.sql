-- ══════════════════════════════════════════════════════════════════════════════
-- Hajeen AI Platform — PostgreSQL Initialization
-- ══════════════════════════════════════════════════════════════════════════════

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id            VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
    username      VARCHAR(100) UNIQUE NOT NULL,
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    roles         JSONB        DEFAULT '[]',
    tenant_id     VARCHAR(100) NOT NULL DEFAULT 'default',
    is_active     BOOLEAN      DEFAULT TRUE,
    created_at    DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW()),
    updated_at    DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW()),
    last_login_at DOUBLE PRECISION,
    metadata      JSONB        DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_users_username   ON users(username);
CREATE INDEX IF NOT EXISTS ix_users_tenant     ON users(tenant_id);
CREATE INDEX IF NOT EXISTS ix_users_email      ON users(email);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id         VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id    VARCHAR(36)  REFERENCES users(id) ON DELETE CASCADE,
    tenant_id  VARCHAR(100) NOT NULL DEFAULT 'default',
    jti        VARCHAR(36)  UNIQUE NOT NULL,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    created_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW()),
    expires_at DOUBLE PRECISION NOT NULL,
    is_active  BOOLEAN DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_sessions_jti      ON sessions(jti);
CREATE INDEX IF NOT EXISTS ix_sessions_user     ON sessions(user_id, is_active);

-- API Keys table
CREATE TABLE IF NOT EXISTS api_keys (
    id           VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
    key_id       VARCHAR(32)  UNIQUE NOT NULL,
    key_hash     VARCHAR(64)  UNIQUE NOT NULL,
    name         VARCHAR(200) NOT NULL,
    user_id      VARCHAR(36)  REFERENCES users(id) ON DELETE CASCADE,
    tenant_id    VARCHAR(100) NOT NULL DEFAULT 'default',
    scopes       JSONB        DEFAULT '[]',
    is_active    BOOLEAN      DEFAULT TRUE,
    created_at   DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW()),
    expires_at   DOUBLE PRECISION,
    last_used_at DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS ix_api_keys_id   ON api_keys(key_id);
CREATE INDEX IF NOT EXISTS ix_api_keys_hash ON api_keys(key_hash);

-- Audit Log table
CREATE TABLE IF NOT EXISTS audit_log (
    id            VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
    event_id      VARCHAR(36)  UNIQUE NOT NULL,
    action        VARCHAR(100) NOT NULL,
    actor_id      VARCHAR(100) NOT NULL,
    tenant_id     VARCHAR(100) NOT NULL DEFAULT 'default',
    resource      VARCHAR(500),
    ip_address    VARCHAR(45),
    user_agent    VARCHAR(500),
    status        VARCHAR(20)  NOT NULL DEFAULT 'success',
    details       JSONB        DEFAULT '{}',
    hash          VARCHAR(64),
    previous_hash VARCHAR(64),
    timestamp     DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW()),
    duration_ms   DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS ix_audit_action    ON audit_log(action);
CREATE INDEX IF NOT EXISTS ix_audit_actor     ON audit_log(actor_id);
CREATE INDEX IF NOT EXISTS ix_audit_tenant_ts ON audit_log(tenant_id, timestamp);

-- Conversations table
CREATE TABLE IF NOT EXISTS conversations (
    id         VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
    session_id VARCHAR(100) UNIQUE NOT NULL,
    user_id    VARCHAR(36)  REFERENCES users(id) ON DELETE CASCADE,
    tenant_id  VARCHAR(100) NOT NULL DEFAULT 'default',
    title      VARCHAR(500),
    language   VARCHAR(10)  DEFAULT 'ar',
    created_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW()),
    updated_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW()),
    metadata   JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_conversations_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS ix_conversations_user    ON conversations(user_id);

-- Messages table
CREATE TABLE IF NOT EXISTS messages (
    id              VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    conversation_id VARCHAR(36) REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL,
    content         TEXT        NOT NULL,
    model           VARCHAR(100),
    provider        VARCHAR(50),
    tokens_used     INTEGER,
    latency_ms      DOUBLE PRECISION,
    created_at      DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW()),
    sources         JSONB DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS ix_messages_conv_ts ON messages(conversation_id, created_at);

-- Vector Documents table
CREATE TABLE IF NOT EXISTS vector_documents (
    id          VARCHAR(36)   PRIMARY KEY DEFAULT gen_random_uuid()::text,
    doc_id      VARCHAR(200)  UNIQUE NOT NULL,
    title       VARCHAR(1000),
    content     TEXT          NOT NULL,
    source_url  VARCHAR(2000),
    channel_id  VARCHAR(100),
    tenant_id   VARCHAR(100)  NOT NULL DEFAULT 'default',
    language    VARCHAR(10)   DEFAULT 'ar',
    indexed_at  DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW()),
    metadata    JSONB         DEFAULT '{}',
    chunk_count INTEGER       DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_vector_docs_doc_id  ON vector_documents(doc_id);
CREATE INDEX IF NOT EXISTS ix_vector_docs_channel ON vector_documents(channel_id);
CREATE INDEX IF NOT EXISTS ix_vector_docs_tenant  ON vector_documents(tenant_id);

-- Default admin user (password: HajeenAdmin2024!)
-- hash = sha256('hajeen-salt-change-me' + 'HajeenAdmin2024!')
INSERT INTO users (id, username, email, password_hash, roles, tenant_id)
VALUES (
    'usr_admin_default',
    'admin',
    'admin@hajeen.ai',
    '__admin_placeholder__',
    '["superadmin"]',
    'default'
) ON CONFLICT (username) DO NOTHING;

COMMENT ON TABLE users           IS 'مستخدمو المنصة';
COMMENT ON TABLE sessions        IS 'جلسات JWT النشطة';
COMMENT ON TABLE api_keys        IS 'مفاتيح API بتجزئة SHA3';
COMMENT ON TABLE audit_log       IS 'سجل تدقيق لا يقبل التلاعب';
COMMENT ON TABLE conversations   IS 'جلسات المحادثة مع الذكاء الاصطناعي';
COMMENT ON TABLE messages        IS 'رسائل المحادثة';
COMMENT ON TABLE vector_documents IS 'المستندات المفهرسة في Vector Store';
