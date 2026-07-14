-- Domain Details Table
CREATE TABLE IF NOT EXISTS domain_details (
    domain VARCHAR(255) PRIMARY KEY NOT NULL UNIQUE,
    smtp_server VARCHAR(255) NOT NULL,
    smtp_port INTEGER NOT NULL CHECK(smtp_port BETWEEN 1 AND 65535),
    imap_server VARCHAR(255) NOT NULL,
    imap_port INTEGER NOT NULL CHECK(imap_port BETWEEN 1 AND 65535),
    sieve_server VARCHAR(255) NOT NULL,
    sieve_port INTEGER NOT NULL CHECK(sieve_port BETWEEN 1 AND 65535),
    is_active BOOLEAN DEFAULT TRUE,
    is_v2_user BOOLEAN DEFAULT FALSE,  -- Flag to indicate if the domain is using V2 Admin (On our servers) or not (External Domains)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Indexes for quicker lookups by domain
    CONSTRAINT smtp_port_range CHECK (smtp_port BETWEEN 1 AND 65535),
    CONSTRAINT imap_port_range CHECK (imap_port BETWEEN 1 AND 65535),
    CONSTRAINT sieve_port_range CHECK (sieve_port BETWEEN 1 AND 65535)
);

-- Index on domain for faster reference lookups in the users table
CREATE INDEX IF NOT EXISTS idx_domain ON domain_details(domain);

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    email VARCHAR(255) PRIMARY KEY NOT NULL UNIQUE,
    domain VARCHAR(255) NOT NULL,
    settings TEXT,  -- If you really need dynamic settings, consider using TEXT, but not ideal for structured data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (domain) REFERENCES domain_details(domain) ON DELETE CASCADE
);

-- Index on email for quick lookup of users
CREATE INDEX IF NOT EXISTS idx_email ON users(email);

-- Users Contacts Table
CREATE TABLE IF NOT EXISTS user_contacts (
    contact_id SERIAL PRIMARY KEY,
    user_email VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_user FOREIGN KEY (user_email) REFERENCES users(email) ON DELETE CASCADE,
    CONSTRAINT unique_user_contact_email UNIQUE (user_email, email)
);

-- Optional index for performance on user_email lookups
CREATE INDEX IF NOT EXISTS idx_user_contacts_user_email ON user_contacts(user_email);

-- Index on contact_email for faster searches
CREATE INDEX IF NOT EXISTS idx_contact_email ON user_contacts(email);

-- Index on contact_id for faster edits and deletes
CREATE INDEX IF NOT EXISTS idx_contact_id ON user_contacts(contact_id);

-- Email Templates
CREATE TABLE IF NOT EXISTS email_templates (
    template_id SERIAL PRIMARY KEY,
    domain VARCHAR(255) NOT NULL,
    created_by VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    is_public BOOLEAN DEFAULT FALSE,    -- All from same domain can access if true
    data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_created_by FOREIGN KEY (created_by) REFERENCES users(email) ON DELETE CASCADE,
    CONSTRAINT fk_domain FOREIGN KEY (domain) REFERENCES domain_details(domain) ON DELETE CASCADE
);

-- Index on domain for faster lookups
CREATE INDEX IF NOT EXISTS idx_email_templates_domain ON email_templates(domain);

-- Search index for name
CREATE INDEX IF NOT EXISTS idx_email_templates_name ON email_templates(name);

-- Index on template_id for faster edits and deletes
CREATE INDEX IF NOT EXISTS idx_email_templates_id ON email_templates(template_id);
