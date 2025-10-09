CREATE TABLE alembic_version (
	version_num VARCHAR(32) NOT NULL, 
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
CREATE TABLE stories (
	id INTEGER NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	author VARCHAR(255) NOT NULL, 
	description TEXT, 
	content TEXT NOT NULL, 
	cover_filename VARCHAR(255), 
	created_at DATETIME, 
	updated_at DATETIME, s3_cover_key VARCHAR(512), 
	PRIMARY KEY (id)
);
CREATE TABLE users (
	id INTEGER NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	email_confirmed BOOLEAN, 
	is_active BOOLEAN, 
	last_login DATETIME, 
	created_at DATETIME, 
	updated_at DATETIME, is_admin BOOLEAN, credits_balance INTEGER DEFAULT '0' NOT NULL, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_users_email ON users (email);
CREATE TABLE IF NOT EXISTS "voices" (
	id INTEGER NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	elevenlabs_voice_id VARCHAR(255), 
	s3_sample_key VARCHAR(512), 
	sample_filename VARCHAR(255), 
	user_id INTEGER NOT NULL, 
	created_at DATETIME, 
	updated_at DATETIME, 
	status VARCHAR(20) NOT NULL, 
	error_message TEXT, 
	PRIMARY KEY (id), 
	UNIQUE (elevenlabs_voice_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE IF NOT EXISTS "audio_stories" (
	id INTEGER NOT NULL, 
	story_id INTEGER NOT NULL, 
	voice_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	error_message TEXT, 
	s3_key VARCHAR(512), 
	duration_seconds FLOAT, 
	file_size_bytes INTEGER, 
	created_at DATETIME, 
	updated_at DATETIME, credits_charged INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(story_id) REFERENCES stories (id), 
	FOREIGN KEY(voice_id) REFERENCES voices (id)
);
CREATE TABLE credit_transactions (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	amount INTEGER NOT NULL, 
	type VARCHAR(20) NOT NULL, 
	reason VARCHAR(255), 
	audio_story_id INTEGER, 
	story_id INTEGER, 
	status VARCHAR(20) DEFAULT 'applied' NOT NULL, 
	metadata JSON, 
	created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(audio_story_id) REFERENCES audio_stories (id) ON DELETE SET NULL, 
	FOREIGN KEY(story_id) REFERENCES stories (id) ON DELETE SET NULL
);
CREATE INDEX ix_credit_transactions_story_id ON credit_transactions (story_id);
CREATE INDEX ix_credit_transactions_user_id ON credit_transactions (user_id);
CREATE INDEX ix_credit_transactions_audio_story_id ON credit_transactions (audio_story_id);
CREATE UNIQUE INDEX uq_credit_tx_open_debit
            ON credit_transactions (audio_story_id, user_id)
            WHERE type = 'debit' AND status = 'applied'
        ;
CREATE TABLE credit_lots (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	source VARCHAR(20) NOT NULL, 
	amount_granted INTEGER NOT NULL, 
	amount_remaining INTEGER NOT NULL, 
	expires_at DATETIME, 
	created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX ix_credit_lots_user_id ON credit_lots (user_id);
CREATE INDEX ix_credit_lots_user_expires ON credit_lots (user_id, expires_at);
CREATE TABLE credit_transaction_allocations (
	transaction_id INTEGER NOT NULL, 
	lot_id INTEGER NOT NULL, 
	amount INTEGER NOT NULL, 
	CONSTRAINT pk_credit_tx_allocations PRIMARY KEY (transaction_id, lot_id), 
	FOREIGN KEY(transaction_id) REFERENCES credit_transactions (id) ON DELETE CASCADE, 
	FOREIGN KEY(lot_id) REFERENCES credit_lots (id) ON DELETE CASCADE
);
