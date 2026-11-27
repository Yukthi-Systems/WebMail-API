-- New SQL schema for Yukthi WebMail API - With SSO


-- Mail Server Configuration
CREATE TABLE mail_server_config (
    config_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    config_name VARCHAR(100) NOT NULL,

    smtp_host TEXT NOT NULL,
    smtp_port INTEGER NOT NULL CHECK(smtp_port BETWEEN 1 AND 65535),

    imap_host TEXT NOT NULL,
    imap_port INTEGER NOT NULL CHECK(imap_port BETWEEN 1 AND 65535),

    sieve_host TEXT NOT NULL,
    sieve_port INTEGER NOT NULL CHECK(sieve_port BETWEEN 1 AND 65535),

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,

    -- Indexes for quicker lookups by domain
    CONSTRAINT smtp_port_range CHECK (smtp_port BETWEEN 1 AND 65535),
    CONSTRAINT imap_port_range CHECK (imap_port BETWEEN 1 AND 65535),
    CONSTRAINT sieve_port_range CHECK (sieve_port BETWEEN 1 AND 65535)
);


-- Domain Details
CREATE TABLE domains (
    domain VARCHAR(255) PRIMARY KEY,

    -- If the domain is external, it should have a mail server configuration
    -- If the domain is internal, it will fetch from SSO API
    mail_server_config_id INTEGER REFERENCES mail_server_config(config_id),

    is_active BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);


-- Users
CREATE TABLE users (
    user_id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    domain VARCHAR(255) NOT NULL REFERENCES domains(domain) ON DELETE CASCADE,

    organization_id UUID NOT NULL,
    organization_name VARCHAR(250) NOT NULL,

    private_info JSONB NOT NULL,    -- Available only to the user themselves
    public_info JSONB NOT NULL     -- Available to all within the organization
);


-- Contacts Table
CREATE TABLE contacts (
    contact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,

    -- Basic contact information
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,

    -- Additional contact information
    phone VARCHAR(20),
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,

    UNIQUE (user_id, email)
);


-- Templates
CREATE TABLE email_templates (
    template_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain VARCHAR(255) NOT NULL REFERENCES domains(domain) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    organization_id UUID NOT NULL,

    name VARCHAR(255) NOT NULL,
    details JSONB NOT NULL,

    is_public BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,

    UNIQUE (user_id, name)
);


-- Indexes 
CREATE INDEX idx_users_domain ON users (domain);
CREATE INDEX idx_domains_mail_server_config ON domains (mail_server_config_id);
CREATE INDEX idx_contacts_user_created ON contacts (user_id, created_at DESC);
CREATE INDEX idx_templates_user_updated ON email_templates (user_id, updated_at DESC);
CREATE INDEX idx_templates_org_public ON email_templates (organization_id, updated_at DESC) WHERE is_public;
